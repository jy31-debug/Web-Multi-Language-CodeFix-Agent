from dataclasses import dataclass, asdict


@dataclass
class SkillDecision:
    skill_name: str
    reason: str
    confidence: float
    language: str
    task_type: str


class SkillRouter:
    def route(self, task_state: dict) -> dict:
        language = (task_state.get("language") or "unknown").lower()
        source_file_path = task_state.get("source_file_path", "") or ""
        project_path = task_state.get("project_path", "") or ""
        test_command = task_state.get("test_command", "") or ""

        if project_path and not test_command.strip():
            return asdict(
                SkillDecision(
                    skill_name="ProjectStaticFixSkill",
                    reason="Detected uploaded project without test command. Use static project repair.",
                    confidence=0.82,
                    language=language,
                    task_type="project_static_repair",
                )
            )

        if language == "python" and test_command.strip():
            return asdict(
                SkillDecision(
                    skill_name="PythonTestFixSkill",
                    reason="Detected Python project with test command.",
                    confidence=0.9,
                    language=language,
                    task_type="python_test_repair",
                )
            )

        if source_file_path:
            return asdict(
                SkillDecision(
                    skill_name="SingleFileFixSkill",
                    reason="Detected single uploaded source file.",
                    confidence=0.85,
                    language=language,
                    task_type="single_file_repair",
                )
            )

        if language == "java":
            return asdict(
                SkillDecision(
                    skill_name="JavaCompileFixSkill",
                    reason="Detected Java task.",
                    confidence=0.65,
                    language=language,
                    task_type="java_compile_repair",
                )
            )

        if language in ["c", "cpp"]:
            return asdict(
                SkillDecision(
                    skill_name="CCompileFixSkill",
                    reason="Detected C/C++ task.",
                    confidence=0.65,
                    language=language,
                    task_type="c_compile_repair",
                )
            )

        if language in ["javascript", "typescript"]:
            return asdict(
                SkillDecision(
                    skill_name="JSTestFixSkill",
                    reason="Detected JavaScript/TypeScript task.",
                    confidence=0.65,
                    language=language,
                    task_type="js_test_repair",
                )
            )

        return asdict(
            SkillDecision(
                skill_name="SingleFileFixSkill",
                reason="Fallback to single file repair.",
                confidence=0.5,
                language=language,
                task_type="fallback",
            )
        )


def route_skill(task_state: dict) -> dict:
    router = SkillRouter()
    return router.route(task_state)


def main():
    print("=== SkillRouter Test ===")

    cases = [
        {
            "language": "python",
            "source_file_path": "buggy_add.py",
            "project_path": "",
            "test_command": "",
        },
        {
            "language": "python",
            "source_file_path": "",
            "project_path": "demo_project",
            "test_command": "pytest",
        },
        {
            "language": "python",
            "source_file_path": "",
            "project_path": "demo_project",
            "test_command": "",
        },
    ]

    for case in cases:
        print(route_skill(case))


if __name__ == "__main__":
    main()