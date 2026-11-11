import sys
import os
import json
import time
import importlib.util
import unittest

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
                raw_expected = step.get("expected_result")
                expected = self.resolve_arg(raw_expected)
                operator = step.get("operator", "==")

                # Próba konwersji typu oczekiwanego, jeśli to możliwe
                try:
                    if isinstance(actual_result, (int, float)) and not isinstance(expected, (int, float)):
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

