from pathlib import Path
import difflib
import inspect
import sys
import zipfile


CURRENT_DIR = Path(__file__).resolve().parent
CODEFIX_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

if str(CODEFIX_DIR) not in sys.path:
    sys.path.insert(0, str(CODEFIX_DIR))

from base_skill import BaseFixSkill, SkillResult
from task_manager import create_task, get_report_path, get_output_path
from llm_patch_generator import generate_patch


class ProjectStaticFixSkill(BaseFixSkill):
    name = "ProjectStaticFixSkill"

    def run(self, task_state: dict) -> SkillResult:
        project_path = task_state.get("project_path", "")
        user_requirement = task_state.get("user_requirement", "")
        language = task_state.get("language", "unknown")

        task_info = create_task()
        report_path = get_report_path(task_info, "project_static_fix_report.md")

        if not project_path:
            return SkillResult(
                success=False,
                skill_name=self.name,
                message="No project_path was provided for ProjectStaticFixSkill.",
                data={
                    "report_path": "",
                    "fixed_file_path": "",
                    "fixed_zip_path": "",
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
                    "fixed_zip_path": "",
                    "diff": "",
                },
            )

        code_files = self._find_code_files(project_dir)

        if not code_files:
            report = self._build_report(
                task_info=task_info,
                project_path=str(project_dir),
                user_requirement=user_requirement,
                language=language,
                file_results=[],
                fixed_zip_path="",
                message="No supported source code files were found in the uploaded project.",
            )
            Path(report_path).write_text(report, encoding="utf-8")

            return SkillResult(
                success=False,
                skill_name=self.name,
                message="No supported source code files were found.",
                data={
                    "task_id": task_info["task_id"],
                    "project_path": str(project_dir),
                    "report_path": report_path,
                    "fixed_file_path": "",
                    "fixed_zip_path": "",
                    "diff": "",
                },
            )

        fixed_files_dir = Path(get_output_path(task_info, "fixed_project_files"))
        fixed_files_dir.mkdir(parents=True, exist_ok=True)

        file_results = []
        all_diff = []

        max_files = 20
        selected_files = code_files[:max_files]

        for source_file in selected_files:
            file_language = self._detect_language_by_suffix(source_file)
            original_code = source_file.read_text(encoding="utf-8", errors="ignore")

            file_requirement = user_requirement.strip()
            if not file_requirement:
                file_requirement = (
                    "Please inspect this source code file, find obvious bugs, "
                    "syntax issues, or logic problems, and return a corrected full version if needed."
                )

            patch_result = self._call_generate_patch(
                language=file_language,
                source_code=original_code,
                user_requirement=file_requirement,
                error_context=(
                    "No test command was provided. "
                    "This is a static project repair task. "
                    "Only inspect and repair this source file. "
                    "Do not invent unrelated business rules."
                ),
                retrieved_context="",
            )

            fixed_code = patch_result.get("fixed_code", original_code)
            fixed_code = self._ensure_trailing_newline(fixed_code)

            relative_name = source_file.relative_to(project_dir)
            fixed_file_path = fixed_files_dir / relative_name
            fixed_file_path.parent.mkdir(parents=True, exist_ok=True)
            fixed_file_path.write_text(fixed_code, encoding="utf-8")

            safe_name = str(relative_name).replace("\\", "__").replace("/", "__")
            flat_fixed_file_path = get_output_path(task_info, f"fixed_{safe_name}")
            Path(flat_fixed_file_path).write_text(fixed_code, encoding="utf-8")

            diff_text = self._build_diff(
                original_text=original_code,
                fixed_text=fixed_code,
                original_name=str(relative_name),
                fixed_name=f"fixed/{relative_name}",
            )

            all_diff.append(diff_text)

            file_results.append(
                {
                    "source_file": str(source_file),
                    "relative_file": str(relative_name),
                    "language": file_language,
                    "fixed_file_path": str(fixed_file_path),
                    "flat_fixed_file_path": flat_fixed_file_path,
                    "success": patch_result.get("success"),
                    "mode": patch_result.get("mode"),
                    "error_cause": patch_result.get("error_cause", ""),
                    "fix_summary": patch_result.get("fix_summary", ""),
                    "diff": diff_text,
                }
            )

        final_diff = "\n\n".join(all_diff)
        fixed_zip_path = get_output_path(task_info, "fixed_project_files.zip")
        self._zip_directory(fixed_files_dir, Path(fixed_zip_path))

        report = self._build_report(
            task_info=task_info,
            project_path=str(project_dir),
            user_requirement=user_requirement,
            language=language,
            file_results=file_results,
            fixed_zip_path=fixed_zip_path,
            message="Project static repair finished.",
        )

        Path(report_path).write_text(report, encoding="utf-8")

        first_fixed_file = file_results[0]["flat_fixed_file_path"] if file_results else ""

        return SkillResult(
            success=True,
            skill_name=self.name,
            message="Project static repair finished.",
            data={
                "task_id": task_info["task_id"],
                "project_path": str(project_dir),
                "processed_file_count": len(file_results),
                "report_path": report_path,
                "fixed_file_path": first_fixed_file,
                "fixed_zip_path": fixed_zip_path,
                "diff": final_diff,
                "file_results": file_results,
            },
        )

    def _find_code_files(self, project_dir: Path) -> list[Path]:
        supported_suffixes = {
            ".py",
            ".java",
            ".c",
            ".h",
            ".cpp",
            ".hpp",
            ".js",
            ".ts",
        }

        ignored_parts = {
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            "tests",
            "test",
        }

        files = []

        for path in project_dir.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in supported_suffixes:
                continue

            lower_parts = {part.lower() for part in path.parts}

            if lower_parts.intersection(ignored_parts):
                continue

            lower_name = path.name.lower()

            if lower_name.startswith("test_"):
                continue

            if lower_name.endswith("_test.py"):
                continue

            if lower_name.endswith(".test.js"):
                continue

            files.append(path)

        return sorted(files)

    def _detect_language_by_suffix(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return "python"

        if suffix == ".java":
            return "java"

        if suffix in [".c", ".h"]:
            return "c"

        if suffix in [".cpp", ".hpp"]:
            return "cpp"

        if suffix == ".js":
            return "javascript"

        if suffix == ".ts":
            return "typescript"

        return "unknown"

    def _call_generate_patch(
        self,
        language: str,
        source_code: str,
        user_requirement: str,
        error_context: str,
        retrieved_context: str,
    ) -> dict:
        signature = inspect.signature(generate_patch)
        supported_params = set(signature.parameters.keys())

        kwargs = {}

        if "language" in supported_params:
            kwargs["language"] = language

        if "source_code" in supported_params:
            kwargs["source_code"] = source_code

        if "user_requirement" in supported_params:
            kwargs["user_requirement"] = user_requirement

        if "error_context" in supported_params:
            kwargs["error_context"] = error_context
        elif "error_log" in supported_params:
            kwargs["error_log"] = error_context
        elif "error_message" in supported_params:
            kwargs["error_message"] = error_context
        elif "test_error" in supported_params:
            kwargs["test_error"] = error_context

        if "retrieved_context" in supported_params:
            kwargs["retrieved_context"] = retrieved_context
        elif "context" in supported_params:
            kwargs["context"] = retrieved_context
        elif "repair_context" in supported_params:
            kwargs["repair_context"] = retrieved_context

        return generate_patch(**kwargs)

    def _build_diff(
        self,
        original_text: str,
        fixed_text: str,
        original_name: str,
        fixed_name: str,
    ) -> str:
        diff = difflib.unified_diff(
            original_text.splitlines(keepends=True),
            fixed_text.splitlines(keepends=True),
            fromfile=original_name,
            tofile=fixed_name,
        )

        return "".join(diff)

    def _build_report(
        self,
        task_info: dict,
        project_path: str,
        user_requirement: str,
        language: str,
        file_results: list[dict],
        fixed_zip_path: str,
        message: str,
    ) -> str:
        lines = [
            "# Project Static CodeFix Report",
            "",
            "## Message",
            "",
            message,
            "",
            "## Task Info",
            "",
            f"- Task ID: {task_info['task_id']}",
            f"- Project Path: {project_path}",
            f"- Language: {language}",
            f"- User Requirement: {user_requirement}",
            f"- Processed File Count: {len(file_results)}",
            f"- Fixed Project Zip: {fixed_zip_path}",
            "",
            "## File Results",
            "",
        ]

        for index, item in enumerate(file_results, start=1):
            lines.extend(
                [
                    f"### File {index}: {item['relative_file']}",
                    "",
                    f"- Language: {item['language']}",
                    f"- Success: {item['success']}",
                    f"- Mode: {item['mode']}",
                    f"- Fixed File: {item['fixed_file_path']}",
                    "",
                    "#### Error Cause",
                    "",
                    item.get("error_cause", ""),
                    "",
                    "#### Fix Summary",
                    "",
                    item.get("fix_summary", ""),
                    "",
                    "#### Diff",
                    "",
                    "~~~diff",
                    item.get("diff", ""),
                    "~~~",
                    "",
                ]
            )

        return "\n".join(lines)

    def _zip_directory(self, source_dir: Path, zip_path: Path) -> None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname)

    def _ensure_trailing_newline(self, text: str) -> str:
        if not text.endswith("\n"):
            return text + "\n"
        return text


def main():
    print("=== ProjectStaticFixSkill Test ===")

    skill = ProjectStaticFixSkill()

    state = {
        "project_path": str(CODEFIX_DIR / "demo_order_project"),
        "test_command": "",
        "user_requirement": "帮我检查这个订单管理项目里的代码问题，并修复明显的逻辑错误。不要修改测试文件，只修复业务代码。",
        "language": "python",
    }

    result = skill.run(state)
    print(result)


if __name__ == "__main__":
    main()