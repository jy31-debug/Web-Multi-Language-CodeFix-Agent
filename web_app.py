from pathlib import Path #Python 自带的路径处理模块，专门处理文件路径文件夹路径、文件名、扩展名、父目录、文件是否存在
import shutil #主要负责高级文件操作，如复制、移动、删除文件和目录
import sys #用于访问 Python 解释器和运行环境

from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent #获取当前文件的绝对路径，并返回其父目录的路径，作为项目的基础目录

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from task_manager import create_task, save_uploaded_zip
from language_detector import detect_language_from_file, detect_main_language
from agent_graph import run_agent_graph


app = FastAPI(title="Web Multi-Language CodeFix Agent")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)  #通过路由访问根路径（/）时，返回HTML响应
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

        project_path = zip_result["project_dir"]  #解压后的项目路径
        source_file_path = ""    #单个文件路径为空

        if language_choice == "auto":
            if "pytest" in test_command.lower():
                detected_language = "python"
            else:
                detected_language = detect_main_language(project_path)  #检测项目的主要编程语言
        else:
            detected_language = language_choice

    else:
        project_path = ""   #单文件上传时，项目路径为空
        source_file_path = str(saved_file_path)   #单文件上传时，源文件路径就是上传的文件路径

        if language_choice == "auto":
            detected_language = detect_language_from_file(str(saved_file_path))  #检测上传文件的编程语言
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

    skill_result = result.get("skill_result", {}) #从运行结果中获取技能执行结果，默认为空字典

    if hasattr(skill_result, "data"): #如果技能结果是一个对象，并且具有data属性，则从中提取数据、成功状态和消息
        skill_data = skill_result.data
        skill_success = skill_result.success
        skill_message = skill_result.message
    elif isinstance(skill_result, dict):  #如果技能结果是一个字典，则从中提取数据、成功状态和消息
        skill_data = skill_result.get("data", {})
        skill_success = skill_result.get("success")
        skill_message = skill_result.get("message", "")
    else:  #如果技能结果既不是对象也不是字典，则将整个结果作为数据，并假设成功状态未知，消息为空
        skill_data = {}
        skill_success = False
        skill_message = ""

    report_path = skill_data.get("report_path", "") #从技能数据中提取报告路径、修复后文件路径、修复后压缩包路径、错误日志路径和差异文本，默认为空字符串
    fixed_file_path = skill_data.get("fixed_file_path", "") #从技能数据中提取修复后文件路径，默认为空字符串
    fixed_zip_path = skill_data.get("fixed_zip_path", "") #从技能数据中提取修复后压缩包路径，默认为空字符串
    error_log_path = skill_data.get("error_log_path", "") #从技能数据中提取错误日志路径，默认为空字符串
    diff_text = skill_data.get("diff", "") #从技能数据中提取差异文本，默认为空字符串

    page_result = {
        "task_id": task_info["task_id"],
        "upload_type": "zip" if is_zip_upload else "file",
        "uploaded_file": str(saved_file_path),
        "project_path": project_path,
        "language": result.get("language", detected_language),
        "test_command": test_command,
        "skill_decision": result.get("skill_decision", {}),
        "memory_backend": result.get("memory_backend", ""), #从运行结果中提取内存后端信息，默认为空字符串
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


'''
启动提示。
直接 python web_app.py 时，它会告诉你应该用 uvicorn 启动；
真正运行网页的是 uvicorn web_app:app。
'''
def main():
    print("Run this app with:")
    print("python -m uvicorn web_app:app --host 127.0.0.1 --port 8000")

if __name__ == "__main__":
    main()