import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from python_adapter import PythonAdapter
from java_adapter import JavaAdapter
from c_adapter import CAdapter
from js_adapter import JSAdapter


class AdapterRegistry:
    def __init__(self):
        self.adapters = {
            "python": PythonAdapter(),
            "java": JavaAdapter(),
            "c": CAdapter(),
            "cpp": CAdapter(),
            "javascript": JSAdapter(),
            "typescript": JSAdapter(),
        }

    def get_adapter(self, language: str):
        language = (language or "").lower().strip()
        return self.adapters.get(language)

    def list_supported_languages(self):
        return list(self.adapters.keys())

    def get_default_check_command(self, language: str, project_path: str) -> str:
        adapter = self.get_adapter(language)

        if adapter is None:
            return ""

        return adapter.get_default_check_command(project_path)

    def parse_error_log(self, language: str, log_text: str) -> dict:
        adapter = self.get_adapter(language)

        if adapter is None:
            return {
                "language": language,
                "error_type": "UnknownLanguageError",
                "raw_log_preview": log_text[:1000],
            }

        return adapter.parse_error_log(log_text)

    def build_repair_hint(self, language: str, parsed_error: dict) -> str:
        adapter = self.get_adapter(language)

        if adapter is None:
            return "No adapter is available for this language."

        return adapter.build_repair_hint(parsed_error)


def get_adapter(language: str):
    registry = AdapterRegistry()
    return registry.get_adapter(language)


def main():
    print("=== AdapterRegistry Test ===")

    registry = AdapterRegistry()

    print("supported languages:")
    print(registry.list_supported_languages())

    test_cases = [
        ("python", "AssertionError: expected 5"),
        ("java", "Main.java:7: error: cannot find symbol"),
        ("c", "main.c:10: error: expected ';' before return"),
        ("javascript", "ReferenceError: x is not defined"),
        ("unknown", "some error"),
    ]

    for language, log_text in test_cases:
        print()
        print("language:", language)

        parsed = registry.parse_error_log(language, log_text)
        print("parsed:", parsed)

        hint = registry.build_repair_hint(language, parsed)
        print("hint:", hint)


if __name__ == "__main__":
    main()