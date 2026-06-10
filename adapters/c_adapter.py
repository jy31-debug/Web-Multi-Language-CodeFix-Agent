import re
from pathlib import Path


class CAdapter:
    language = "c"

    def detect_project_type(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "Makefile").exists() or (path / "makefile").exists():
            return "c_make_project"

        if any(path.rglob("*.c")):
            return "c_single_file_or_gcc_project"

        if any(path.rglob("*.cpp")):
            return "cpp_single_file_or_gpp_project"

        return "unknown_c_project"

    def get_default_check_command(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "Makefile").exists() or (path / "makefile").exists():
            return "make"

        c_files = list(path.rglob("*.c"))
        if c_files:
            return f"gcc {c_files[0].name} -o main.exe"

        cpp_files = list(path.rglob("*.cpp"))
        if cpp_files:
            return f"g++ {cpp_files[0].name} -o main.exe"

        return "gcc main.c -o main.exe"

    def parse_error_log(self, log_text: str) -> dict:
        error_type = "CError"
        file_name = ""
        line_number = -1

        if "expected" in log_text and ";" in log_text:
            error_type = "SyntaxError"
        elif "undefined reference" in log_text:
            error_type = "UndefinedReference"
        elif "segmentation fault" in log_text.lower():
            error_type = "SegmentationFault"
        elif "error:" in log_text:
            error_type = "CompileError"

        match = re.search(r"([A-Za-z0-9_]+\.(c|cpp|h|hpp)):(\d+)", log_text)
        if match:
            file_name = match.group(1)
            line_number = int(match.group(3))

        return {
            "language": self.language,
            "error_type": error_type,
            "file_name": file_name,
            "line_number": line_number,
            "raw_log_preview": log_text[:1000],
        }

    def build_repair_hint(self, parsed_error: dict) -> str:
        return (
            f"This is a C/C++ repair task. "
            f"Detected error type: {parsed_error.get('error_type', 'CError')}. "
            f"Focus on compile errors, missing symbols, syntax errors, or memory errors."
        )


def main():
    print("=== CAdapter Test ===")
    adapter = CAdapter()
    sample_log = "main.c:10: error: expected ';' before return"
    parsed = adapter.parse_error_log(sample_log)
    print("language:", adapter.language)
    print("project_type:", adapter.detect_project_type("."))
    print("default_command:", adapter.get_default_check_command("."))
    print("parsed:", parsed)
    print("hint:", adapter.build_repair_hint(parsed))


if __name__ == "__main__":
    main()