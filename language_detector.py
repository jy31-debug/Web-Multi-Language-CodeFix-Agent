from pathlib import Path


LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".js": "javascript",
    ".ts": "typescript",
}


def detect_language_from_file(file_path: str) -> str:
    """
    Detect programming language from a single file extension.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    return LANGUAGE_EXTENSIONS.get(suffix, "unknown")


def detect_languages_in_directory(directory_path: str) -> dict:
    """
    Detect all programming languages in a directory.
    """
    directory = Path(directory_path)

    if not directory.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory_path}")

    language_counts = {}

    for file_path in directory.rglob("*"):
        if file_path.is_file():
            language = detect_language_from_file(str(file_path))

            if language != "unknown":
                language_counts[language] = language_counts.get(language, 0) + 1

    return language_counts


def detect_main_language(directory_path: str) -> str:
    """
    Detect the main language of a project directory.

    The main language is the language with the largest number of source files.
    """
    language_counts = detect_languages_in_directory(directory_path)

    if not language_counts:
        return "unknown"

    return max(language_counts.items(), key=lambda item: item[1])[0]


def get_default_check_command(language: str) -> str:
    """
    Return a default check command for each language.

    This is only a fallback. In the Web version, the user can still provide
    a custom test command.
    """
    if language == "python":
        return "pytest"
    if language == "java":
        return "javac Main.java"
    if language == "c":
        return "gcc main.c -o main.exe"
    if language == "cpp":
        return "g++ main.cpp -o main.exe"
    if language == "javascript":
        return "node main.js"
    if language == "typescript":
        return "npm test"

    return ""


def main():
    print("=== Day 19 Language Detector Test ===")

    test_files = [
        "example.py",
        "Main.java",
        "main.c",
        "main.cpp",
        "app.js",
        "index.ts",
        "README.md",
    ]

    for file_name in test_files:
        language = detect_language_from_file(file_name)
        command = get_default_check_command(language)
        print(f"{file_name} -> language: {language}, default command: {command}")

    print("\nLanguage detector test finished.")


if __name__ == "__main__":
    main()