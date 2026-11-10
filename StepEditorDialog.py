import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os

# ==========================================
# DIALOG EDYCJI KROKU
# ==========================================

class StepEditorDialog(tk.Toplevel):
    def __init__(self, parent, step_data=None, default_section="execution"):
        super().__init__(parent)
        self.title("Step Configuration")
        self.geometry("500x550")
        self.transient(parent)
        self.grab_set()

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
        self.create_widgets()

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

        # Filepath with browse
        ttk.Label(self, text="File Path (Python script / JSON):").pack(anchor=tk.W, **pad)
        f_frame = ttk.Frame(self)
        f_frame.pack(fill=tk.X, **pad)
        self.file_ent = ttk.Entry(f_frame)
        self.file_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.file_ent.insert(0, self.step_data.get("filepath", ""))
        ttk.Button(f_frame, text="Browse...", command=self.browse_file).pack(side=tk.RIGHT, padx=5)

        # Function / Method Name
        ttk.Label(self, text="Function Name / Test Method:").pack(anchor=tk.W, **pad)
        self.func_ent = ttk.Entry(self)
        self.func_ent.pack(fill=tk.X, **pad)
        self.func_ent.insert(0, self.step_data.get("function", ""))

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
            self.file_ent.delete(0, tk.END)
            self.file_ent.insert(0, os.path.basename(filename))

    def on_save(self):
        try:
            raw_args = self.args_ent.get().strip()
            args_parsed = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Arguments must be a valid JSON dictionary (e.g. {\"x\": 10})")
            return

        self.section = self.sec_cb.get()
        self.result = {
            "name": self.name_ent.get(),
            "type": self.type_cb.get(),
            "filepath": self.file_ent.get(),
            "function": self.func_ent.get(),
            "is_unittest": self.ut_var.get(),
            "class_name": self.class_ent.get(),
            "operator": self.op_cb.get(),
            "expected_result": self.exp_ent.get(),
            "args": args_parsed
        }
        self.destroy()
