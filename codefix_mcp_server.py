from pathlib import Path
import difflib
import os
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from llm_patch_generator import generate_patch


mcp = FastMCP("CodeFix MCP Server")


MAX_OUTPUT_CHARS = 12000


def _truncate_text(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n...[output truncated]..."


@mcp.tool()
def read_file(path: str) -> dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        return {
            "success": False,
            "error": f"File not found: {path}",
        }

    return {
        "success": True,
        "path": str(file_path),
        "content": file_path.read_text(encoding="utf-8", errors="ignore"),
    }


@mcp.tool()
def write_file(path: str, content: str) -> dict[str, Any]:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "path": str(file_path),
        "bytes": len(content.encode("utf-8")),
    }


@mcp.tool()
def run_command(
    command: str,
    workspace_path: str,
    timeout: int = 30,
) -> dict[str, Any]:
    workspace = Path(workspace_path)

    if not workspace.exists():
        return {
            "success": False,
            "backend": "official_mcp_local_subprocess",
            "command": command,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Workspace does not exist: {workspace_path}",
        }

    original_command = command.strip()

    if not original_command:
        original_command = "pytest"

    if original_command == "pytest":
        command_args = [sys.executable, "-m", "pytest", "-q"]
        shell = False
        command_display = "python -m pytest -q"
    else:
        command_args = original_command
        shell = True
        command_display = original_command

    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace) + os.pathsep + env.get("PYTHONPATH", "")

    try:
        completed = subprocess.run(
            command_args,
            cwd=str(workspace),
            shell=shell,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )

        return {
            "success": completed.returncode == 0,
            "backend": "official_mcp_local_subprocess",
            "command": command_display,
            "returncode": completed.returncode,
            "stdout": _truncate_text(completed.stdout),
            "stderr": _truncate_text(completed.stderr),
        }

    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        return {
            "success": False,
            "backend": "official_mcp_local_subprocess",
            "command": command_display,
            "returncode": -1,
            "stdout": _truncate_text(stdout if isinstance(stdout, str) else str(stdout)),
            "stderr": _truncate_text(stderr if isinstance(stderr, str) else str(stderr))
            + f"\nCommand timed out after {timeout} seconds.",
        }

    except Exception as exc:
        return {
            "success": False,
            "backend": "official_mcp_local_subprocess",
            "command": command_display,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


@mcp.tool()
def generate_code_patch(
    language: str,
    source_code: str,
    user_requirement: str,
    error_context: str = "",
    retrieved_context: str = "",
) -> dict[str, Any]:
    return generate_patch(
        user_requirement=user_requirement,
        language=language,
        source_code=source_code,
        error_info=error_context,
        retrieved_context=retrieved_context,
    )


@mcp.tool()
def show_diff(
    original_text: str,
    fixed_text: str,
    original_name: str = "original",
    fixed_name: str = "fixed",
) -> dict[str, Any]:
    if not original_text.endswith("\n"):
        original_text += "\n"

    if not fixed_text.endswith("\n"):
        fixed_text += "\n"

    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        fixed_text.splitlines(keepends=True),
        fromfile=original_name,
        tofile=fixed_name,
    )

    return {
        "success": True,
        "diff": "".join(diff),
    }


@mcp.tool()
def save_report(path: str, title: str, content: str) -> dict[str, Any]:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    full_content = f"# {title}\n\n{content}\n"
    report_path.write_text(full_content, encoding="utf-8")

    return {
        "success": True,
        "path": str(report_path),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()