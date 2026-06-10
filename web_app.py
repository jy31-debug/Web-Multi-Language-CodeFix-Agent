from pathlib import Path
import shutil
import sys

from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from task_manager import create_task, save_uploaded_zip
from language_detector import detect_language_from_file, detect_main_language
from agent_graph import run_agent_graph


app = FastAPI(title="Web Multi-Language CodeFix Agent")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": None,
        },
    )


@app.post("/run-agent", response_class=HTMLResponse)
async def run_agent(
    request: Request,
    uploaded_file: UploadFile = File(...),
    user_requirement: str = Form(""),
    test_command: str = Form(""),
    language_choice: str = Form("auto"),
):
    task_info = create_task()

    uploaded_dir = Path(task_info["uploaded_dir"])
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    saved_file_path = uploaded_dir / uploaded_file.filename

    with saved_file_path.open("wb") as buffer:
        shutil.copyfileobj(uploaded_file.file, buffer)

    is_zip_upload = saved_file_path.suffix.lower() == ".zip"

    if is_zip_upload:
        zip_result = save_uploaded_zip(task_info, str(saved_file_path))

        if not zip_result.get("success"):
            page_result = self_error_result(
                task_info=task_info,
                upload_type="zip",
                uploaded_file=str(saved_file_path),
                final_message=f"Zip extraction failed: {zip_result.get('error')}",
            )
            return templates.TemplateResponse(
                request,
                "index.html",
                {
                    "result": page_result,
                },
            )

        project_path = zip_result["project_dir"]
        source_file_path = ""

        if language_choice == "auto":
            if "pytest" in test_command.lower():
                detected_language = "python"
            else:
                detected_language = detect_main_language(project_path)
        else:
            detected_language = language_choice

    else:
        project_path = ""
        source_file_path = str(saved_file_path)

        if language_choice == "auto":
            detected_language = detect_language_from_file(str(saved_file_path))
        else:
            detected_language = language_choice

    initial_state = {
        "source_file_path": source_file_path,
        "project_path": project_path,
        "user_requirement": user_requirement,
        "test_command": test_command,
        "language": detected_language,
    }

    result = run_agent_graph(initial_state)

    skill_result = result.get("skill_result", {})

    if hasattr(skill_result, "data"):
        skill_data = skill_result.data
        skill_success = skill_result.success
        skill_message = skill_result.message
    elif isinstance(skill_result, dict):
        skill_data = skill_result.get("data", {})
        skill_success = skill_result.get("success")
        skill_message = skill_result.get("message", "")
    else:
        skill_data = {}
        skill_success = False
        skill_message = ""

    report_path = skill_data.get("report_path", "")
    fixed_file_path = skill_data.get("fixed_file_path", "")
    fixed_zip_path = skill_data.get("fixed_zip_path", "")
    error_log_path = skill_data.get("error_log_path", "")
    diff_text = skill_data.get("diff", "")

    page_result = {
        "task_id": task_info["task_id"],
        "upload_type": "zip" if is_zip_upload else "file",
        "uploaded_file": str(saved_file_path),
        "project_path": project_path,
        "language": result.get("language", detected_language),
        "test_command": test_command,
        "skill_decision": result.get("skill_decision", {}),
        "memory_backend": result.get("memory_backend", ""),
        "final_message": result.get("final_message", ""),
        "skill_result": {
            "success": skill_success,
            "message": skill_message,
        },
        "report_path": report_path,
        "fixed_file_path": fixed_file_path,
        "fixed_zip_path": fixed_zip_path,
        "error_log_path": error_log_path,
        "diff": diff_text,
        "report_exists": Path(report_path).exists() if report_path else False,
        "fixed_file_exists": Path(fixed_file_path).exists() if fixed_file_path else False,
        "fixed_zip_exists": Path(fixed_zip_path).exists() if fixed_zip_path else False,
        "error_log_exists": Path(error_log_path).exists() if error_log_path else False,
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": page_result,
        },
    )


@app.get("/download")
async def download_file(path: str):
    file_path = Path(path)

    if not file_path.exists():
        return HTMLResponse(f"<h3>File not found: {path}</h3>", status_code=404)

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


def self_error_result(
    task_info: dict,
    upload_type: str,
    uploaded_file: str,
    final_message: str,
) -> dict:
    return {
        "task_id": task_info["task_id"],
        "upload_type": upload_type,
        "uploaded_file": uploaded_file,
        "project_path": "",
        "language": "unknown",
        "test_command": "",
        "skill_decision": {},
        "memory_backend": "",
        "final_message": final_message,
        "skill_result": {},
        "report_path": "",
        "fixed_file_path": "",
        "fixed_zip_path": "",
        "error_log_path": "",
        "diff": "",
        "report_exists": False,
        "fixed_file_exists": False,
        "fixed_zip_exists": False,
        "error_log_exists": False,
    }


def main():
    print("Run this app with:")
    print("uvicorn agent_harness_projects.codefix_agent.web_app:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    main()