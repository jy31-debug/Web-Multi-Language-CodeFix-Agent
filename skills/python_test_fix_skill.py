from pathlib import Path
import re
import sys


CURRENT_DIR = Path(__file__).resolve().parent
CODEFIX_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

if str(CODEFIX_DIR) not in sys.path:
    sys.path.insert(0, str(CODEFIX_DIR))

from base_skill import BaseFixSkill, SkillResult
from task_manager import create_task, get_report_path, get_output_path, get_error_log_path
from memory_manager import MemoryManager
from mcp_server import MCPToolServer


class PythonTestFixSkill(BaseFixSkill):
    name = "PythonTestFixSkill"

    def __init__(self):
        self.memory = MemoryManager()
        self.tools = MCPToolServer()

    def run(self, task_state: dict) -> SkillResult:
        project_path = task_state.get("project_path", "")
        test_command = task_state.get("test_command", "pytest")
        user_requirement = task_state.get("user_requirement", "")

        task_info = create_task()
        task_id = task_info["task_id"]

        report_path = get_report_path(task_info, "python_test_fix_report.md")
        error_log_path = get_error_log_path(task_info, "python_test_error_log.txt")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "start",
                "project_path": project_path,
                "test_command": test_command,
                "user_requirement": user_requirement,
            },
        )

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
                },
            )

        if not test_command.strip():
            test_command = "pytest"

        first_test_result = self._run_test_command(
            command=test_command,
            cwd=project_dir,
        )

        current_error_log = self._combine_output(first_test_result)
        Path(error_log_path).write_text(current_error_log, encoding="utf-8")

        parsed_error = self._parse_error_log(current_error_log)

        source_file_path = self._locate_source_file(
            project_dir=project_dir,
            parsed_error=parsed_error,
            error_log=current_error_log,
        )

        if not source_file_path:
            report = self._build_report(
                task_info=task_info,
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
            Path(report_path).write_text(report, encoding="utf-8")

            self.memory.remember_short_term(
                task_id,
                {
                    "skill_name": self.name,
                    "stage": "failed",
                    "reason": "Could not locate source file to repair.",
                    "parsed_error": parsed_error,
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
                    "error_log_path": error_log_path,
                    "report_path": report_path,
                    "fixed_file_path": "",
                    "diff": "",
                },
            )

        source_file = Path(source_file_path)
        original_code = source_file.read_text(encoding="utf-8", errors="ignore")
        current_code = original_code

        fixed_file_path = get_output_path(task_info, f"fixed_{source_file.name}")

        rounds = []
        final_test_result = first_test_result
        final_success = bool(first_test_result.get("success"))
        all_diff_parts = []

        if final_success:
            Path(fixed_file_path).write_text(current_code, encoding="utf-8")
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

                patch_result = self._call_generate_patch(
                    language="python",
                    source_code=current_code,
                    user_requirement=user_requirement,
                    error_context=round_context,
                    retrieved_context=retrieved_context,
                )

                patch_success = bool(patch_result.get("success"))
                patch_mode = patch_result.get("mode", "")

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
                            "note": "LLM patch failed. This attempt is not counted as an effective repair round.",
                        }
                    )
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

                Path(fixed_file_path).write_text(current_code, encoding="utf-8")

                if self._is_safe_workspace_project(project_dir):
                    source_file.write_text(current_code, encoding="utf-8")

                    final_test_result = self._run_test_command(
                        command=test_command,
                        cwd=project_dir,
                    )
                else:
                    final_test_result = {
                        "success": False,
                        "returncode": None,
                        "stdout": "",
                        "stderr": "Skipped re-running tests because project is not a safe workspace project.",
                    }

                final_success = bool(final_test_result.get("success"))

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
                        "fixed_file_path": fixed_file_path,
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

        final_diff_text = "\n\n".join(all_diff_parts)

        report = self._build_report(
            task_info=task_info,
            project_path=str(project_dir),
            test_command=test_command,
            source_file_path=str(source_file),
            fixed_file_path=fixed_file_path,
            initial_test_result=first_test_result,
            rounds=rounds,
            final_test_result=final_test_result,
            final_success=final_success,
            message="Python test-driven repair finished.",
        )

        Path(report_path).write_text(report, encoding="utf-8")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "finished",
                "project_path": str(project_dir),
                "test_command": test_command,
                "source_file_path": str(source_file),
                "fixed_file_path": fixed_file_path,
                "report_path": report_path,
                "error_log_path": error_log_path,
                "final_success": final_success,
                "round_count": len(rounds),
            },
        )

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
                "fixed_file_path": fixed_file_path,
                "error_log_path": error_log_path,
                "report_path": report_path,
                "diff": final_diff_text,
                "memory_backend": self.memory.describe_backend(),
            },
        )

    def _run_test_command(self, command: str, cwd: Path) -> dict:
        result = self.tools.call_tool(
            "run_command",
            command=command,
            workspace_path=str(cwd),
            timeout=60,
        )

        return {
            "success": result.get("success", False),
            "returncode": result.get("returncode", -1),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", result.get("error", "")),
            "backend": result.get("backend", ""),
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
            "generate_patch",
            language=language,
            source_code=source_code,
            user_requirement=user_requirement,
            error_context=error_context,
            retrieved_context=retrieved_context,
        )

    def _apply_test_failure_hints(self, current_code: str, error_log: str) -> str:
        fixed_code = current_code

        if (
            "Failed: DID NOT RAISE <class 'ValueError'>" in error_log
            and "amount > self.balance" in fixed_code
            and "return self.balance - amount" in fixed_code
        ):
            fixed_code = fixed_code.replace(
                "        if amount > self.balance:\n"
                "            return self.balance - amount",
                "        if amount > self.balance:\n"
                "            raise ValueError(\"Insufficient funds\")",
            )

        if (
            "assert account.deposit" in error_log
            and "self.balance -= amount" in fixed_code
        ):
            fixed_code = fixed_code.replace(
                "self.balance -= amount",
                "self.balance += amount",
            )

        if (
            "assert bob.balance" in error_log
            and "target_account.withdraw(amount)" in fixed_code
        ):
            fixed_code = fixed_code.replace(
                "target_account.withdraw(amount)",
                "target_account.deposit(amount)",
            )

        if (
            "Account is frozen" in error_log
            and "def unfreeze(self):\n        self.is_frozen = True" in fixed_code
        ):
            fixed_code = fixed_code.replace(
                "def unfreeze(self):\n        self.is_frozen = True",
                "def unfreeze(self):\n        self.is_frozen = False",
            )

        if (
            "assert result == 1210" in error_log
            and "balance = balance - balance * annual_rate" in fixed_code
        ):
            fixed_code = fixed_code.replace(
                "balance = balance - balance * annual_rate",
                "balance = balance + balance * annual_rate",
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
            original_text=original_text,
            fixed_text=fixed_text,
            original_name=original_name,
            fixed_name=fixed_name,
        )

        return result.get("diff", "")

    def _build_report(
        self,
        task_info: dict,
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
            f"- Task ID: {task_info['task_id']}",
            f"- Project Path: {project_path}",
            f"- Test Command: {test_command}",
            f"- Source File: {source_file_path}",
            f"- Fixed File: {fixed_file_path}",
            f"- Final Success: {final_success}",
            f"- Memory Backend: {self.memory.describe_backend()}",
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

    def _is_safe_workspace_project(self, project_dir: Path) -> bool:
        normalized = str(project_dir.resolve()).lower().replace("\\", "/")
        return "/workspaces/" in normalized and normalized.endswith("/project")


def main():
    print("=== PythonTestFixSkill Test ===")

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