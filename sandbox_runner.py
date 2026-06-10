import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional


def is_docker_available() -> bool:
    return shutil.which("docker") is not None


def run_command_local(
    command: str,
    workspace_path: str,
    timeout: int = 20,
) -> Dict:
    workspace = Path(workspace_path)

    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "success": result.returncode == 0,
            "backend": "local",
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
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


def run_command_in_docker(
    command: str,
    workspace_path: str,
    image: str = "python:3.11-slim",
    timeout: int = 30,
) -> Dict:
    workspace = Path(workspace_path).resolve()

    if not is_docker_available():
        return {
            "success": False,
            "backend": "docker_unavailable",
            "command": command,
            "returncode": -1,
            "stdout": "",
            "stderr": "Docker is not available on this machine.",
        }

    docker_command = (
        f'docker run --rm '
        f'-v "{workspace}:/workspace" '
        f'-w /workspace '
        f'{image} '
        f'sh -c "{command}"'
    )

    try:
        result = subprocess.run(
            docker_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "success": result.returncode == 0,
            "backend": "docker",
            "image": image,
            "command": command,
            "docker_command": docker_command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "backend": "docker",
            "image": image,
            "command": command,
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": f"Docker command timed out after {timeout} seconds.",
        }


def run_sandbox_command(
    command: str,
    workspace_path: str,
    language: str = "python",
    prefer_docker: bool = True,
    timeout: int = 30,
) -> Dict:
    image_map = {
        "python": "python:3.11-slim",
        "java": "eclipse-temurin:17",
        "c": "gcc:13",
        "cpp": "gcc:13",
        "javascript": "node:20-slim",
        "typescript": "node:20-slim",
    }

    image = image_map.get(language, "python:3.11-slim")

    if prefer_docker:
        docker_result = run_command_in_docker(
            command=command,
            workspace_path=workspace_path,
            image=image,
            timeout=timeout,
        )

        if docker_result["backend"] != "docker_unavailable":
            return docker_result

    local_result = run_command_local(
        command=command,
        workspace_path=workspace_path,
        timeout=timeout,
    )

    local_result["docker_fallback_reason"] = (
        "Docker is unavailable, so the command was executed locally."
    )

    return local_result


def main():
    print("=== Sandbox Runner Test ===")
    print("docker available:", is_docker_available())

    current_dir = Path(__file__).resolve().parent

    result = run_sandbox_command(
        command="python --version",
        workspace_path=str(current_dir),
        language="python",
        prefer_docker=True,
    )

    print("backend:", result["backend"])
    print("success:", result["success"])
    print("returncode:", result["returncode"])
    print("stdout:", result["stdout"])
    print("stderr:", result["stderr"])


if __name__ == "__main__":
    main()