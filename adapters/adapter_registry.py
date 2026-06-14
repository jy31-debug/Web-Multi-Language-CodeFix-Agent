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
        adapter = self.get_adapter(language)   #根据语言获取对应的适配器，如果没有适配器，就返回一个包含错误信息的字典，告诉调用者这个语言不受支持。如果有适配器，就调用适配器的 parse_error_log 方法来解析错误日志，并返回解析结果。

        if adapter is None:
            return {
                "language": language,
                "error_type": "UnknownLanguageError",
                "raw_log_preview": log_text[:1000],
            }

        return adapter.parse_error_log(log_text)  #调用适配器的 parse_error_log 方法（并非自己本身）来解析错误日志，并返回解析结果。这个方法的实现会根据不同语言的错误日志格式来提取关键信息，比如错误类型、错误位置、相关代码片段等，以便后续生成修复提示时使用。

    def build_repair_hint(self, language: str, parsed_error: dict) -> str:
        adapter = self.get_adapter(language)

        if adapter is None:
            return "No adapter is available for this language."

        return adapter.build_repair_hint(parsed_error)


def get_adapter(language: str):  #这是一个全局函数，提供了一个简化的接口来获取适配器实例。它内部创建了一个 AdapterRegistry 实例，并调用AdapterRegistry里面的 get_adapter 方法来获取对应语言的适配器。这种设计允许其他模块直接调用 get_adapter(language) 来获取适配器，而不需要关心 AdapterRegistry 的具体实现细节。
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