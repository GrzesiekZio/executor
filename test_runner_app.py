import sys
import os
import json
import time
import importlib.util
import unittest
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ==========================================
# REPOZYTORIUM / SILNIK TESTOWY (BACKEND)
# ==========================================

class SequenceRunner:
    def __init__(self, sequence_data, base_dir=".", log_callback=None, step_update_callback=None):
        self.sequence_data = sequence_data
        self.base_dir = base_dir
        self.log_callback = log_callback
        self.step_update_callback = step_update_callback

        self.variables = sequence_data.get("variables", {})
        self.is_paused = False
        self.is_stopped = False
        self.results = []

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def update_step_status(self, section, step_idx, status, result_details=""):
        if self.step_update_callback:
            self.step_update_callback(section, step_idx, status, result_details)

    def check_control_flags(self):
        while self.is_paused and not self.is_stopped:
            time.sleep(0.1)
        if self.is_stopped:
            raise InterruptedError("Sequence stopped by user.")

    def resolve_arg(self, arg):
        if isinstance(arg, str) and arg.startswith("${") and arg.endswith("}"):
            var_name = arg[2:-1]
            return self.variables.get(var_name, arg)
        return arg

    def run_sequence(self):
        self.log(f"=== Starting Sequence: {self.sequence_data.get('name', 'Unnamed')} ===")
        sections = ["preparation", "execution", "cleanup"]

        for section in sections:
            steps = self.sequence_data.get(section, [])
            if not steps:
                continue
            self.log(f"\n--- Section: {section.upper()} ---")
            for idx, step in enumerate(steps):
                try:
                    self.check_control_flags()
                except InterruptedError:
                    self.log("!!! Execution Halted !!!")
                    return self.results

                self.update_step_status(section, idx, "Running...")
                res = self.execute_step(step, section, idx)
                self.results.append(res)
                self.update_step_status(section, idx, res["status"], res["details"])
                self.log(f"Step '{step.get('name')}': {res['status']} | Details: {res['details']}")

        self.log("\n=== Sequence Completed ===")
        return self.results

    def execute_step(self, step, section, idx):
        step_type = step.get("type", "Execute")
        step_name = step.get("name", "Unnamed Step")

        # Scenario A: Sub-sequence Call
        if step_type == "SubSequence":
            sub_path = os.path.join(self.base_dir, step.get("filepath", ""))
            if not os.path.exists(sub_path):
                return {"name": step_name, "type": step_type, "status": "Error",
                        "details": f"File not found: {sub_path}"}
            try:
                with open(sub_path, 'r', encoding='utf-8') as f:
                    sub_data = json.load(f)
                sub_runner = SequenceRunner(sub_data, os.path.dirname(sub_path), self.log_callback)
                sub_results = sub_runner.run_sequence()
                has_error = any(r["status"] in ["Error", "Fail"] for r in sub_results)
                status = "Fail" if has_error else "Done"
                return {"name": step_name, "type": step_type, "status": status, "details": "Sub-sequence executed"}
            except Exception as e:
                return {"name": step_name, "type": step_type, "status": "Error", "details": str(e)}

        # Scenario B: Python File execution (unittest or custom function)
        py_file = step.get("filepath", "")
        func_name = step.get("function", "")
        is_unittest = step.get("is_unittest", False)

        full_py_path = os.path.join(self.base_dir, py_file)
        if not os.path.exists(full_py_path):
            return {"name": step_name, "type": step_type, "status": "Error",
                    "details": f"Python file not found: {full_py_path}"}

        try:
            spec = importlib.util.spec_from_file_location("dynamic_mod", full_py_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["dynamic_mod"] = mod
            spec.loader.exec_module(mod)

            # Standard Unittest Integration
            if is_unittest:
                class_name = step.get("class_name", "")
                test_class = getattr(mod, class_name)
                suite = unittest.TestSuite()
                suite.addTest(test_class(func_name))
                runner = unittest.TextTestRunner(stream=open(os.devnull, 'w'), verbosity=0)
                test_result = runner.run(suite)

                if test_result.wasSuccessful():
                    status = "Pass" if step_type == "Test" else "Done"
                    details = "Unittest Passed"
                elif test_result.failures:
                    status = "Fail" if step_type == "Test" else "Error"
                    details = test_result.failures[0][1].splitlines()[-1]
                else:
                    status = "Error"
                    details = test_result.errors[0][1].splitlines()[-1]

                return {"name": step_name, "type": step_type, "status": status, "details": details}

            # Standard Python Function Integration
            func = getattr(mod, func_name)
            raw_args = step.get("args", {})
            resolved_args = {k: self.resolve_arg(v) for k, v in raw_args.items()}

            actual_result = func(**resolved_args)

            if step_type == "Execute":
                return {"name": step_name, "type": step_type, "status": "Done", "details": f"Returned: {actual_result}"}

            elif step_type == "Test":
                expected = step.get("expected_result")
                operator = step.get("operator", "==")

                # Próba konwersji typu oczekiwanego, jeśli to możliwe
                try:
                    if isinstance(actual_result, (int, float)):
                        expected = type(actual_result)(expected)
                except ValueError:
                    pass

                passed = False
                if operator == "==":
                    passed = (actual_result == expected)
                elif operator == "!=":
                    passed = (actual_result != expected)
                elif operator == ">":
                    passed = (actual_result > expected)
                elif operator == "<":
                    passed = (actual_result < expected)

                status = "Pass" if passed else "Fail"
                details = f"Expected {operator} {expected}, Got: {actual_result}"
                return {"name": step_name, "type": step_type, "status": status, "details": details}

        except Exception as e:
            return {"name": step_name, "type": step_type, "status": "Error", "details": str(e)}

    @staticmethod
    def generate_html_report(sequence_name, results, output_filepath):
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Test Report - {sequence_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f9; }}
        h1 {{ color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
        th {{ background-color: #007bff; color: white; }}
        .Pass, .Done {{ background-color: #d4edda; color: #155724; font-weight: bold; }}
        .Fail {{ background-color: #f8d7da; color: #721c24; font-weight: bold; }}
        .Error {{ background-color: #fff3cd; color: #856404; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Test Execution Report</h1>
    <p><strong>Sequence Name:</strong> {sequence_name}</p>
    <p><strong>Generated At:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    <table>
        <tr>
            <th>#</th>
            <th>Step Name</th>
            <th>Type</th>
            <th>Status</th>
            <th>Details</th>
        </tr>
"""
        for i, res in enumerate(results, 1):
            html += f"""
        <tr>
            <td>{i}</td>
            <td>{res['name']}</td>
            <td>{res['type']}</td>
            <td class="{res['status']}">{res['status']}</td>
            <td>{res['details']}</td>
        </tr>"""
        html += """
    </table>
</body>
</html>"""
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(html)


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


# ==========================================
# INTERFEJS GRAFICZNY (GUI - TKINTER)
# ==========================================

class TestStandApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Test Sequence Runner & Editor")
        self.root.geometry("1000x700")

        self.current_sequence_path = None
        self.sequence_data = self.get_empty_sequence()
        self.runner = None
        self.execution_thread = None

        self.setup_ui()

    def get_empty_sequence(self):
        return {
            "name": "New Sequence",
            "variables": {"VOLTAGE_LIMIT": 12.5, "TIMEOUT_SEC": 5},
            "preparation": [],
            "execution": [],
            "cleanup": []
        }

    def setup_ui(self):
        # Top Control Panel
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        btn_open = ttk.Button(control_frame, text="Open Sequence", command=self.open_sequence)
        btn_open.pack(side=tk.LEFT, padx=2)

        btn_new = ttk.Button(control_frame, text="New Sequence", command=self.new_sequence)
        btn_new.pack(side=tk.LEFT, padx=2)

        btn_save = ttk.Button(control_frame, text="Save Sequence", command=self.save_sequence)
        btn_save.pack(side=tk.LEFT, padx=2)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Editor Buttons
        btn_add = ttk.Button(control_frame, text="➕ Add Step", command=self.add_step)
        btn_add.pack(side=tk.LEFT, padx=2)

        btn_edit = ttk.Button(control_frame, text="✏ Edit Step", command=self.edit_step)
        btn_edit.pack(side=tk.LEFT, padx=2)

        btn_del = ttk.Button(control_frame, text="🗑 Delete Step", command=self.delete_step)
        btn_del.pack(side=tk.LEFT, padx=2)

        btn_vars = ttk.Button(control_frame, text="⚙ Variables", command=self.edit_variables)
        btn_vars.pack(side=tk.LEFT, padx=2)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_run = ttk.Button(control_frame, text="▶ Run", command=self.run_sequence)
        self.btn_run.pack(side=tk.LEFT, padx=2)

        self.btn_pause = ttk.Button(control_frame, text="⏸ Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(control_frame, text="⏹ Stop", command=self.stop_sequence, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_report = ttk.Button(control_frame, text="📊 Export Report", command=self.export_report,
                                     state=tk.DISABLED)
        self.btn_report.pack(side=tk.LEFT, padx=2)

        # Main Split View (Tree + Logs)
        main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Step View (Treeview)
        tree_frame = ttk.Frame(main_paned)
        columns = ("type", "path_func", "status", "details")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Section / Step Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("path_func", text="Target (File / Function)")
        self.tree.heading("status", text="Status")
        self.tree.heading("details", text="Execution Details")

        self.tree.column("#0", width=220)
        self.tree.column("type", width=90)
        self.tree.column("path_func", width=220)
        self.tree.column("status", width=90)
        self.tree.column("details", width=250)

        # Tags for status colors
        self.tree.tag_configure("Pass", background="#d4edda")
        self.tree.tag_configure("Done", background="#d4edda")
        self.tree.tag_configure("Fail", background="#f8d7da")
        self.tree.tag_configure("Error", background="#fff3cd")
        self.tree.tag_configure("Running...", background="#cce5ff")

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        main_paned.add(tree_frame, weight=3)

        # Log Console Frame
        log_frame = ttk.LabelFrame(main_paned, text="Execution Console Log", padding=5)
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, background="#1e1e1e", foreground="#d4d4d4",
                                font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        main_paned.add(log_frame, weight=1)

        self.refresh_tree()

    def log_to_console(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        sections = ["preparation", "execution", "cleanup"]
        for sec in sections:
            sec_node = self.tree.insert("", tk.END, text=sec.upper(), open=True)
            for idx, step in enumerate(self.sequence_data.get(sec, [])):
                target = step.get("filepath", "")
                if step.get("function"): target += f" -> {step.get('function')}()"

                node_id = f"{sec}_{idx}"
                self.tree.insert(sec_node, tk.END, iid=node_id, text=step.get("name", "Step"),
                                 values=(step.get("type", "Execute"), target, "Idle", ""))

    def update_step_ui(self, section, step_idx, status, details=""):
        node_id = f"{section}_{step_idx}"

        def _update():
            if self.tree.exists(node_id):
                item_vals = list(self.tree.item(node_id, "values"))
                item_vals[2] = status
                item_vals[3] = details
                self.tree.item(node_id, values=item_vals, tags=(status,))

        self.root.after(0, _update)

    # --- Edycja Sekwencji (Add / Edit / Delete) ---
    def add_step(self):
        dialog = StepEditorDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result:
            sec = dialog.section
            if sec not in self.sequence_data:
                self.sequence_data[sec] = []
            self.sequence_data[sec].append(dialog.result)
            self.refresh_tree()
            self.log_to_console(f"Added step '{dialog.result['name']}' to section {sec}.")

    def edit_step(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a step to edit.")
            return

        node_id = selected[0]
        parts = node_id.split('_')
        if len(parts) != 2:
            messagebox.showwarning("Warning", "Please select a specific step, not a section header.")
            return

        sec, idx_str = parts[0], parts[1]
        idx = int(idx_str)
        step_data = self.sequence_data[sec][idx]

        dialog = StepEditorDialog(self.root, step_data=step_data, default_section=sec)
        self.root.wait_window(dialog)
        if dialog.result:
            # Jeśli sekcja została zmieniona
            old_sec = sec
            new_sec = dialog.section

            if old_sec != new_sec:
                self.sequence_data[old_sec].pop(idx)
                if new_sec not in self.sequence_data:
                    self.sequence_data[new_sec] = []
                self.sequence_data[new_sec].append(dialog.result)
            else:
                self.sequence_data[sec][idx] = dialog.result

            self.refresh_tree()
            self.log_to_console(f"Updated step '{dialog.result['name']}'.")

    def delete_step(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a step to delete.")
            return

        node_id = selected[0]
        parts = node_id.split('_')
        if len(parts) != 2:
            messagebox.showwarning("Warning", "Please select a specific step to delete.")
            return

        sec, idx = parts[0], int(parts[1])
        step_name = self.sequence_data[sec][idx].get("name", "Step")

        if messagebox.askyesno("Confirm", f"Are you sure you want to delete step '{step_name}'?"):
            self.sequence_data[sec].pop(idx)
            self.refresh_tree()
            self.log_to_console(f"Deleted step '{step_name}'.")

    def edit_variables(self):
        # Okno dialogowe edycji zmiennych jako tekst JSON
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Sequence Variables")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Variables (JSON format):").pack(anchor=tk.W, padx=10, pady=5)
        txt = tk.Text(dialog, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        current_vars = self.sequence_data.get("variables", {})

        # POPRAWKA TUTAJ: zmieniono na "1.0" (początek tekstu)
        txt.insert("1.0", json.dumps(current_vars, indent=4))

        def save_vars():
            try:
                parsed = json.loads(txt.get("1.0", tk.END))
                self.sequence_data["variables"] = parsed
                self.log_to_console("Sequence variables updated.")
                dialog.destroy()
            except json.JSONDecodeError as e:
                messagebox.showerror("Error", f"Invalid JSON format:\n{e}")

        ttk.Button(dialog, text="Save Variables", command=save_vars).pack(pady=10)

    # --- File Operations ---
    def open_sequence(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.sequence_data = json.load(f)
            self.current_sequence_path = file_path
            self.refresh_tree()
            self.log_to_console(f"Loaded sequence: {file_path}")

    def new_sequence(self):
        self.sequence_data = self.get_empty_sequence()
        self.current_sequence_path = None
        self.refresh_tree()
        self.log_to_console("Created new sequence template.")

    def save_sequence(self):
        if not self.current_sequence_path:
            self.current_sequence_path = filedialog.asksaveasfilename(defaultextension=".json",
                                                                      filetypes=[("JSON Files", "*.json")])
        if self.current_sequence_path:
            with open(self.current_sequence_path, 'w', encoding='utf-8') as f:
                json.dump(self.sequence_data, f, indent=4)
            messagebox.showinfo("Saved", "Sequence saved successfully.")

    # --- Execution Controls ---
    def run_sequence(self):
        self.refresh_tree()
        base_dir = os.path.dirname(self.current_sequence_path) if self.current_sequence_path else "."

        self.runner = SequenceRunner(
            self.sequence_data,
            base_dir=base_dir,
            log_callback=self.log_to_console,
            step_update_callback=self.update_step_ui
        )

        self.btn_run.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸ Pause")
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_report.config(state=tk.DISABLED)

        def worker():
            self.runner.run_sequence()
            self.root.after(0, self.on_execution_finished)

        self.execution_thread = threading.Thread(target=worker, daemon=True)
        self.execution_thread.start()

    def toggle_pause(self):
        if self.runner:
            self.runner.is_paused = not self.runner.is_paused
            btn_text = "▶ Resume" if self.runner.is_paused else "⏸ Pause"
            self.btn_pause.config(text=btn_text)
            self.log_to_console("PAUSED..." if self.runner.is_paused else "RESUMED.")

    def stop_sequence(self):
        if self.runner:
            self.runner.is_stopped = True
            self.log_to_console("Stopping sequence...")

    def on_execution_finished(self):
        self.btn_run.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_report.config(state=tk.NORMAL)
        self.log_to_console("Execution thread finished.")

    def export_report(self):
        if not self.runner or not self.runner.results:
            messagebox.showwarning("Warning", "No execution results to export.")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML Report", "*.html")])
        if save_path:
            self.runner.generate_html_report(self.sequence_data.get("name", "Sequence"), self.runner.results, save_path)
            messagebox.showinfo("Report Exported", f"Report saved to:\n{save_path}")


# ==========================================
# KOD URUCHOMIENIOWY
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    app = TestStandApp(root)
    root.mainloop()