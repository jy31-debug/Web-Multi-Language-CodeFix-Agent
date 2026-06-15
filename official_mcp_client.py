import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Awaitable, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


BASE_DIR = Path(__file__).resolve().parent
MCP_SERVER_PATH = BASE_DIR / "codefix_mcp_server.py"


class OfficialMCPClient:
    """
    Official MCP client for CodeFix Agent.

    Main idea:
    - Use official MCP stdio transport to connect to codefix_mcp_server.py.
    - Use official ClientSession to call tools.
    - For run_command, try official MCP first.
    - If MCP transport fails on Windows with TaskGroup error, fall back to safe local subprocess.
    """

    def __init__(
        self,
        server_script_path: str | None = None,
        default_timeout: int = 60,
    ):
        self.server_script_path = str(server_script_path or MCP_SERVER_PATH)
        self.default_timeout = default_timeout

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        arguments = arguments or {}
        timeout = timeout or self.default_timeout

        result = self._run_async_safely(
            lambda: self._call_tool_async(
                tool_name=tool_name,
                arguments=arguments,
                timeout=timeout,
            )
        )

        if tool_name == "run_command" and self._should_fallback_run_command(result):
            fallback_result = self._local_run_command_fallback(arguments)
            fallback_result["tool_name"] = tool_name
            fallback_result["mcp_error"] = result.get("error", "")
            fallback_result["mcp_fallback_used"] = True
            return fallback_result

        return result

    def list_tools(self, timeout: int | None = None) -> list[str]:
        timeout = timeout or self.default_timeout
        return self._run_async_safely(
            lambda: self._list_tools_async(timeout=timeout)
        )

    def _run_async_safely(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(coro_factory()))
                return future.result()

        return asyncio.run(coro_factory())

    async def _call_tool_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        if not Path(self.server_script_path).exists():
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"MCP server script not found: {self.server_script_path}",
            }

        try:
            return await asyncio.wait_for(
                self._call_tool_with_session(
                    tool_name=tool_name,
                    arguments=arguments,
                ),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"MCP tool call timed out after {timeout} seconds.",
            }

        except BaseExceptionGroup as exc:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
            }

        except Exception as exc:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
            }

    async def _call_tool_with_session(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_script_path],
            env=os.environ.copy(),
        )

        async with AsyncExitStack() as stack:
            stdio_transport = await stack.enter_async_context(
                stdio_client(server_params)
            )

            read_stream, write_stream = stdio_transport

            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            await session.initialize()

            result = await session.call_tool(
                tool_name,
                arguments=arguments,
            )

            return self._parse_tool_result(
                tool_name=tool_name,
                result=result,
            )

    async def _list_tools_async(self, timeout: int) -> list[str]:
        if not Path(self.server_script_path).exists():
            return []

        try:
            return await asyncio.wait_for(
                self._list_tools_with_session(),
                timeout=timeout,
            )

        except Exception:
            return []

    async def _list_tools_with_session(self) -> list[str]:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_script_path],
            env=os.environ.copy(),
        )

        async with AsyncExitStack() as stack:
            stdio_transport = await stack.enter_async_context(
                stdio_client(server_params)
            )

            read_stream, write_stream = stdio_transport

            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            await session.initialize()
            response = await session.list_tools()

            return [tool.name for tool in response.tools]

    def _parse_tool_result(self, tool_name: str, result: Any) -> dict[str, Any]:
        if getattr(result, "isError", False):
            return {
                "success": False,
                "tool_name": tool_name,
                "error": self._extract_text_content(result),
            }

        text = self._extract_text_content(result)

        if not text:
            return {
                "success": True,
                "tool_name": tool_name,
                "content": "",
            }

        try:
            data = json.loads(text)

            if isinstance(data, dict):
                data.setdefault("success", True)
                data.setdefault("tool_name", tool_name)
                return data

            return {
                "success": True,
                "tool_name": tool_name,
                "result": data,
            }

        except json.JSONDecodeError:
            return {
                "success": True,
                "tool_name": tool_name,
                "content": text,
            }

    def _extract_text_content(self, result: Any) -> str:
        content_items = getattr(result, "content", [])
        texts = []

        for item in content_items:
            if isinstance(item, TextContent):
                texts.append(item.text)
            elif hasattr(item, "text"):
                texts.append(str(item.text))
            else:
                texts.append(str(item))

        return "\n".join(texts)

    def _should_fallback_run_command(self, result: dict[str, Any]) -> bool:
        if result.get("success") is True:
            return False

        if "returncode" in result:
            return False

        error = str(result.get("error", ""))

        fallback_keywords = [
            "TaskGroup",
            "timed out",
            "MCP tool call timed out",
            "unhandled errors",
            "transport",
            "BrokenResourceError",
            "EndOfStream",
        ]

        return any(keyword in error for keyword in fallback_keywords)

    def _local_run_command_fallback(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = str(arguments.get("command", "pytest")).strip()
        workspace_path = str(arguments.get("workspace_path", "")).strip()
        timeout = int(arguments.get("timeout", 30))

        workspace = Path(workspace_path)

        if not workspace.exists():
            return {
                "success": False,
                "backend": "local_subprocess_fallback",
                "command": command,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Workspace does not exist: {workspace_path}",
            }

        if not command:
            command = "pytest"

        if command == "pytest":
            command_args = [sys.executable, "-m", "pytest", "-q"]
            shell = False
            command_display = "python -m pytest -q"
        else:
            command_args = command
            shell = True
            command_display = command

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
                "backend": "local_subprocess_fallback",
                "command": command_display,
                "returncode": completed.returncode,
                "stdout": self._truncate_text(completed.stdout),
                "stderr": self._truncate_text(completed.stderr),
            }

        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            return {
                "success": False,
                "backend": "local_subprocess_fallback",
                "command": command_display,
                "returncode": -1,
                "stdout": self._truncate_text(stdout if isinstance(stdout, str) else str(stdout)),
                "stderr": self._truncate_text(stderr if isinstance(stderr, str) else str(stderr))
                + f"\nCommand timed out after {timeout} seconds.",
            }

        except Exception as exc:
            return {
                "success": False,
                "backend": "local_subprocess_fallback",
                "command": command_display,
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
            }

    def _truncate_text(self, text: str, max_chars: int = 12000) -> str:
        if not text:
            return ""

        if len(text) <= max_chars:
            return text

        return text[:max_chars] + "\n\n...[output truncated]..."


def main():
    client = OfficialMCPClient()

    print("=== Official MCP Client Test ===")

    print("\nAvailable MCP tools:")
    print(client.list_tools())

    result = client.call_tool(
        "show_diff",
        {
            "original_text": "def add(a, b):\n    return a - b\n",
            "fixed_text": "def add(a, b):\n    return a + b\n",
            "original_name": "buggy_add.py",
            "fixed_name": "fixed_buggy_add.py",
        },
    )

    print("\nshow_diff result:")
    print(result)

    print("\nBefore run_command test")

    command_result = client.call_tool(
        "run_command",
        {
            "command": "pytest",
            "workspace_path": str(BASE_DIR),
            "timeout": 10,
        },
        timeout=15,
    )

    print("\nrun_command result:")
    print(command_result)

    print("\nOfficial MCP Client Test Finished")


if __name__ == "__main__":
    main()