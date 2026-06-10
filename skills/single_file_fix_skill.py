from pathlib import Path
import sys


CURRENT_DIR = Path(__file__).resolve().parent
CODEFIX_DIR = CURRENT_DIR.parent

if str(CODEFIX_DIR) not in sys.path:
    sys.path.insert(0, str(CODEFIX_DIR))

from base_skill import BaseFixSkill, SkillResult
from single_file_runner import run_single_file_repair


class SingleFileFixSkill(BaseFixSkill):
    """
    Skill for single-file repair tasks.

    It is used when the user uploads one source file and provides
    a natural-language repair requirement, without a test command.
    """

    skill_name = "SingleFileFixSkill"

    def run(self, task_state: dict) -> SkillResult:
        source_file_path = task_state.get("source_file_path", "")
        user_requirement = task_state.get("user_requirement", "")

        if not source_file_path:
            return SkillResult(
                success=False,
                skill_name=self.skill_name,
                message="source_file_path is required.",
                data={},
            )

        if not user_requirement:
            return SkillResult(
                success=False,
                skill_name=self.skill_name,
                message="user_requirement is required.",
                data={},
            )

        result = run_single_file_repair(
            source_file_path=source_file_path,
            user_requirement=user_requirement,
        )

        return SkillResult(
            success=result["success"],
            skill_name=self.skill_name,
            message="Single-file repair finished.",
            data=result,
        )


def main():
    print("=== Day 20 SingleFileFixSkill Test ===")

    demo_file = CODEFIX_DIR / "demo_inputs" / "buggy_add.py"

    skill = SingleFileFixSkill()
    result = skill.run(
        {
            "source_file_path": str(demo_file),
            "user_requirement": "Fix the add function. It should return the sum of a and b.",
        }
    )

    print("success:", result.success)
    print("skill_name:", result.skill_name)
    print("message:", result.message)

    if result.data:
        print("task_id:", result.data["task_info"]["task_id"])
        print("language:", result.data["language"])
        print("fixed_file_path:", result.data["fixed_file_path"])
        print("report_path:", result.data["report_path"])
        print("\nDIFF:")
        print(result.data["diff_text"])

    print("\nSingleFileFixSkill test finished.")


if __name__ == "__main__":
    main()