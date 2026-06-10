from pathlib import Path
import difflib
import sys
import inspect
from typing import Any, Callable, Dict


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sandbox_runner import run_sandbox_command
from llm_patch_generator import generate_patch


class MCPToolServer:
    def __init__(self):
        self.tools: Dict[str, Callable[..., Dict[str, Any]]] = {}
        self.register_default_tools()

    def register_tool(self, name: str, func: Callable[..., Dict[str, Any]]):
        self.tools[name] = func

    def list_tools(self):
        return list(self.tools.keys())

    def call_tool(self, name: str, **kwargs) -> Dict[str, Any]:
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

    def register_default_tools(self):
        self.register_tool("read_file", tool_read_file)
        self.register_tool("write_file", tool_write_file)
        self.register_tool("run_command", tool_run_command)
        self.register_tool("generate_patch", tool_generate_patch)
        self.register_tool("show_diff", tool_show_diff)
        self.register_tool("save_report", tool_save_report)


def tool_read_file(path: str) -> Dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        return {
            "success": False,
            "error": f"File not found: {path}",
        }

    return {
        "success": True,
        "path": str(file_path),
        "content": file_path.read_text(encoding="utf-8"),
    }


def tool_write_file(path: str, content: str) -> Dict[str, Any]:
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
    language: str = "python",
    prefer_docker: bool = True,
) -> Dict[str, Any]:
    return run_sandbox_command(
        command=command,
        workspace_path=workspace_path,
        language=language,
        prefer_docker=prefer_docker,
    )


def tool_generate_patch(
    language: str,
    source_code: str,
    user_requirement: str,
    error_context: str = "",
    retrieved_context: str = "",
) -> Dict[str, Any]:
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


def tool_show_diff(
    original_text: str,
    fixed_text: str,
    original_name: str = "original",
    fixed_name: str = "fixed",
) -> Dict[str, Any]:
    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        fixed_text.splitlines(keepends=True),
        fromfile=original_name,
        tofile=fixed_name,
    )

    diff_text = "".join(diff)

    return {
        "success": True,
        "diff": diff_text,
    }


def tool_save_report(path: str, title: str, content: str) -> Dict[str, Any]:
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

    demo_dir = BASE_DIR / "demo_inputs"
    demo_file = demo_dir / "buggy_add.py"

    read_result = server.call_tool("read_file", path=str(demo_file))
    print()
    print("read_file success:", read_result.get("success"))

    if read_result.get("success"):
        source_code = read_result["content"]

        patch_result = server.call_tool(
            "generate_patch",
            language="python",
            source_code=source_code,
            user_requirement="修复 add 函数，它应该返回 a 和 b 的和。",
            error_context="",
            retrieved_context="",
        )

        print("generate_patch success:", patch_result.get("success"))
        print("generate_patch mode:", patch_result.get("mode"))
        print("generate_patch error:", patch_result.get("error"))
        print("generate_patch error_cause:", patch_result.get("error_cause"))
        print("generate_patch raw_output:", patch_result.get("raw_output"))

        fixed_code = patch_result.get("fixed_code", source_code)

        diff_result = server.call_tool(
            "show_diff",
            original_text=source_code,
            fixed_text=fixed_code,
            original_name="buggy_add.py",
            fixed_name="fixed_buggy_add.py",
        )

        print("show_diff success:", diff_result.get("success"))
        print(diff_result.get("diff", ""))

    command_result = server.call_tool(
        "run_command",
        command="python --version",
        workspace_path=str(BASE_DIR),
        language="python",
        prefer_docker=True,
    )

    print("run_command backend:", command_result.get("backend"))
    print("run_command success:", command_result.get("success"))


if __name__ == "__main__":
    main()