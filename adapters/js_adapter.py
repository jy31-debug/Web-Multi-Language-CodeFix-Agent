from pathlib import Path


class JSAdapter:
    language = "javascript"

    def detect_project_type(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "package.json").exists():
            return "node_or_npm_project"

        if any(path.rglob("*.js")):
            return "javascript_single_file_or_node_script"

        if any(path.rglob("*.ts")):
            return "typescript_project"

        return "unknown_js_project"

    def get_default_check_command(self, project_path: str) -> str:
        path = Path(project_path)

        if (path / "package.json").exists():
            return "npm test"

        js_files = list(path.rglob("*.js"))
        if js_files:
            return f"node {js_files[0].name}"

        return "node main.js"

    def parse_error_log(self, log_text: str) -> dict:
        error_type = "JavaScriptError"

        for name in [
            "ReferenceError",
            "TypeError",
            "SyntaxError",
            "RangeError",
            "Cannot find module",
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
            f"This is a JavaScript/TypeScript repair task. "
            f"Detected error type: {parsed_error.get('error_type', 'JavaScriptError')}. "
            f"Focus on runtime error, syntax error, missing import, or test failure."
        )


def main():
    print("=== JSAdapter Test ===")
    adapter = JSAdapter()
    sample_log = "ReferenceError: x is not defined"
    parsed = adapter.parse_error_log(sample_log)
    print("language:", adapter.language)
    print("project_type:", adapter.detect_project_type("."))
    print("default_command:", adapter.get_default_check_command("."))
    print("parsed:", parsed)
    print("hint:", adapter.build_repair_hint(parsed))


if __name__ == "__main__":
    main()