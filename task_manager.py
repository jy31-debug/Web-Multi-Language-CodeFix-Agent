from pathlib import Path
from datetime import datetime
import shutil
import zipfile


BASE_DIR = Path(__file__).resolve().parent
WORKSPACES_DIR = BASE_DIR / "workspaces"


def create_task(task_name: str | None = None) -> dict:
    """
    Create a new task workspace.

    Every user upload creates one task workspace.
    Uploaded files, extracted projects, error logs, traces, reports and outputs
    are stored inside this workspace.
    """
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    if task_name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_name = f"task_{timestamp}"

    task_dir = WORKSPACES_DIR / task_name

    uploaded_dir = task_dir / "uploaded"
    project_dir = task_dir / "project"
    error_logs_dir = task_dir / "error_logs"
    reports_dir = task_dir / "reports"
    traces_dir = task_dir / "traces"
    outputs_dir = task_dir / "outputs"

    for directory in [
        uploaded_dir,
        project_dir,
        error_logs_dir,
        reports_dir,
        traces_dir,
        outputs_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    return {
        "task_id": task_name,
        "task_dir": str(task_dir),
        "uploaded_dir": str(uploaded_dir),
        "project_dir": str(project_dir),
        "error_logs_dir": str(error_logs_dir),
        "reports_dir": str(reports_dir),
        "traces_dir": str(traces_dir),
        "outputs_dir": str(outputs_dir),
    }


def save_uploaded_file(task_info: dict, source_file_path: str) -> dict:
    source_path = Path(source_file_path)

    if not source_path.exists():
        raise FileNotFoundError(f"Uploaded file does not exist: {source_file_path}")

    uploaded_dir = Path(task_info["uploaded_dir"])
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    target_path = uploaded_dir / source_path.name

    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)

    return {
        "type": "file",
        "original_path": str(source_path),
        "saved_path": str(target_path),
        "filename": source_path.name,
    }


def save_uploaded_zip(task_info: dict, source_zip_path: str) -> dict:
    """
    Save and extract one uploaded zip file.

    Original zip:
        workspace/uploaded/

    Extracted project:
        workspace/project/
    """
    source_path = Path(source_zip_path)

    if not source_path.exists():
        return {
            "success": False,
            "type": "zip",
            "error": f"Uploaded zip does not exist: {source_zip_path}",
        }

    if source_path.suffix.lower() != ".zip":
        return {
            "success": False,
            "type": "zip",
            "error": f"Not a zip file: {source_zip_path}",
        }

    uploaded_dir = Path(task_info["uploaded_dir"])
    project_dir = Path(task_info["project_dir"])

    uploaded_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)

    copied_zip_path = uploaded_dir / source_path.name

    if source_path.resolve() != copied_zip_path.resolve():
        shutil.copy2(source_path, copied_zip_path)

    try:
        with zipfile.ZipFile(copied_zip_path, "r") as zip_ref:
            zip_ref.extractall(project_dir)

        return {
            "success": True,
            "type": "zip",
            "original_path": str(source_path),
            "saved_zip_path": str(copied_zip_path),
            "project_dir": str(project_dir),
            "filename": source_path.name,
            "error": "",
        }

    except zipfile.BadZipFile:
        return {
            "success": False,
            "type": "zip",
            "original_path": str(source_path),
            "saved_zip_path": str(copied_zip_path),
            "project_dir": str(project_dir),
            "filename": source_path.name,
            "error": "Bad zip file. The uploaded file is not a valid zip archive.",
        }


def get_error_log_path(task_info: dict, filename: str = "error_log.txt") -> str:
    return str(Path(task_info["error_logs_dir"]) / filename)


def get_report_path(task_info: dict, filename: str = "repair_report.md") -> str:
    return str(Path(task_info["reports_dir"]) / filename)


def get_trace_path(task_info: dict, filename: str = "trace.jsonl") -> str:
    return str(Path(task_info["traces_dir"]) / filename)


def get_output_path(task_info: dict, filename: str) -> str:
    return str(Path(task_info["outputs_dir"]) / filename)


def describe_task(task_info: dict) -> str:
    lines = [
        "Task workspace summary:",
        f"task_id: {task_info['task_id']}",
        f"task_dir: {task_info['task_dir']}",
        f"uploaded_dir: {task_info['uploaded_dir']}",
        f"project_dir: {task_info['project_dir']}",
        f"error_logs_dir: {task_info['error_logs_dir']}",
        f"reports_dir: {task_info['reports_dir']}",
        f"traces_dir: {task_info['traces_dir']}",
        f"outputs_dir: {task_info['outputs_dir']}",
    ]
    return "\n".join(lines)


def main():
    print("=== Day 22 Task Manager Test ===")

    task_info = create_task()
    print(describe_task(task_info))

    print("\nDefault generated paths:")
    print("error log:", get_error_log_path(task_info))
    print("report:", get_report_path(task_info))
    print("trace:", get_trace_path(task_info))
    print("output:", get_output_path(task_info, "fixed_code.py"))

    print("\nTask manager test finished.")


if __name__ == "__main__":
    main()