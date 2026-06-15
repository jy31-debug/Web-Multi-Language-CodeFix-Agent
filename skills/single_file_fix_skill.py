from pathlib import Path
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


class SingleFileFixSkill(BaseFixSkill):
    name = "SingleFileFixSkill"
    skill_name = "SingleFileFixSkill"

    def __init__(self):
        self.memory = MemoryManager()
        self.tools = OfficialMCPClient()
        self.trace_path: Path | None = None

    def run(self, task_state: dict) -> SkillResult:
        source_file_path = task_state.get("source_file_path", "")
        user_requirement = task_state.get("user_requirement", "")
        language = task_state.get("language", "")

        if not source_file_path:
            return SkillResult(
                success=False,
                skill_name=self.name,
                message="No source_file_path was provided.",
                data={
                    "fixed_file_path": "",
                    "report_path": "",
                    "trace_path": "",
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        source_file = Path(source_file_path).resolve()

        if not source_file.exists():
            return SkillResult(
                success=False,
                skill_name=self.name,
                message=f"Source file does not exist: {source_file}",
                data={
                    "fixed_file_path": "",
                    "report_path": "",
                    "trace_path": "",
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        task_dir = self._infer_task_dir(source_file)

        uploaded_dir = task_dir / "uploaded"
        project_dir = task_dir / "project"
        error_log_dir = task_dir / "error_logs"
        report_dir = task_dir / "reports"
        trace_dir = task_dir / "traces"
        output_dir = task_dir / "outputs"

        for directory in [
            uploaded_dir,
            project_dir,
            error_log_dir,
            report_dir,
            trace_dir,
            output_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        task_id = task_dir.name
        fixed_file_path = output_dir / f"fixed_{source_file.name}"
        report_path = report_dir / "single_file_repair_report.md"
        self.trace_path = trace_dir / "single_file_repair_trace.txt"
        self.trace_path.write_text("", encoding="utf-8")

        self._trace("SingleFileFixSkill started")
        self._trace(f"task_id: {task_id}")
        self._trace(f"source_file: {source_file}")
        self._trace(f"language: {language}")
        self._trace(f"user_requirement: {user_requirement}")
        self._trace(f"memory_backend: {self.memory.describe_backend()}")
        self._trace("tool_backend: official_mcp")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "start",
                "source_file_path": str(source_file),
                "user_requirement": user_requirement,
                "language": language,
                "tool_backend": "official_mcp",
            },
        )

        read_result = self.tools.call_tool(
            "read_file",
            {
                "path": str(source_file),
            },
            timeout=30,
        )

        if not read_result.get("success"):
            message = read_result.get("error", "Failed to read source file.")
            self._trace(f"read_file failed: {message}")

            return SkillResult(
                success=False,
                skill_name=self.name,
                message=message,
                data={
                    "task_id": task_id,
                    "source_file_path": str(source_file),
                    "fixed_file_path": "",
                    "report_path": "",
                    "trace_path": str(self.trace_path),
                    "diff": "",
                    "tool_backend": "official_mcp",
                },
            )

        original_code = read_result.get("content", "")

        self._trace(f"source code length: {len(original_code)}")

        memory_query = "\n".join(
            [
                user_requirement,
                language,
                source_file.name,
                original_code[:2000],
            ]
        )

        retrieved_context = self.memory.build_retrieved_context(
            query=memory_query,
            top_k=3,
        )

        self._trace(f"retrieved_context_used: {bool(retrieved_context)}")
        self._trace(f"retrieved_context_length: {len(retrieved_context)}")

        error_context = (
            "This is a single-file repair task.\n"
            "There is no pytest log in this route.\n"
            "Fix the source file according to the user requirement.\n"
            "Return the complete corrected source code.\n"
        )

        self._trace("Calling generate_code_patch through official MCP")

        patch_result = self.tools.call_tool(
            "generate_code_patch",
            {
                "language": language or self._guess_language_from_suffix(source_file),
                "source_code": original_code,
                "user_requirement": user_requirement,
                "error_context": error_context,
                "retrieved_context": retrieved_context,
            },
            timeout=120,
        )

        self._trace(f"patch_result_success: {patch_result.get('success')}")
        self._trace(f"patch_result_mode: {patch_result.get('mode', '')}")

        if not patch_result.get("success"):
            message = patch_result.get("error", "Patch generation failed.")

            report = self._build_report(
                task_id=task_id,
                source_file_path=str(source_file),
                fixed_file_path="",
                language=language,
                user_requirement=user_requirement,
                patch_result=patch_result,
                diff_text="",
                success=False,
                message=message,
            )

            report_path.write_text(report, encoding="utf-8")

            self.memory.remember_short_term(
                task_id,
                {
                    "skill_name": self.name,
                    "stage": "failed",
                    "reason": message,
                    "tool_backend": "official_mcp",
                },
            )

            return SkillResult(
                success=False,
                skill_name=self.name,
                message=message,
                data={
                    "task_id": task_id,
                    "source_file_path": str(source_file),
                    "fixed_file_path": "",
                    "report_path": str(report_path),
                    "trace_path": str(self.trace_path),
                    "diff": "",
                    "memory_backend": self.memory.describe_backend(),
                    "tool_backend": "official_mcp",
                },
            )

        fixed_code = patch_result.get("fixed_code", original_code)
        fixed_code = self._ensure_trailing_newline(fixed_code)

        self._trace(f"fixed code length: {len(fixed_code)}")

        diff_result = self.tools.call_tool(
            "show_diff",
            {
                "original_text": original_code,
                "fixed_text": fixed_code,
                "original_name": source_file.name,
                "fixed_name": f"fixed_{source_file.name}",
            },
            timeout=30,
        )

        diff_text = diff_result.get("diff", "")

        self._trace(f"diff length: {len(diff_text)}")

        write_result = self.tools.call_tool(
            "write_file",
            {
                "path": str(fixed_file_path),
                "content": fixed_code,
            },
            timeout=30,
        )

        if not write_result.get("success"):
            message = write_result.get("error", "Failed to write fixed file.")
            self._trace(f"write_file failed: {message}")

            return SkillResult(
                success=False,
                skill_name=self.name,
                message=message,
                data={
                    "task_id": task_id,
                    "source_file_path": str(source_file),
                    "fixed_file_path": "",
                    "report_path": "",
                    "trace_path": str(self.trace_path),
                    "diff": diff_text,
                    "memory_backend": self.memory.describe_backend(),
                    "tool_backend": "official_mcp",
                },
            )

        self._trace(f"fixed file saved: {fixed_file_path}")

        report = self._build_report(
            task_id=task_id,
            source_file_path=str(source_file),
            fixed_file_path=str(fixed_file_path),
            language=language,
            user_requirement=user_requirement,
            patch_result=patch_result,
            diff_text=diff_text,
            success=True,
            message="Single-file repair finished.",
        )

        save_report_result = self.tools.call_tool(
            "save_report",
            {
                "path": str(report_path),
                "title": "Single File CodeFix Report",
                "content": report,
            },
            timeout=30,
        )

        if not save_report_result.get("success"):
            report_path.write_text(report, encoding="utf-8")

        self._trace(f"report saved: {report_path}")

        self.memory.remember_episodic(
            {
                "skill_name": self.name,
                "language": language,
                "user_requirement": user_requirement,
                "source_file_path": str(source_file),
                "fix_summary": patch_result.get("fix_summary", ""),
                "error_cause": patch_result.get("error_cause", ""),
                "success": True,
                "diff_preview": diff_text[:2000],
                "tool_backend": "official_mcp",
            }
        )

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "finished",
                "source_file_path": str(source_file),
                "fixed_file_path": str(fixed_file_path),
                "report_path": str(report_path),
                "trace_path": str(self.trace_path),
                "success": True,
                "tool_backend": "official_mcp",
            },
        )

        self._trace("SingleFileFixSkill finished")

        return SkillResult(
            success=True,
            skill_name=self.name,
            message="Single-file repair finished.",
            data={
                "task_id": task_id,
                "source_file_path": str(source_file),
                "fixed_file_path": str(fixed_file_path),
                "report_path": str(report_path),
                "trace_path": str(self.trace_path),
                "diff": diff_text,
                "memory_backend": self.memory.describe_backend(),
                "tool_backend": "official_mcp",
            },
        )

    def _infer_task_dir(self, source_file: Path) -> Path:
        parts = list(source_file.parts)

        for index, part in enumerate(parts):
            if part.startswith("task_"):
                return Path(*parts[: index + 1])

        if source_file.parent.name in {"uploaded", "project"}:
            return source_file.parent.parent

        return source_file.parent

    def _guess_language_from_suffix(self, source_file: Path) -> str:
        suffix = source_file.suffix.lower()

        if suffix == ".py":
            return "python"

        if suffix == ".java":
            return "java"

        if suffix in {".c", ".h"}:
            return "c"

        if suffix in {".js", ".jsx"}:
            return "javascript"

        if suffix in {".ts", ".tsx"}:
            return "typescript"

        return "unknown"

    def _build_report(
        self,
        task_id: str,
        source_file_path: str,
        fixed_file_path: str,
        language: str,
        user_requirement: str,
        patch_result: dict,
        diff_text: str,
        success: bool,
        message: str,
    ) -> str:
        lines = [
            "## Message",
            "",
            message,
            "",
            "## Task Info",
            "",
            f"- Task ID: {task_id}",
            f"- Source File: {source_file_path}",
            f"- Fixed File: {fixed_file_path}",
            f"- Language: {language}",
            f"- Success: {success}",
            f"- Memory Backend: {self.memory.describe_backend()}",
            f"- Tool Backend: official_mcp",
            "",
            "## User Requirement",
            "",
            user_requirement,
            "",
            "## Error Cause",
            "",
            patch_result.get("error_cause", ""),
            "",
            "## Fix Summary",
            "",
            patch_result.get("fix_summary", ""),
            "",
            "## Diff",
            "",
            "~~~diff",
            diff_text,
            "~~~",
            "",
        ]

        return "\n".join(lines)

    def _trace(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"

        print(f"[SingleFileFixSkill] {message}", flush=True)

        if self.trace_path:
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _ensure_trailing_newline(self, text: str) -> str:
        if not text.endswith("\n"):
            return text + "\n"
        return text


def main():
    print("=== SingleFileFixSkill Official MCP Test ===")

    skill = SingleFileFixSkill()

    state = {
        "source_file_path": str(CODEFIX_DIR / "demo_single_file.py"),
        "user_requirement": "Fix the bug in this single Python file.",
        "language": "python",
    }

    result = skill.run(state)
    print(result)


if __name__ == "__main__":
    main()