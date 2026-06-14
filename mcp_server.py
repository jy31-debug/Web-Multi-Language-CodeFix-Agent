from pathlib import Path
import difflib
import inspect
import subprocess
import sys
from typing import Any, Callable, Dict


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from llm_patch_generator import generate_patch


class MCPToolServer:
    """
    Lightweight MCP-style tool server for CodeFix Agent.

    It provides a unified tool interface:
    - read_file
    - write_file
    - run_command
    - generate_patch
    - show_diff
    - save_report

    In the next step, PythonTestFixSkill will call this server instead of
    directly calling generate_patch and difflib.
    """

    def __init__(self):
        self.tools: Dict[str, Callable[..., Dict[str, Any]]] = {}
        self.register_default_tools()

    def register_tool(self, name: str, func: Callable[..., Dict[str, Any]]) -> None:
        """
        Register one tool by name.
        """
        self.tools[name] = func

    def list_tools(self) -> list[str]:
        """
        List all registered tool names.
        """
        return list(self.tools.keys())

    def call_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Call a registered tool.

        Example:
            server.call_tool("read_file", path="demo.py")
        """
        if name not in self.tools:
            return {
                "success": False,
                "tool_name": name,
                "error": f"Tool not found: {name}",
            }

        try:
            result = self.tools[name](**kwargs)

            if isinstance(result, dict):
                result.setdefault("tool_name", name)
                return result

            return {
                "success": True,
                "tool_name": name,
                "result": result,
            }

        except Exception as exc:
            return {
                "success": False,
                "tool_name": name,
                "error": str(exc),
            }

    def register_default_tools(self) -> None:
        """
        Register default tools used by CodeFix Agent.
        """
        self.register_tool("read_file", tool_read_file)
        self.register_tool("write_file", tool_write_file)
        self.register_tool("run_command", tool_run_command)
        self.register_tool("generate_patch", tool_generate_patch)
        self.register_tool("show_diff", tool_show_diff)
        self.register_tool("save_report", tool_save_report)


def tool_read_file(path: str) -> Dict[str, Any]:
    """
    Read a text file.
    """
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


def tool_write_file(path: str, content: str) -> Dict[str, Any]:
    """
    Write text content into a file.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "path": str(file_path),
        "bytes": len(content.encode("utf-8")),
    }


def tool_run_command(
    command: str,
    workspace_path: str,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Run a command locally.

    For now we keep this simple and local.
    Docker sandbox can be connected later if needed.
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        return {
            "success": False,
            "backend": "local",
            "command": command,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Workspace does not exist: {workspace_path}",
        }

    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        return {
            "success": completed.returncode == 0,
            "backend": "local",
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "backend": "local",
            "command": command,
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": f"Command timed out after {timeout} seconds.",
        }

    except Exception as exc:
        return {
            "success": False,
            "backend": "local",
            "command": command,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def tool_generate_patch(
    language: str,
    source_code: str,
    user_requirement: str,
    error_context: str = "",
    retrieved_context: str = "",
) -> Dict[str, Any]:
    """
    Call llm_patch_generator.generate_patch safely.

    This function adapts different parameter names:
    - error_context
    - error_info
    - error_log
    - error_message
    - test_error

    Your current generate_patch uses error_info, so this compatibility is important.
    """
    signature = inspect.signature(generate_patch)
    supported_params = set(signature.parameters.keys())

    kwargs: Dict[str, Any] = {}

    if "user_requirement" in supported_params:
        kwargs["user_requirement"] = user_requirement

    if "language" in supported_params:
        kwargs["language"] = language

    if "source_code" in supported_params:
        kwargs["source_code"] = source_code

    if "error_context" in supported_params:
        kwargs["error_context"] = error_context
    elif "error_info" in supported_params:
        kwargs["error_info"] = error_context
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


def tool_show_diff(
    original_text: str,
    fixed_text: str,
    original_name: str = "original",
    fixed_name: str = "fixed",
) -> Dict[str, Any]:
    """
    Build unified diff between original text and fixed text.
    """
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


def tool_save_report(path: str, title: str, content: str) -> Dict[str, Any]:
    """
    Save a Markdown report.
    """
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    full_content = f"# {title}\n\n{content}\n"
    report_path.write_text(full_content, encoding="utf-8")

    return {
        "success": True,
        "path": str(report_path),
    }


def main():
    print("=== MCP Tool Server Test ===")

    server = MCPToolServer()

    print("registered tools:")
    print(server.list_tools())

    demo_code = """def add(a, b):
    return a - b
"""

    patch_result = server.call_tool(
        "generate_patch",
        language="python",
        source_code=demo_code,
        user_requirement="修复 add 函数，它应该返回 a 和 b 的和。",
        error_context="测试失败：add(1, 2) 应该等于 3，但当前代码返回 -1。",
        retrieved_context="",
    )

    print("\ngenerate_patch success:", patch_result.get("success"))
    print("generate_patch mode:", patch_result.get("mode"))
    print("error_cause:", patch_result.get("error_cause"))
    print("fix_summary:", patch_result.get("fix_summary"))

    fixed_code = patch_result.get("fixed_code", demo_code)

    diff_result = server.call_tool(
        "show_diff",
        original_text=demo_code,
        fixed_text=fixed_code,
        original_name="buggy_add.py",
        fixed_name="fixed_buggy_add.py",
    )

    print("\nshow_diff success:", diff_result.get("success"))
    print(diff_result.get("diff", ""))

    command_result = server.call_tool(
        "run_command",
        command="python --version",
        workspace_path=str(BASE_DIR),
        timeout=20,
    )

    print("\nrun_command success:", command_result.get("success"))
    print("backend:", command_result.get("backend"))
    print("stdout:", command_result.get("stdout"))
    print("stderr:", command_result.get("stderr"))

    print("\nMCP tool server test finished.")


if __name__ == "__main__":
    main()