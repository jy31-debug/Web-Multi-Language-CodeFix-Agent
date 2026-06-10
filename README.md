# Web Multi-Language CodeFix Agent

A web-based multi-language CodeFix Agent MVP.

This project allows users to upload a single source code file or a zip project, describe the bug in natural language, and let the agent automatically route the task, run repair skills, generate fixed code, produce diffs, and return repair reports.

## Why this project exists

Many code repair tools only work for a single file or require users to know exactly how to run tests.

This project is designed for a more realistic use case:

- A user uploads one buggy file and asks the agent to fix it.
- A user uploads a zip project with tests and provides a command such as `pytest`.
- A user uploads a zip project without tests and asks the agent to inspect and repair the source files.

The goal is to build a practical CodeFix Agent workflow instead of a simple one-shot code generation demo.

## Main Features

- FastAPI web interface
- Single source file repair
- Zip project upload
- Static project repair without test scripts
- Python pytest-based test-driven repair
- Multi-round repair loop
- Skill Router for automatic task routing
- LangGraph workflow orchestration
- LangChain and LLM-based patch generation
- Multi-language adapter design
- Fixed code, diff, and repair report generation
- Fixed project zip download
- Sandbox runner prototype
- MCP tool server prototype

## Task Routes

### Single File Repair

When the user uploads one source file and leaves the test command empty, the system routes the task to `SingleFileFixSkill`.

This route is suitable for simple code repair tasks.

Example user request:

`Fix the add function. It should return the sum of a and b.`

### Python Test-Driven Project Repair

When the user uploads a zip project and provides a pytest command, the system routes the task to `PythonTestFixSkill`.

Example test command:

`pytest`

This skill runs the tests, reads failure logs, repairs the source code, and can perform multiple repair rounds until tests pass or the repair limit is reached.

### Static Project Repair

When the user uploads a zip project but does not provide a test command, the system routes the task to `ProjectStaticFixSkill`.

This skill scans source code files, skips test files, generates repaired versions, and packages the fixed files into a downloadable zip file.

This route is useful when the uploaded project has no test scripts.

## Project Structure

- `adapters/`  
  Multi-language adapter modules.

- `skills/`  
  Code repair skills, including single-file repair, static project repair, and Python test-driven repair.

- `templates/`  
  FastAPI HTML frontend template.

- `agent_graph.py`  
  LangGraph workflow definition.

- `skill_router.py`  
  Routes tasks to different repair skills.

- `language_detector.py`  
  Detects source code language.

- `memory_manager.py`  
  Stores short-term and episodic task memory.

- `task_manager.py`  
  Manages uploaded files, workspaces, outputs, reports, and error logs.

- `llm_patch_generator.py`  
  Calls the LLM to generate code patches.

- `web_app.py`  
  FastAPI web application entry point.

- `sandbox_runner.py`  
  Sandbox command runner prototype.

- `mcp_server.py`  
  MCP tool server prototype.

- `Dockerfile` and `docker-compose.yml`  
  Deployment prototype files.

## Local Installation

Install dependencies:

`pip install -r requirements.txt`

Run the web app:

`uvicorn web_app:app --host 127.0.0.1 --port 8000`

Or on Windows:

`run_web.bat`

Then open:

`http://127.0.0.1:8000`

## Environment Variables

The LLM API key should be configured locally and must not be committed to GitHub.

Example:

`DEEPSEEK_API_KEY=your_api_key_here`

Do not upload `.env` files.

## Current Status

This is an MVP project.

The current version focuses on the complete product loop:

`Upload code → Route skill → Run repair → Generate diff and report → Download fixed result`

## Tech Stack

- Python
- FastAPI
- LangGraph
- LangChain
- LLM API
- Pytest
- Docker prototype
- MCP tool server prototype

## Future Work

- Improve cross-file reasoning
- Add stronger language-specific repair skills
- Improve frontend interaction
- Add safer sandbox isolation
- Add project-level dependency analysis
- Add richer evaluation examples
