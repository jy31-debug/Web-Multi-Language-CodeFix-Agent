from pathlib import Path
import sys
import zipfile
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


class ProjectStaticFixSkill(BaseFixSkill):
    name = "ProjectStaticFixSkill"
    skill_name = "ProjectStaticFixSkill"

    def __init__(self):
        self.memory = MemoryManager()
        self.tools = OfficialMCPClient()
        self.trace_path: Path | None = None

    def run(self, task_state: dict) -> SkillResult:
        project_path = task_state.get("project_path", "")
        user_requirement = task_state.get("user_requirement", "")
        language = task_state.get("language", "")

        if not project_path:
            return SkillResult(
                success=False,
                skill_name=self.name,
                message="No project_path was provided.",
                data={
                    "report_path": "",
                    "trace_path": "",
                    "fixed_files": [],
                    "fixed_file_path": "",
                    "fixed_files_zip_path": "",
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
                    "trace_path": "",
                    "fixed_files": [],
                    "fixed_file_path": "",
                    "fixed_files_zip_path": "",
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

        report_path = report_dir / "project_static_fix_report.md"
        self.trace_path = trace_dir / "project_static_fix_trace.txt"
        self.trace_path.write_text("", encoding="utf-8")

        project_requirement = self._read_project_requirement(project_dir)

        self._trace("ProjectStaticFixSkill started")
        self._trace(f"task_id: {task_id}")
        self._trace(f"project_dir: {project_dir}")
        self._trace(f"detected_language_from_router: {language}")
        self._trace(f"user_requirement: {user_requirement}")
        self._trace(f"project_requirement_length: {len(project_requirement)}")
        self._trace(f"memory_backend: {self.memory.describe_backend()}")
        self._trace("tool_backend: official_mcp")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "start",
                "project_path": str(project_dir),
                "user_requirement": user_requirement,
                "language": language,
                "tool_backend": "official_mcp",
            },
        )

        source_files = self._select_source_files(
            project_dir=project_dir,
            max_files=20,
        )

        self._trace(f"selected source files: {[str(p) for p in source_files]}")

        if not source_files:
            message = "No source files were found for static project repair."

            report = self._build_report(
                task_id=task_id,
                project_path=str(project_dir),
                language=language,
                user_requirement=user_requirement,
                project_requirement=project_requirement,
                file_results=[],
                success=False,
                message=message,
            )

            report_path.write_text(report, encoding="utf-8")

            return SkillResult(
                success=False,
                skill_name=self.name,
                message=message,
                data={
                    "task_id": task_id,
                    "project_path": str(project_dir),
                    "report_path": str(report_path),
                    "trace_path": str(self.trace_path),
                    "fixed_files": [],
                    "fixed_file_path": "",
                    "fixed_files_zip_path": "",
                    "diff": "",
                    "memory_backend": self.memory.describe_backend(),
                    "tool_backend": "official_mcp",
                },
            )

        file_results = []
        all_diffs = []
        fixed_files = []

        for source_file in source_files:
            self._trace("=" * 80)
            self._trace(f"Repairing file: {source_file}")

            detected_language = self._guess_language_from_suffix(source_file)
            self._trace(f"file_language: {detected_language}")

            read_result = self.tools.call_tool(
                "read_file",
                {
                    "path": str(source_file),
                },
                timeout=30,
            )

            if not read_result.get("success"):
                error_message = read_result.get("error", "Failed to read file.")
                self._trace(f"read_file failed: {error_message}")

                file_results.append(
                    {
                        "source_file": str(source_file),
                        "fixed_file": "",
                        "language": detected_language,
                        "success": False,
                        "error": error_message,
                        "error_cause": "",
                        "fix_summary": "",
                        "diff": "",
                        "retrieved_context_used": False,
                    }
                )
                continue

            original_code = read_result.get("content", "")

            memory_query = "\n".join(
                [
                    user_requirement,
                    project_requirement,
                    detected_language,
                    source_file.name,
                    original_code[:2500],
                ]
            )

            retrieved_context = self.memory.build_retrieved_context(
                query=memory_query,
                top_k=3,
            )

            self._trace(f"retrieved_context_used: {bool(retrieved_context)}")
            self._trace(f"retrieved_context_length: {len(retrieved_context)}")

            error_context = self._build_error_context(
                project_requirement=project_requirement,
                source_file=source_file,
                detected_language=detected_language,
            )

            self._trace("Calling generate_code_patch through official MCP")

            patch_result = self.tools.call_tool(
                "generate_code_patch",
                {
                    "language": detected_language,
                    "source_code": original_code,
                    "user_requirement": user_requirement,
                    "error_context": error_context,
                    "retrieved_context": retrieved_context,
                },
                timeout=120,
            )

            patch_success = bool(patch_result.get("success"))
            self._trace(f"patch_success: {patch_success}")
            self._trace(f"patch_mode: {patch_result.get('mode', '')}")

            if not patch_success:
                error_message = patch_result.get("error", "Patch generation failed.")

                file_results.append(
                    {
                        "source_file": str(source_file),
                        "fixed_file": "",
                        "language": detected_language,
                        "success": False,
                        "error": error_message,
                        "error_cause": patch_result.get("error_cause", ""),
                        "fix_summary": patch_result.get("fix_summary", ""),
                        "diff": "",
                        "retrieved_context_used": bool(retrieved_context),
                    }
                )
                continue

            fixed_code = patch_result.get("fixed_code", original_code)
            fixed_code = self._ensure_trailing_newline(fixed_code)

            diff_result = self.tools.call_tool(
                "show_diff",
                {
                    "original_text": original_code,
                    "fixed_text": fixed_code,
                    "original_name": str(source_file.relative_to(project_dir)),
                    "fixed_name": f"fixed_{source_file.name}",
                },
                timeout=30,
            )

            diff_text = diff_result.get("diff", "")

            relative_name = self._safe_relative_output_name(
                project_dir=project_dir,
                source_file=source_file,
            )
            fixed_file_path = output_dir / f"fixed_{relative_name}"

            write_output_result = self.tools.call_tool(
                "write_file",
                {
                    "path": str(fixed_file_path),
                    "content": fixed_code,
                },
                timeout=30,
            )

            if not write_output_result.get("success"):
                error_message = write_output_result.get("error", "Failed to write fixed output file.")
                self._trace(f"write fixed output failed: {error_message}")

                file_results.append(
                    {
                        "source_file": str(source_file),
                        "fixed_file": "",
                        "language": detected_language,
                        "success": False,
                        "error": error_message,
                        "error_cause": patch_result.get("error_cause", ""),
                        "fix_summary": patch_result.get("fix_summary", ""),
                        "diff": diff_text,
                        "retrieved_context_used": bool(retrieved_context),
                    }
                )
                continue

            write_back_result = self.tools.call_tool(
                "write_file",
                {
                    "path": str(source_file),
                    "content": fixed_code,
                },
                timeout=30,
            )

            if not write_back_result.get("success"):
                error_message = write_back_result.get("error", "Failed to write fixed code back to project.")
                self._trace(f"write back failed: {error_message}")

                file_results.append(
                    {
                        "source_file": str(source_file),
                        "fixed_file": str(fixed_file_path),
                        "language": detected_language,
                        "success": False,
                        "error": error_message,
                        "error_cause": patch_result.get("error_cause", ""),
                        "fix_summary": patch_result.get("fix_summary", ""),
                        "diff": diff_text,
                        "retrieved_context_used": bool(retrieved_context),
                    }
                )
                continue

            self._trace(f"fixed output saved: {fixed_file_path}")
            self._trace(f"fixed code written back to project file: {source_file}")

            all_diffs.append(diff_text)
            fixed_files.append(str(fixed_file_path))

            file_result = {
                "source_file": str(source_file),
                "fixed_file": str(fixed_file_path),
                "language": detected_language,
                "success": True,
                "error": "",
                "error_cause": patch_result.get("error_cause", ""),
                "fix_summary": patch_result.get("fix_summary", ""),
                "diff": diff_text,
                "retrieved_context_used": bool(retrieved_context),
            }

            file_results.append(file_result)

            self.memory.remember_episodic(
                {
                    "skill_name": self.name,
                    "language": detected_language,
                    "user_requirement": user_requirement,
                    "project_requirement": project_requirement[:2000],
                    "source_file_path": str(source_file),
                    "fix_summary": patch_result.get("fix_summary", ""),
                    "error_cause": patch_result.get("error_cause", ""),
                    "success": True,
                    "diff_preview": diff_text[:2000],
                    "tool_backend": "official_mcp",
                }
            )

        final_success = any(item.get("success") for item in file_results)

        if final_success:
            message = "Project static repair finished."
        else:
            message = "Project static repair failed."

        self._trace(f"final_success: {final_success}")
        self._trace(message)

        report = self._build_report(
            task_id=task_id,
            project_path=str(project_dir),
            language=language,
            user_requirement=user_requirement,
            project_requirement=project_requirement,
            file_results=file_results,
            success=final_success,
            message=message,
        )

        save_report_result = self.tools.call_tool(
            "save_report",
            {
                "path": str(report_path),
                "title": "Project Static CodeFix Report",
                "content": report,
            },
            timeout=30,
        )

        if not save_report_result.get("success"):
            report_path.write_text(report, encoding="utf-8")

        self._trace(f"report saved: {report_path}")

        fixed_files_zip_path = ""

        if fixed_files:
            fixed_files_zip_path = self._package_fixed_files(
                output_dir=output_dir,
                fixed_files=fixed_files,
            )
            self._trace(f"fixed files zip saved: {fixed_files_zip_path}")

        self.memory.remember_short_term(
            task_id,
            {
                "skill_name": self.name,
                "stage": "finished",
                "project_path": str(project_dir),
                "report_path": str(report_path),
                "trace_path": str(self.trace_path),
                "success": final_success,
                "fixed_files": fixed_files,
                "fixed_files_zip_path": fixed_files_zip_path,
                "tool_backend": "official_mcp",
            },
        )

        return SkillResult(
            success=final_success,
            skill_name=self.name,
            message=message,
            data={
                "task_id": task_id,
                "project_path": str(project_dir),
                "report_path": str(report_path),
                "trace_path": str(self.trace_path),
                "fixed_files": fixed_files,
                "fixed_file_path": fixed_files_zip_path or (fixed_files[0] if fixed_files else ""),
                "fixed_files_zip_path": fixed_files_zip_path,
                "diff": "\n\n".join(all_diffs),
                "memory_backend": self.memory.describe_backend(),
                "tool_backend": "official_mcp",
                "file_results": file_results,
            },
        )

    def _infer_task_dir(self, project_dir: Path) -> Path:
        if project_dir.name == "project":
            return project_dir.parent

        parts = list(project_dir.parts)

        for index, part in enumerate(parts):
            if part.startswith("task_"):
                return Path(*parts[: index + 1])

        return project_dir

    def _read_project_requirement(self, project_dir: Path) -> str:
        candidate_names = [
            "README_REQUIREMENT.md",
            "REQUIREMENT.md",
            "requirements.md",
            "README.md",
        ]

        chunks = []

        for name in candidate_names:
            path = project_dir / name
            if path.exists() and path.is_file():
                try:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    pass

        return "\n\n".join(chunks)

    def _build_error_context(
        self,
        project_requirement: str,
        source_file: Path,
        detected_language: str,
    ) -> str:
        return "\n".join(
            [
                "This is a static mixed-language project repair task.",
                "There may be Python, Java, C, JavaScript, or TypeScript files in the same ZIP project.",
                "Repair this file according to the project requirement and the comments inside the source code.",
                "Return the complete corrected source code for this file only.",
                "Do not remove public function names, class names, method names, or main functions.",
                f"Current file: {source_file.name}",
                f"Current file language: {detected_language}",
                "",
                "Project requirement:",
                project_requirement,
            ]
        )

    def _select_source_files(
        self,
        project_dir: Path,
        max_files: int = 20,
    ) -> list[Path]:
        supported_suffixes = {
            ".py",
            ".java",
            ".c",
            ".h",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
        }

        ignored_dirs = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            "target",
            ".pytest_cache",
            ".mypy_cache",
            ".idea",
            ".vscode",
        }

        selected = []

        for path in project_dir.rglob("*"):
            if not path.is_file():
                continue

            lower_parts = {part.lower() for part in path.parts}

            if lower_parts.intersection(ignored_dirs):
                continue

            if path.suffix.lower() not in supported_suffixes:
                continue

            lower_name = path.name.lower()

            if lower_name.startswith("test_"):
                continue

            if lower_name.endswith("_test.py"):
                continue

            if lower_name.endswith(".test.js"):
                continue

            if lower_name.endswith(".spec.js"):
                continue

            selected.append(path)

        selected.sort(key=lambda p: (self._language_sort_key(p), str(p)))

        return selected[:max_files]

    def _language_sort_key(self, source_file: Path) -> int:
        suffix = source_file.suffix.lower()

        order = {
            ".py": 0,
            ".java": 1,
            ".c": 2,
            ".h": 3,
            ".js": 4,
            ".jsx": 5,
            ".ts": 6,
            ".tsx": 7,
        }

        return order.get(suffix, 99)

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

    def _safe_relative_output_name(
        self,
        project_dir: Path,
        source_file: Path,
    ) -> str:
        try:
            relative_path = source_file.relative_to(project_dir)
        except ValueError:
            relative_path = source_file.name

        safe_name = str(relative_path).replace("\\", "_").replace("/", "_")
        return safe_name

    def _package_fixed_files(
        self,
        output_dir: Path,
        fixed_files: list[str],
    ) -> str:
        zip_path = output_dir / "fixed_project_files.zip"

        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in fixed_files:
                path = Path(file_path)

                if not path.exists() or not path.is_file():
                    continue

                zf.write(path, arcname=path.name)

        return str(zip_path)

    def _build_report(
        self,
        task_id: str,
        project_path: str,
        language: str,
        user_requirement: str,
        project_requirement: str,
        file_results: list[dict],
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
            f"- Project Path: {project_path}",
            f"- Router Language: {language}",
            f"- Success: {success}",
            f"- Memory Backend: {self.memory.describe_backend()}",
            f"- Tool Backend: official_mcp",
            "",
            "## User Requirement",
            "",
            user_requirement,
            "",
            "## Project Requirement",
            "",
            project_requirement,
            "",
            "## File Results",
            "",
        ]

        for index, item in enumerate(file_results, start=1):
            lines.extend(
                [
                    f"### File {index}",
                    "",
                    f"- Source File: {item.get('source_file', '')}",
                    f"- Fixed File: {item.get('fixed_file', '')}",
                    f"- Language: {item.get('language', '')}",
                    f"- Success: {item.get('success', False)}",
                    f"- Retrieved Context Used: {item.get('retrieved_context_used', False)}",
                    f"- Error: {item.get('error', '')}",
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

    def _trace(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"

        print(f"[ProjectStaticFixSkill] {message}", flush=True)

        if self.trace_path:
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _ensure_trailing_newline(self, text: str) -> str:
        if not text.endswith("\n"):
            return text + "\n"
        return text


def main():
    print("=== ProjectStaticFixSkill Official MCP Test ===")

    skill = ProjectStaticFixSkill()

    state = {
        "project_path": str(CODEFIX_DIR / "demo_static_project"),
        "user_requirement": "Fix obvious bugs in this project.",
        "language": "mixed",
    }

    result = skill.run(state)
    print(result)


if __name__ == "__main__":
    main()