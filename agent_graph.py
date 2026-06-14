from pathlib import Path
import sys
from typing import TypedDict, Any

from langgraph.graph import StateGraph, END


BASE_DIR = Path(__file__).resolve().parent # 找到当前文件的绝对路径，并返回其父目录的路径，作为项目的基础目录

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SKILLS_DIR = BASE_DIR / "skills"  #找到 skills 文件夹

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

from language_detector import detect_language_from_file, detect_main_language
from skill_router import route_skill
from memory_manager import MemoryManager
from single_file_fix_skill import SingleFileFixSkill
from python_test_fix_skill import PythonTestFixSkill
from project_static_fix_skill import ProjectStaticFixSkill


class CodeFixState(TypedDict, total=False):  #定义整个 Agent 流程中传来传去的数据格式，这些字段不一定每个节点都会用到，所以 total=False 表示这些字段都是可选的
    source_file_path: str
    project_path: str
    user_requirement: str
    test_command: str
    language: str
    skill_decision: dict
    skill_result: Any
    memory_backend: str
    final_message: str


def detect_language_node(state: CodeFixState) -> CodeFixState:  #这个节点负责检测输入的代码是用什么编程语言写的，或者说这个修复任务涉及到什么编程语言。它会根据输入状态中的信息来判断语言，并把结果存回状态中，供后续节点使用。
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

    if source_file_path:  #如果有单个文件路径，尝试从文件检测语言
        state["language"] = detect_language_from_file(source_file_path)
        return state

    if project_path:  #如果有项目路径，尝试从项目检测主要语言，对zip
        state["language"] = detect_main_language(project_path)
        return state

    state["language"] = "unknown"
    return state


def route_skill_node(state: CodeFixState) -> CodeFixState:  #这个节点负责根据检测到的语言和用户需求来决定使用哪个修复技能
    print("[LangGraph] route_skill")

    state["skill_decision"] = route_skill(state)
    return state


def remember_start_node(state: CodeFixState) -> CodeFixState:  #这个节点负责在任务开始时记住相关信息，比如语言、技能决策、输入文件路径等，以便后续分析和改进。它使用 MemoryManager 来存储这些信息。
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


def run_skill_node(state: CodeFixState) -> CodeFixState:  #这个节点负责运行选定的修复技能
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
        state["skill_result"] = {    #如果技能名称不匹配任何已实现的技能，则返回一个默认的结果，表示技能未实现
            "success": False,
            "skill_name": skill_name,
            "message": f"Skill not implemented yet: {skill_name}",
            "data": {},
        }
        return state

    result = skill.run(state)
    state["skill_result"] = result
    return state


def remember_finish_node(state: CodeFixState) -> CodeFixState: #这个节点负责在任务结束时记住相关信息，比如技能执行的结果、成功与否、生成的修复文件路径等，以便后续分析和改进。它使用 MemoryManager 来存储这些信息。
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


def save_final_message_node(state: CodeFixState) -> CodeFixState:  #这个节点负责生成一个最终的消息，包含整个修复过程的总结信息，比如选择了哪个技能、为什么选择它、技能执行的结果等，并把这个消息存回状态中，供前端展示或者日志记录使用。
    print("[LangGraph] save_final_message")

    decision = state.get("skill_decision", {})
    skill_result = state.get("skill_result")

    if hasattr(skill_result, "success"):  # 如果技能结果是一个对象，并且具有 success 属性，则从中提取成功状态、消息和数据
        success = skill_result.success
        message = skill_result.message
        data = skill_result.data
    elif isinstance(skill_result, dict):   #如果技能结果是一个字典，则从中提取成功状态、消息和数据
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


def build_codefix_graph():  # 这个函数负责构建整个 Agent 的流程图，定义各个节点和它们之间的连接关系。它使用 StateGraph 来创建一个有向图，节点是上面定义的函数，边表示执行顺序。最后返回编译好的图对象。
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


def run_agent_graph(initial_state: dict) -> dict:  #这个函数负责运行整个 Agent 流程图，接受一个初始状态字典作为输入，调用 build_codefix_graph 来构建图，然后执行图并返回最终状态的字典形式。
    app = build_codefix_graph()
    return app.invoke(initial_state)


def main():  #这个函数是一个简单的测试函数，用来验证整个 Agent 流程图是否能够正确运行。它定义了一些测试用例，调用 run_agent_graph 来执行流程，并打印最终的消息结果。
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