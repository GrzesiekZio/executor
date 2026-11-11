import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import SequenceRunner as srun
import StepEditorDialog as sed

# ==========================================
# INTERFEJS GRAFICZNY (GUI - TKINTER)
# ==========================================

class TestExecutor:
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
        base_dir = os.path.dirname(self.current_sequence_path) if self.current_sequence_path else "."
        dialog = sed.StepEditorDialog(self.root, base_dir=base_dir)
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

        base_dir = os.path.dirname(self.current_sequence_path) if self.current_sequence_path else "."
        dialog = sed.StepEditorDialog(self.root, step_data=step_data, default_section=sec,base_dir=base_dir)
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

        self.runner = srun.SequenceRunner(
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
