import re
from pathlib import Path


class JavaAdapter:
    language = "java"

    def detect_project_type(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "pom.xml").exists():
            return "java_maven_project"

        if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            return "java_gradle_project"

        return "java_single_file_or_javac_project"

    def get_default_check_command(self, project_path: str) -> str:
        project_type = self.detect_project_type(project_path)

        if project_type == "java_maven_project":
            return "mvn test"

        if project_type == "java_gradle_project":
            return "gradle test"

        java_files = list(Path(project_path).rglob("*.java"))
        if java_files:
            return f"javac {java_files[0].name}"

        return "javac Main.java"

    def parse_error_log(self, log_text: str) -> dict:
        error_type = "JavaError"
        file_name = ""
        line_number = -1

        if "cannot find symbol" in log_text:
            error_type = "CannotFindSymbol"
        elif "NullPointerException" in log_text:
            error_type = "NullPointerException"
        elif "incompatible types" in log_text:
            error_type = "IncompatibleTypes"
        elif "error:" in log_text:
            error_type = "CompileError"

        match = re.search(r"([A-Za-z0-9_]+\.java):(\d+)", log_text)
        if match:
            file_name = match.group(1)
            line_number = int(match.group(2))

        return {
            "language": self.language,
            "error_type": error_type,
            "file_name": file_name,
            "line_number": line_number,
            "raw_log_preview": log_text[:1000],
        }

    def build_repair_hint(self, parsed_error: dict) -> str:
        return (
            f"This is a Java repair task. "
            f"Detected error type: {parsed_error.get('error_type', 'JavaError')}. "
            f"Focus on Java compile/runtime error location and return a corrected Java file."
        )


def main():
    print("=== JavaAdapter Test ===")
    adapter = JavaAdapter()
    sample_log = "Main.java:7: error: cannot find symbol"
    parsed = adapter.parse_error_log(sample_log)
    print("language:", adapter.language)
    print("project_type:", adapter.detect_project_type("."))
    print("default_command:", adapter.get_default_check_command("."))
    print("parsed:", parsed)
    print("hint:", adapter.build_repair_hint(parsed))


if __name__ == "__main__":
    main()