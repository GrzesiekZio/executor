import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
import inspect
import importlib.util
import unittest


# ==========================================
# DIALOG EDYCJI KROKU
# ==========================================

class StepEditorDialog(tk.Toplevel):
    def __init__(self, parent, step_data=None, default_section="execution", base_dir="."):
        super().__init__(parent)
        self.title("Step Configuration")
        self.geometry("520x620")
        self.transient(parent)
        self.grab_set()

        self.base_dir = base_dir
        self.result = None
        self.step_data = step_data or {
            "name": "New Step",
            "type": "Execute",
            "filepath": "",
            "function": "",
            "is_unittest": False,
            "class_name": "",
            "operator": "==",
            "expected_result": "",
            "args": {}
        }
        self.section = default_section
        self.scanned_items = {}  # Słownik przechowujący obiekty funkcji/metod do wyciągania argumentów

        self.create_widgets()

        # Jeśli edytujemy istniejący krok i ma już ścieżkę do pliku, załaduj funkcje automatycznie
        initial_file = self.step_data.get("filepath", "")
        if initial_file:
            self.scan_python_file(initial_file, select_func=self.step_data.get("function", ""))

    def create_widgets(self):
        pad = {'padx': 10, 'pady': 5}

        # Section
        ttk.Label(self, text="Section:").pack(anchor=tk.W, **pad)
        self.sec_cb = ttk.Combobox(self, values=["preparation", "execution", "cleanup"], state="readonly")
        self.sec_cb.pack(fill=tk.X, **pad)
        self.sec_cb.set(self.section)

        # Name
        ttk.Label(self, text="Step Name:").pack(anchor=tk.W, **pad)
        self.name_ent = ttk.Entry(self)
        self.name_ent.pack(fill=tk.X, **pad)
        self.name_ent.insert(0, self.step_data.get("name", ""))

        # Type
        ttk.Label(self, text="Step Type:").pack(anchor=tk.W, **pad)
        self.type_cb = ttk.Combobox(self, values=["Execute", "Test", "SubSequence"], state="readonly")
        self.type_cb.pack(fill=tk.X, **pad)
        self.type_cb.set(self.step_data.get("type", "Execute"))

        # Filepath with browse & scan
        ttk.Label(self, text="File Path (Python script / JSON):").pack(anchor=tk.W, **pad)
        f_frame = ttk.Frame(self)
        f_frame.pack(fill=tk.X, **pad)
        self.file_ent = ttk.Entry(f_frame)
        self.file_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.file_ent.insert(0, self.step_data.get("filepath", ""))

        ttk.Button(f_frame, text="Browse...", command=self.browse_file).pack(side=tk.RIGHT, padx=2)
        ttk.Button(f_frame, text="Scan", command=self.manual_scan).pack(side=tk.RIGHT, padx=2)

        # Function / Method Name (Combobox zamiast Entry)
        ttk.Label(self, text="Function Name / Test Method:").pack(anchor=tk.W, **pad)
        self.func_cb = ttk.Combobox(self, state="readonly")
        self.func_cb.pack(fill=tk.X, **pad)
        self.func_cb.bind("<<ComboboxSelected>>", self.on_function_selected)

        # Unittest options
        self.ut_var = tk.BooleanVar(value=self.step_data.get("is_unittest", False))
        ttk.Checkbutton(self, text="Is Python Unittest Case?", variable=self.ut_var).pack(anchor=tk.W, **pad)

        ttk.Label(self, text="Test Class Name (if unittest):").pack(anchor=tk.W, **pad)
        self.class_ent = ttk.Entry(self)
        self.class_ent.pack(fill=tk.X, **pad)
        self.class_ent.insert(0, self.step_data.get("class_name", ""))

        # Test assertion options
        test_frame = ttk.LabelFrame(self, text="Test Assertions (Only for 'Test' type)", padding=5)
        test_frame.pack(fill=tk.X, **pad)

        ttk.Label(test_frame, text="Operator:").pack(side=tk.LEFT)
        self.op_cb = ttk.Combobox(test_frame, values=["==", "!=", ">", "<"], width=5, state="readonly")
        self.op_cb.pack(side=tk.LEFT, padx=5)
        self.op_cb.set(self.step_data.get("operator", "=="))

        ttk.Label(test_frame, text="Expected:").pack(side=tk.LEFT, padx=5)
        self.exp_ent = ttk.Entry(test_frame, width=15)
        self.exp_ent.pack(side=tk.LEFT, padx=5)
        self.exp_ent.insert(0, str(self.step_data.get("expected_result", "")))

        # Args JSON
        ttk.Label(self, text="Arguments (JSON format, e.g. {\"param\": \"value\"}):").pack(anchor=tk.W, **pad)
        self.args_ent = ttk.Entry(self)
        self.args_ent.pack(fill=tk.X, **pad)
        args_dict = self.step_data.get("args", {})
        self.args_ent.insert(0, json.dumps(args_dict))

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=15)
        ttk.Button(btn_frame, text="Save", command=self.on_save).pack(side=tk.RIGHT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Python/JSON Files", "*.py *.json"), ("All Files", "*.*")])
        if filename:
            rel_path = os.path.basename(filename)  # lub ścieżka względna jeśli wolisz
            self.file_ent.delete(0, tk.END)
            self.file_ent.insert(0, rel_path)
            self.scan_python_file(filename)

    def manual_scan(self):
        filepath = self.file_ent.get().strip()
        if not filepath:
            messagebox.showwarning("Warning", "Please provide a file path first.")
            return
        full_path = filepath if os.path.isabs(filepath) else os.path.join(self.base_dir, filepath)
        self.scan_python_file(full_path)

    def scan_python_file(self, filepath, select_func=""):
        full_path = filepath if os.path.isabs(filepath) else os.path.join(self.base_dir, filepath)
        if not os.path.exists(full_path) or not full_path.endswith('.py'):
            return

        try:
            mod_name = "dynamic_editor_mod"
            spec = importlib.util.spec_from_file_location(mod_name, full_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

            options = []
            self.scanned_items = {}

            # Skanowanie modułu w poszukiwaniu funkcji i testów
            for name, obj in inspect.getmembers(mod):
                # Zwykłe funkcje
                if inspect.isfunction(obj) and not name.startswith('_'):
                    if obj.__module__ == mod.__name__:
                        display_name = f"func: {name}"
                        options.append(display_name)
                        self.scanned_items[display_name] = {
                            "name": name,
                            "is_unittest": False,
                            "class_name": "",
                            "obj": obj
                        }
                # Klasy unittest
                elif inspect.isclass(obj) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                    class_name = name
                    for method_name, method_obj in inspect.getmembers(obj, predicate=inspect.isfunction):
                        if method_name.startswith('test_'):
                            display_name = f"unittest: {class_name}.{method_name}"
                            options.append(display_name)
                            self.scanned_items[display_name] = {
                                "name": method_name,
                                "is_unittest": True,
                                "class_name": class_name,
                                "obj": method_obj
                            }

            self.func_cb['values'] = options

            # Próba zaznaczenia wcześniej wybranej funkcji, jeśli istnieje
            if select_func:
                for opt in options:
                    if select_func in opt:
                        self.func_cb.set(opt)
                        break
            elif options:
                self.func_cb.set(options[0])
                self.on_function_selected(None)

        except Exception as e:
            print(f"Error scanning file: {e}")

    def on_function_selected(self, event):
        selected = self.func_cb.get()
        if not selected or selected not in self.scanned_items:
            return

        item = self.scanned_items[selected]
        self.ut_var.set(item["is_unittest"])

        self.class_ent.delete(0, tk.END)
        self.class_ent.insert(0, item["class_name"])

        # Automatyczne generowanie argumentów na podstawie sygnatury funkcji
        obj = item["obj"]
        try:
            sig = inspect.signature(obj)
            args_dict = {}
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                # Jeśli funkcja ma domyślną wartość, używamy jej; w przeciwnym razie pusty ciąg
                if param.default != inspect.Parameter.empty:
                    default_val = param.default
                    if isinstance(default_val, (int, float, str, bool, list, dict, type(None))):
                        args_dict[param_name] = default_val
                    else:
                        args_dict[param_name] = str(default_val)
                else:
                    args_dict[param_name] = ""

            self.args_ent.delete(0, tk.END)
            self.args_ent.insert(0, json.dumps(args_dict))
        except Exception as e:
            print(f"Could not inspect signature: {e}")

    def on_save(self):
        try:
            raw_args = self.args_ent.get().strip()
            args_parsed = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Arguments must be a valid JSON dictionary (e.g. {\"x\": 10})")
            return

        # Wyciągamy czystą nazwę funkcji/metody z wybranego elementu comboboxa
        selected_display = self.func_cb.get()
        func_name = ""
        if selected_display in self.scanned_items:
            func_name = self.scanned_items[selected_display]["name"]
        else:
            func_name = selected_display  # fallback jeśli wpisano ręcznie

        self.section = self.sec_cb.get()
        self.result = {
            "name": self.name_ent.get(),
            "type": self.type_cb.get(),
            "filepath": self.file_ent.get(),
            "function": func_name,
            "is_unittest": self.ut_var.get(),
            "class_name": self.class_ent.get(),
            "operator": self.op_cb.get(),
            "expected_result": self.exp_ent.get(),
            "args": args_parsed
        }
        self.destroy()