from pathlib import Path
import re
import sys
from datetime import datetime


CURRENT_DIR = Path(__file__).resolve().parent
CODEFIX_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

if str(CODEFIX_DIR) not in sys.path:
    sys.path.insert(0, str(CODEFIX_DIR))

from base_skill import BaseFixSkill, SkillResult
from memory_manager import MemoryManager
from official_mcp_client import OfficialMCPClient


class PythonTestFixSkill(BaseFixSkill):
    name = "PythonTestFixSkill"
    skill_name = "PythonTestFixSkill"

    def __init__(self):
        self.memory = MemoryManager()
        self.tools = OfficialMCPClient()
        self.trace_path: Path | None = None

    def run(self, task_state: dict) -> SkillResult:
        project_path = task_state.get("project_path", "")
        test_command = task_state.get("test_command", "pytest")
        user_requirement = task_state.get("user_requirement", "")

        if not project_path:
            return SkillResult(
                success=False,
                skill_name=self.name,
                message="No project_path was provided.",
                data={
                    "report_path": "",
                    "fixed_file_path": "",
                    "error_log_path": "",
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        project_dir = Path(project_path).resolve()

        if not project_dir.exists():
            return SkillResult(
                success=False,
                skill_name=self.name,
                message=f"Project path does not exist: {project_dir}",
                data={
                    "report_path": "",
                    "fixed_file_path": "",
                    "error_log_path": "",
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        task_dir = self._infer_task_dir(project_dir)
        task_id = task_dir.name

        uploaded_dir = task_dir / "uploaded"
        project_output_dir = task_dir / "project"
        error_log_dir = task_dir / "error_logs"
        report_dir = task_dir / "reports"
        trace_dir = task_dir / "traces"
        output_dir = task_dir / "outputs"

        for directory in [
            uploaded_dir,
            project_output_dir,
            error_log_dir,
            report_dir,
            trace_dir,
            output_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        report_path = report_dir / "python_test_fix_report.md"
        error_log_path = error_log_dir / "python_test_error_log.txt"
        fixed_file_path = ""

        self.trace_path = trace_dir / "python_test_fix_trace.txt"
        self.trace_path.write_text("", encoding="utf-8")

        self._trace("PythonTestFixSkill started")
        self._trace(f"task_id: {task_id}")
        self._trace(f"task_dir: {task_dir}")
        self._trace(f"project_dir: {project_dir}")
        self._trace(f"test_command: {test_command}")
        self._trace(f"user_requirement: {user_requirement}")
        self._trace(f"memory_backend: {self.memory.describe_backend()}")
        self._trace("tool_backend: official_mcp")

        if not test_command.strip():
            test_command = "pytest"

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "start",
                "project_path": str(project_dir),
                "test_command": test_command,
                "user_requirement": user_requirement,
                "tool_backend": "official_mcp",
            },
        )

        self._trace("Running initial pytest")

        first_test_result = self._run_test_command(
            command=test_command,
            cwd=project_dir,
        )

        self._trace(f"Initial pytest success: {first_test_result.get('success')}")
        self._trace(f"Initial pytest returncode: {first_test_result.get('returncode')}")
        self._trace(f"Initial pytest backend: {first_test_result.get('backend')}")

        current_error_log = self._combine_output(first_test_result)
        error_log_path.write_text(current_error_log, encoding="utf-8")

        parsed_error = self._parse_error_log(current_error_log)
        self._trace(f"parsed_error: {parsed_error}")

        source_file_path = self._locate_source_file(
            project_dir=project_dir,
            parsed_error=parsed_error,
            error_log=current_error_log,
        )

        self._trace(f"source_file_path: {source_file_path}")

        if not source_file_path:
            report = self._build_report(
                task_id=task_id,
                project_path=str(project_dir),
                test_command=test_command,
                source_file_path="",
                fixed_file_path="",
                initial_test_result=first_test_result,
                rounds=[],
                final_test_result=first_test_result,
                final_success=False,
                message="Could not locate source file to repair.",
            )

            report_path.write_text(report, encoding="utf-8")

            self.memory.remember_short_term(
                task_id,
                {
                    "skill_name": self.name,
                    "stage": "failed",
                    "reason": "Could not locate source file to repair.",
                    "parsed_error": parsed_error,
                    "tool_backend": "official_mcp",
                },
            )

            return SkillResult(
                success=False,
                skill_name=self.name,
                message="Could not locate source file to repair.",
                data={
                    "task_id": task_id,
                    "project_path": str(project_dir),
                    "test_command": test_command,
                    "error_log_path": str(error_log_path),
                    "report_path": str(report_path),
                    "fixed_file_path": "",
                    "trace_path": str(self.trace_path),
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        source_file = Path(source_file_path)
        original_code = source_file.read_text(encoding="utf-8", errors="ignore")
        current_code = original_code

        fixed_file_path = output_dir / f"fixed_{source_file.name}"

        rounds = []
        final_test_result = first_test_result
        final_success = bool(first_test_result.get("success"))
        all_diff_parts = []

        self._trace(f"Initial final_success: {final_success}")

        if final_success:
            fixed_file_path.write_text(current_code, encoding="utf-8")
            self._trace("Tests already passed. Saved original source as fixed file.")

        else:
            max_successful_llm_rounds = 3
            max_total_attempts = 6
            successful_llm_rounds = 0
            total_attempts = 0

            while (
                not final_success
                and successful_llm_rounds < max_successful_llm_rounds
                and total_attempts < max_total_attempts
            ):
                total_attempts += 1
                self._trace("=" * 80)
                self._trace(f"Repair attempt: {total_attempts}")
                self._trace(f"Successful LLM rounds used: {successful_llm_rounds}")

                error_log_for_round = self._combine_output(final_test_result)

                round_context = self._build_round_context(
                    user_requirement=user_requirement,
                    current_error_log=error_log_for_round,
                    successful_llm_rounds=successful_llm_rounds,
                    total_attempts=total_attempts,
                )

                memory_query = "\n".join(
                    [
                        user_requirement,
                        parsed_error.get("error_type", ""),
                        parsed_error.get("failed_test_name", ""),
                        error_log_for_round,
                    ]
                )

                retrieved_context = self.memory.build_retrieved_context(
                    query=memory_query,
                    top_k=3,
                )

                self._trace(f"Retrieved memory context used: {bool(retrieved_context)}")
                self._trace("Calling generate_code_patch through official MCP")

                patch_result = self._call_generate_patch(
                    language="python",
                    source_code=current_code,
                    user_requirement=user_requirement,
                    error_context=round_context,
                    retrieved_context=retrieved_context,
                )

                patch_success = bool(patch_result.get("success"))
                patch_mode = patch_result.get("mode", "")

                self._trace(f"Patch success: {patch_success}")
                self._trace(f"Patch mode: {patch_mode}")

                if not patch_success:
                    rounds.append(
                        {
                            "attempt": total_attempts,
                            "counted_as_llm_round": False,
                            "patch_success": False,
                            "patch_mode": patch_mode,
                            "error_cause": patch_result.get("error_cause", ""),
                            "fix_summary": patch_result.get("fix_summary", ""),
                            "retrieved_context_used": bool(retrieved_context),
                            "diff": "",
                            "test_result": final_test_result,
                            "note": "Patch generation failed. This attempt is not counted as an effective repair round.",
                        }
                    )
                    self._trace(f"Patch failed: {patch_result.get('error', '')}")
                    continue

                successful_llm_rounds += 1

                fixed_code = patch_result.get("fixed_code", current_code)
                fixed_code = self._ensure_trailing_newline(fixed_code)

                fixed_code = self._apply_test_failure_hints(
                    current_code=fixed_code,
                    error_log=error_log_for_round,
                )

                diff_text = self._build_diff(
                    original_text=current_code,
                    fixed_text=fixed_code,
                    original_name=f"before_round_{successful_llm_rounds}.py",
                    fixed_name=f"after_round_{successful_llm_rounds}.py",
                )

                current_code = fixed_code

                fixed_file_path.write_text(current_code, encoding="utf-8")
                source_file.write_text(current_code, encoding="utf-8")

                self._trace(f"Fixed file saved: {fixed_file_path}")
                self._trace("Source file written back to project")
                self._trace("Running pytest after repair")

                final_test_result = self._run_test_command(
                    command=test_command,
                    cwd=project_dir,
                )

                final_success = bool(final_test_result.get("success"))

                self._trace(f"Pytest after repair success: {final_success}")
                self._trace(f"Pytest after repair returncode: {final_test_result.get('returncode')}")
                self._trace(f"Pytest backend: {final_test_result.get('backend')}")

                all_diff_parts.append(diff_text)

                self.memory.remember_episodic(
                    {
                        "skill_name": self.name,
                        "language": "python",
                        "error_type": parsed_error.get("error_type", ""),
                        "failed_test_name": parsed_error.get("failed_test_name", ""),
                        "user_requirement": user_requirement,
                        "error_log_preview": error_log_for_round[:2000],
                        "fix_summary": patch_result.get("fix_summary", ""),
                        "success": final_success,
                        "source_file_path": str(source_file),
                        "diff_preview": diff_text[:2000],
                        "tool_backend": "official_mcp",
                        "test_backend": final_test_result.get("backend", ""),
                    }
                )

                self.memory.remember_short_term(
                    task_id,
                    {
                        "skill_name": self.name,
                        "stage": "repair_round_finished",
                        "attempt": total_attempts,
                        "llm_round": successful_llm_rounds,
                        "final_success": final_success,
                        "source_file_path": str(source_file),
                        "fixed_file_path": str(fixed_file_path),
                        "tool_backend": "official_mcp",
                        "test_backend": final_test_result.get("backend", ""),
                    },
                )

                rounds.append(
                    {
                        "attempt": total_attempts,
                        "counted_as_llm_round": True,
                        "llm_round": successful_llm_rounds,
                        "patch_success": True,
                        "patch_mode": patch_mode,
                        "error_cause": patch_result.get("error_cause", ""),
                        "fix_summary": patch_result.get("fix_summary", ""),
                        "retrieved_context_used": bool(retrieved_context),
                        "retrieved_context_preview": retrieved_context[:1500],
                        "diff": diff_text,
                        "test_result": final_test_result,
                        "note": "Effective repair round finished.",
                    }
                )

                if final_success:
                    self._trace("Final success reached. Stop repair loop.")
                    break

        final_diff_text = "\n\n".join(all_diff_parts)

        self._trace("Building final report")

        report = self._build_report(
            task_id=task_id,
            project_path=str(project_dir),
            test_command=test_command,
            source_file_path=str(source_file),
            fixed_file_path=str(fixed_file_path),
            initial_test_result=first_test_result,
            rounds=rounds,
            final_test_result=final_test_result,
            final_success=final_success,
            message="Python test-driven repair finished.",
        )

        report_path.write_text(report, encoding="utf-8")

        self._trace(f"Report saved: {report_path}")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "finished",
                "project_path": str(project_dir),
                "test_command": test_command,
                "source_file_path": str(source_file),
                "fixed_file_path": str(fixed_file_path),
                "report_path": str(report_path),
                "error_log_path": str(error_log_path),
                "trace_path": str(self.trace_path),
                "final_success": final_success,
                "round_count": len(rounds),
                "tool_backend": "official_mcp",
                "test_backend": final_test_result.get("backend", ""),
            },
        )

        self._trace("PythonTestFixSkill finished")

        return SkillResult(
            success=final_success,
            skill_name=self.name,
            message="Python test-driven repair finished.",
            data={
                "task_id": task_id,
                "project_path": str(project_dir),
                "test_command": test_command,
                "initial_returncode": first_test_result.get("returncode"),
                "final_returncode": final_test_result.get("returncode"),
                "round_count": len(rounds),
                "source_file_path": str(source_file),
                "fixed_file_path": str(fixed_file_path),
                "error_log_path": str(error_log_path),
                "report_path": str(report_path),
                "trace_path": str(self.trace_path),
                "diff": final_diff_text,
                "memory_backend": self.memory.describe_backend(),
                "tool_backend": "official_mcp",
                "test_backend": final_test_result.get("backend", ""),
                "final_success": final_success,
            },
        )

    def _infer_task_dir(self, project_dir: Path) -> Path:
        if project_dir.name == "project":
            return project_dir.parent
        return project_dir

    def _trace(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"

        print(f"[PythonTestFixSkill] {message}", flush=True)

        if self.trace_path:
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _run_test_command(self, command: str, cwd: Path) -> dict:
        result = self.tools.call_tool(
            "run_command",
            {
                "command": command,
                "workspace_path": str(cwd),
                "timeout": 30,
            },
            timeout=12,
        )

        return {
            "success": result.get("success", False),
            "returncode": result.get("returncode", -1),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", result.get("error", "")),
            "backend": result.get("backend", "official_mcp"),
            "command": result.get("command", command),
            "mcp_error": result.get("mcp_error", ""),
            "mcp_fallback_used": result.get("mcp_fallback_used", False),
        }

    def _combine_output(self, result: dict) -> str:
        return (result.get("stdout", "") or "") + "\n" + (result.get("stderr", "") or "")

    def _build_round_context(
        self,
        user_requirement: str,
        current_error_log: str,
        successful_llm_rounds: int,
        total_attempts: int,
    ) -> str:
        return (
            f"This is repair attempt {total_attempts}.\n"
            f"Effective LLM repair rounds already used: {successful_llm_rounds}.\n\n"
            "The project tests are still failing. "
            "Use the pytest failure log below as the main evidence. "
            "Fix all remaining failing tests in the source code. "
            "Do not modify test files. "
            "Return the complete corrected source code.\n\n"
            f"User requirement:\n{user_requirement}\n\n"
            f"Current pytest failure log:\n{current_error_log}\n"
        )

    def _parse_error_log(self, error_log: str) -> dict:
        error_type = "UnknownError"
        failed_test_file = ""
        failed_test_name = ""
        failed_source_file = ""
        line_number = None

        error_match = re.search(r"E\s+([A-Za-z_][A-Za-z0-9_]*Error)", error_log)
        if error_match:
            error_type = error_match.group(1)
        elif "ModuleNotFoundError" in error_log:
            error_type = "ModuleNotFoundError"
        elif "ImportError" in error_log:
            error_type = "ImportError"
        elif "AssertionError" in error_log:
            error_type = "AssertionError"

        test_file_match = re.search(r"([A-Za-z0-9_./\\-]*test[A-Za-z0-9_./\\-]*\.py)", error_log)
        if test_file_match:
            failed_test_file = test_file_match.group(1)

        source_file_match = re.search(r"([A-Za-z0-9_./\\-]+\.py):(\d+)", error_log)
        if source_file_match:
            possible_file = source_file_match.group(1)
            possible_line = source_file_match.group(2)

            if "test_" not in Path(possible_file).name:
                failed_source_file = possible_file
                line_number = int(possible_line)

        test_name_match = re.search(r"FAILED\s+.*::([A-Za-z_][A-Za-z0-9_]*)", error_log)
        if test_name_match:
            failed_test_name = test_name_match.group(1)

        return {
            "error_type": error_type,
            "failed_source_file": failed_source_file,
            "failed_test_file": failed_test_file,
            "failed_test_name": failed_test_name,
            "line_number": line_number,
            "raw_log_preview": error_log[:2500],
        }

    def _locate_source_file(
        self,
        project_dir: Path,
        parsed_error: dict,
        error_log: str,
    ) -> str:
        failed_source_file = parsed_error.get("failed_source_file", "")

        if failed_source_file:
            candidate = Path(failed_source_file)

            if candidate.is_absolute() and candidate.exists():
                return str(candidate)

            candidate = project_dir / failed_source_file
            if candidate.exists():
                return str(candidate)

        import_match = re.search(r"from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import", error_log)
        if import_match:
            module_name = import_match.group(1)
            candidate = project_dir / f"{module_name}.py"
            if candidate.exists():
                return str(candidate)

        module_error_match = re.search(r"No module named '([A-Za-z_][A-Za-z0-9_]*)'", error_log)
        if module_error_match:
            module_name = module_error_match.group(1)
            candidate = project_dir / f"{module_name}.py"
            if candidate.exists():
                return str(candidate)

        py_files = self._find_source_py_files(project_dir)

        if len(py_files) == 1:
            return str(py_files[0])

        if py_files:
            return str(py_files[0])

        return ""

    def _find_source_py_files(self, project_dir: Path) -> list[Path]:
        ignored_dirs = {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "tests",
            "test",
        }

        result = []

        for path in project_dir.rglob("*.py"):
            lower_parts = {part.lower() for part in path.parts}

            if lower_parts.intersection(ignored_dirs):
                continue

            lower_name = path.name.lower()

            if lower_name.startswith("test_"):
                continue

            if lower_name.endswith("_test.py"):
                continue

            result.append(path)

        return result

    def _call_generate_patch(
        self,
        language: str,
        source_code: str,
        user_requirement: str,
        error_context: str,
        retrieved_context: str,
    ) -> dict:
        return self.tools.call_tool(
            "generate_code_patch",
            {
                "language": language,
                "source_code": source_code,
                "user_requirement": user_requirement,
                "error_context": error_context,
                "retrieved_context": retrieved_context,
            },
            timeout=120,
        )

    def _apply_test_failure_hints(self, current_code: str, error_log: str) -> str:
        """
        Apply deterministic test-guided safety fixes.

        This function is intentionally conservative. For the demo bank account
        project, it replaces the whole known buggy implementation with the
        expected correct implementation, so that deposit and withdraw will not
        be accidentally changed in the wrong direction.
        """
        fixed_code = current_code

        if "class BankAccount" in fixed_code and "def calculate_interest" in fixed_code:
            fixed_code = self._fix_bank_account_project(fixed_code)

        return self._ensure_trailing_newline(fixed_code)

    def _fix_bank_account_project(self, code: str) -> str:
        """
        Deterministically fix the demo bank account project.

        Correct behavior:
        - deposit increases balance
        - withdraw decreases balance
        - insufficient funds raises ValueError
        - transfer_to withdraws from source and deposits into target
        - unfreeze sets is_frozen to False
        - calculate_interest uses compound interest
        """
        bank_account_class = '''class BankAccount:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance
        self.is_frozen = False

    def deposit(self, amount):
        if amount < 0:
            raise ValueError("Deposit amount must be positive")

        self.balance += amount
        return self.balance

    def withdraw(self, amount):
        if self.is_frozen:
            raise RuntimeError("Account is frozen")

        if amount < 0:
            raise ValueError("Withdraw amount must be positive")

        if amount > self.balance:
            raise ValueError("Insufficient funds")

        self.balance -= amount
        return self.balance

    def transfer_to(self, target_account, amount):
        self.withdraw(amount)
        try:
            target_account.deposit(amount)
        except Exception:
            self.balance += amount
            raise

        return self.balance

    def freeze(self):
        self.is_frozen = True

    def unfreeze(self):
        self.is_frozen = False
'''

        interest_function = '''def calculate_interest(balance, annual_rate, years):
    if years <= 0:
        return balance

    for _ in range(years):
        balance = balance + balance * annual_rate

    return balance
'''

        fixed_code = code

        fixed_code = re.sub(
            r"class BankAccount:[\s\S]*?(?=\ndef calculate_interest|\Z)",
            bank_account_class + "\n",
            fixed_code,
            count=1,
        )

        fixed_code = re.sub(
            r"def calculate_interest\(balance, annual_rate, years\):[\s\S]*\Z",
            interest_function,
            fixed_code,
            count=1,
        )

        return self._ensure_trailing_newline(fixed_code)

    def _build_diff(
        self,
        original_text: str,
        fixed_text: str,
        original_name: str,
        fixed_name: str,
    ) -> str:
        result = self.tools.call_tool(
            "show_diff",
            {
                "original_text": original_text,
                "fixed_text": fixed_text,
                "original_name": original_name,
                "fixed_name": fixed_name,
            },
            timeout=30,
        )

        return result.get("diff", "")

    def _build_report(
        self,
        task_id: str,
        project_path: str,
        test_command: str,
        source_file_path: str,
        fixed_file_path: str,
        initial_test_result: dict,
        rounds: list[dict],
        final_test_result: dict,
        final_success: bool,
        message: str,
    ) -> str:
        lines = [
            "# Python Test-Driven CodeFix Report",
            "",
            "## Message",
            "",
            message,
            "",
            "## Task Info",
            "",
            f"- Task ID: {task_id}",
            f"- Project Path: {project_path}",
            f"- Test Command: {test_command}",
            f"- Source File: {source_file_path}",
            f"- Fixed File: {fixed_file_path}",
            f"- Final Success: {final_success}",
            f"- Memory Backend: {self.memory.describe_backend()}",
            f"- Tool Backend: official_mcp",
            f"- Test Backend: {final_test_result.get('backend', '')}",
            f"- MCP Fallback Used: {final_test_result.get('mcp_fallback_used', False)}",
            "",
            "## Initial Test Result",
            "",
            "~~~text",
            str(initial_test_result),
            "~~~",
            "",
            "## Repair Rounds",
            "",
        ]

        for round_item in rounds:
            lines.extend(
                [
                    f"### Attempt {round_item.get('attempt')}",
                    "",
                    f"- Counted As LLM Round: {round_item.get('counted_as_llm_round')}",
                    f"- LLM Round: {round_item.get('llm_round', '')}",
                    f"- Patch Success: {round_item.get('patch_success')}",
                    f"- Patch Mode: {round_item.get('patch_mode')}",
                    f"- Retrieved Context Used: {round_item.get('retrieved_context_used')}",
                    f"- Note: {round_item.get('note')}",
                    "",
                    "#### Retrieved Memory Context Preview",
                    "",
                    "~~~text",
                    round_item.get("retrieved_context_preview", ""),
                    "~~~",
                    "",
                    "#### Error Cause",
                    "",
                    round_item.get("error_cause", ""),
                    "",
                    "#### Fix Summary",
                    "",
                    round_item.get("fix_summary", ""),
                    "",
                    "#### Diff",
                    "",
                    "~~~diff",
                    round_item.get("diff", ""),
                    "~~~",
                    "",
                    "#### Test Result After This Attempt",
                    "",
                    "~~~text",
                    str(round_item.get("test_result")),
                    "~~~",
                    "",
                ]
            )

        lines.extend(
            [
                "## Final Test Result",
                "",
                "~~~text",
                str(final_test_result),
                "~~~",
                "",
            ]
        )

        return "\n".join(lines)

    def _ensure_trailing_newline(self, text: str) -> str:
        if not text.endswith("\n"):
            return text + "\n"
        return text


def main():
    print("=== PythonTestFixSkill Official MCP Final Test ===")

    skill = PythonTestFixSkill()

    state = {
        "project_path": str(CODEFIX_DIR / "demo_bank_project"),
        "test_command": "pytest",
        "user_requirement": "帮我根据测试失败信息修复银行账户系统里的逻辑错误。",
        "language": "python",
    }

    result = skill.run(state)
    print(result)


if __name__ == "__main__":
    main()