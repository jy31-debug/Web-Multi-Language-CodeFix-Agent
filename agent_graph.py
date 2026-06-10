from pathlib import Path
import sys
from typing import TypedDict, Any

from langgraph.graph import StateGraph, END


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SKILLS_DIR = BASE_DIR / "skills"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

from language_detector import detect_language_from_file, detect_main_language
from skill_router import route_skill
from memory_manager import MemoryManager
from single_file_fix_skill import SingleFileFixSkill
from python_test_fix_skill import PythonTestFixSkill
from project_static_fix_skill import ProjectStaticFixSkill


class CodeFixState(TypedDict, total=False):
    source_file_path: str
    project_path: str
    user_requirement: str
    test_command: str
    language: str
    skill_decision: dict
    skill_result: Any
    memory_backend: str
    final_message: str


def detect_language_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] detect_language")

    source_file_path = state.get("source_file_path", "")
    project_path = state.get("project_path", "")
    test_command = (state.get("test_command", "") or "").lower()
    existing_language = state.get("language", "")

    if existing_language and existing_language != "unknown":
        return state

    if "pytest" in test_command or "python -m pytest" in test_command:
        state["language"] = "python"
        return state

    if source_file_path:
        state["language"] = detect_language_from_file(source_file_path)
        return state

    if project_path:
        state["language"] = detect_main_language(project_path)
        return state

    state["language"] = "unknown"
    return state


def route_skill_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] route_skill")

    state["skill_decision"] = route_skill(state)
    return state


def remember_start_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] remember_start")

    memory = MemoryManager()
    state["memory_backend"] = memory.describe_backend()

    memory.remember_short_term(
        "latest_codefix_task",
        {
            "language": state.get("language"),
            "skill_decision": state.get("skill_decision"),
            "source_file_path": state.get("source_file_path"),
            "project_path": state.get("project_path"),
            "test_command": state.get("test_command"),
        },
    )

    return state


def run_skill_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] run_skill")

    decision = state.get("skill_decision", {})
    skill_name = decision.get("skill_name", "")

    if skill_name == "SingleFileFixSkill":
        skill = SingleFileFixSkill()
    elif skill_name == "PythonTestFixSkill":
        skill = PythonTestFixSkill()
    elif skill_name == "ProjectStaticFixSkill":
        skill = ProjectStaticFixSkill()
    else:
        state["skill_result"] = {
            "success": False,
            "skill_name": skill_name,
            "message": f"Skill not implemented yet: {skill_name}",
            "data": {},
        }
        return state

    result = skill.run(state)
    state["skill_result"] = result
    return state


def remember_finish_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] remember_finish")

    memory = MemoryManager()
    skill_result = state.get("skill_result")

    memory.remember_episodic(
        {
            "language": state.get("language"),
            "skill_decision": state.get("skill_decision"),
            "skill_result": str(skill_result),
        }
    )

    return state


def save_final_message_node(state: CodeFixState) -> CodeFixState:
    print("[LangGraph] save_final_message")

    decision = state.get("skill_decision", {})
    skill_result = state.get("skill_result")

    if hasattr(skill_result, "success"):
        success = skill_result.success
        message = skill_result.message
        data = skill_result.data
    elif isinstance(skill_result, dict):
        success = skill_result.get("success")
        message = skill_result.get("message")
        data = skill_result.get("data", {})
    else:
        success = False
        message = "Unknown skill result."
        data = {}

    state["final_message"] = (
        f"CodeFix Agent finished.\n"
        f"Selected Skill: {decision.get('skill_name')}\n"
        f"Reason: {decision.get('reason')}\n"
        f"Success: {success}\n"
        f"Message: {message}\n"
        f"Report: {data.get('report_path', '')}\n"
        f"Fixed File: {data.get('fixed_file_path', '')}"
    )

    return state


def build_codefix_graph():
    graph = StateGraph(CodeFixState)

    graph.add_node("detect_language", detect_language_node)
    graph.add_node("route_skill", route_skill_node)
    graph.add_node("remember_start", remember_start_node)
    graph.add_node("run_skill", run_skill_node)
    graph.add_node("remember_finish", remember_finish_node)
    graph.add_node("save_final_message", save_final_message_node)

    graph.set_entry_point("detect_language")
    graph.add_edge("detect_language", "route_skill")
    graph.add_edge("route_skill", "remember_start")
    graph.add_edge("remember_start", "run_skill")
    graph.add_edge("run_skill", "remember_finish")
    graph.add_edge("remember_finish", "save_final_message")
    graph.add_edge("save_final_message", END)

    return graph.compile()


def run_agent_graph(initial_state: dict) -> dict:
    app = build_codefix_graph()
    return app.invoke(initial_state)


def main():
    print("=== AgentGraph Test ===")

    single_file_state = {
        "source_file_path": str(BASE_DIR / "demo_inputs" / "buggy_add.py"),
        "project_path": "",
        "user_requirement": "Fix the add function. It should return the sum of a and b.",
        "test_command": "",
        "language": "python",
    }

    result = run_agent_graph(single_file_state)
    print(result["final_message"])


if __name__ == "__main__":
    main()