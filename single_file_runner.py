from pathlib import Path
import difflib

from task_manager import (
    create_task,
    save_uploaded_file,
    get_output_path,
    get_report_path,
)
from language_detector import detect_language_from_file
from llm_patch_generator import generate_patch


BASE_DIR = Path(__file__).resolve().parent


def read_text_file(file_path: str) -> str:
    """
    Read a text file with UTF-8 encoding.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    return path.read_text(encoding="utf-8")


def write_text_file(file_path: str, content: str) -> None:
    """
    Write text content to a file with UTF-8 encoding.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_unified_diff(original_code: str, fixed_code: str, filename: str) -> str:
    """
    Build a unified diff between original code and fixed code.
    """
    original_lines = original_code.splitlines(keepends=True)
    fixed_lines = fixed_code.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        original_lines,
        fixed_lines,
        fromfile=f"original/{filename}",
        tofile=f"fixed/{filename}",
    )

    return "".join(diff_lines)


def save_single_file_report(
    report_path: str,
    task_info: dict,
    uploaded_file_info: dict,
    language: str,
    user_requirement: str,
    llm_result: dict,
    diff_text: str,
    fixed_file_path: str,
) -> None:
    """
    Save a Markdown repair report for the single-file repair task.
    """
    report = f"""# Single File CodeFix Report

## Task Info

- Task ID: {task_info["task_id"]}
- Task Directory: {task_info["task_dir"]}
- Uploaded File: {uploaded_file_info["saved_path"]}
- Fixed File: {fixed_file_path}

## Language

{language}

## User Requirement

{user_requirement}

## LLM Mode

{llm_result.get("mode", "")}

## Success

{llm_result.get("success", "")}

## Error Cause

{llm_result.get("error_cause", "")}

## Fix Summary

{llm_result.get("fix_summary", "")}

## Diff

~~~diff
{diff_text}
~~~

## Fixed Code

~~~{language}
{llm_result.get("fixed_code", "")}
~~~
"""
    write_text_file(report_path, report)


def run_single_file_repair(source_file_path: str, user_requirement: str) -> dict:
    """
    Run a single-file repair task.

    Pipeline:
    user file -> create workspace -> copy file -> detect language
    -> call LangChain + DeepSeek -> generate fixed code
    -> build diff -> save fixed file -> save report
    """
    task_info = create_task()
    uploaded_file_info = save_uploaded_file(task_info, source_file_path)

    saved_file_path = uploaded_file_info["saved_path"]
    filename = uploaded_file_info["filename"]

    language = detect_language_from_file(saved_file_path)
    source_code = read_text_file(saved_file_path)

    llm_result = generate_patch(
        user_requirement=user_requirement,
        language=language,
        source_code=source_code,
        error_info="Single-file repair mode. No test log is provided.",
        retrieved_context="No external retrieval context is provided in this single-file demo.",
    )

    fixed_code = llm_result["fixed_code"]
    diff_text = build_unified_diff(source_code, fixed_code, filename)

    fixed_file_path = get_output_path(task_info, f"fixed_{filename}")
    write_text_file(fixed_file_path, fixed_code)

    report_path = get_report_path(task_info, "single_file_repair_report.md")
    save_single_file_report(
        report_path=report_path,
        task_info=task_info,
        uploaded_file_info=uploaded_file_info,
        language=language,
        user_requirement=user_requirement,
        llm_result=llm_result,
        diff_text=diff_text,
        fixed_file_path=fixed_file_path,
    )

    return {
        "success": llm_result["success"],
        "task_info": task_info,
        "uploaded_file_info": uploaded_file_info,
        "language": language,
        "llm_result": llm_result,
        "diff_text": diff_text,
        "fixed_file_path": fixed_file_path,
        "report_path": report_path,
    }


def main():
    print("=== Day 19 Single File Runner Test ===")

    demo_file = BASE_DIR / "demo_inputs" / "buggy_add.py"
    user_requirement = "Fix the add function. It should return the sum of a and b."

    if not demo_file.exists():
        print("Demo file does not exist:")
        print(demo_file)
        print()
        print("Please create it first:")
        print(r"agent_harness_projects\codefix_agent\demo_inputs\buggy_add.py")
        return

    result = run_single_file_repair(
        source_file_path=str(demo_file),
        user_requirement=user_requirement,
    )

    print("success:", result["success"])
    print("task_id:", result["task_info"]["task_id"])
    print("language:", result["language"])
    print("fixed_file_path:", result["fixed_file_path"])
    print("report_path:", result["report_path"])

    print("\nERROR_CAUSE:")
    print(result["llm_result"]["error_cause"])

    print("\nFIX_SUMMARY:")
    print(result["llm_result"]["fix_summary"])

    print("\nDIFF:")
    print(result["diff_text"])

    print("\nSingle file runner test finished.")


if __name__ == "__main__":
    main()