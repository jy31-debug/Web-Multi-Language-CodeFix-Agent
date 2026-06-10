from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SkillResult:
    """
    Standard output returned by all CodeFix skills.
    """
    success: bool
    skill_name: str
    message: str
    data: dict[str, Any]


class BaseFixSkill(ABC):
    """
    Base class for all CodeFix skills.

    A skill is a repair capability selected by SkillRouter.
    For example:
    - SingleFileFixSkill
    - PythonTestFixSkill
    - JavaCompileFixSkill
    - CCompileFixSkill
    - JSTestFixSkill
    """

    skill_name: str = "BaseFixSkill"

    @abstractmethod
    def run(self, task_state: dict) -> SkillResult:
        """
        Run the skill with a task state.
        """
        raise NotImplementedError