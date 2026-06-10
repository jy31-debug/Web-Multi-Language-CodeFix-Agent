from pathlib import Path


class PythonAdapter:
    language = "python"

    def detect_project_type(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "pytest.ini").exists() or (path / "tests").exists():
            return "python_pytest_project"

        if any(path.rglob("test_*.py")):
            return "python_pytest_project"

        return "python_single_file_or_script"

    def get_default_check_command(self, project_path: str) -> str:
        path = Path(project_path)

        if any(path.rglob("test_*.py")) or (path / "tests").exists():
            return "pytest"

        return "python main.py"

    def parse_error_log(self, log_text: str) -> dict:
        error_type = "UnknownError"

        for name in [
            "AssertionError",
            "RecursionError",
            "TypeError",
            "ValueError",
            "ImportError",
            "ModuleNotFoundError",
            "IndexError",
            "KeyError",
            "ZeroDivisionError",
        ]:
            if name in log_text:
                error_type = name
                break

        return {
            "language": self.language,
            "error_type": error_type,
            "raw_log_preview": log_text[:1000],
        }

    def build_repair_hint(self, parsed_error: dict) -> str:
        return (
            f"This is a Python repair task. "
            f"Detected error type: {parsed_error.get('error_type', 'UnknownError')}. "
            f"Use pytest output, source code, and tests to generate a safe fix."
        )


def main():
    print("=== PythonAdapter Test ===")
    adapter = PythonAdapter()
    print("language:", adapter.language)
    print("project_type:", adapter.detect_project_type("."))
    print("default_command:", adapter.get_default_check_command("."))
    print("parsed:", adapter.parse_error_log("AssertionError: expected 5"))
    print("hint:", adapter.build_repair_hint({"error_type": "AssertionError"}))


if __name__ == "__main__":
    main()