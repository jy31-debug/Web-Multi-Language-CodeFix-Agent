\# Web Multi-Language CodeFix Agent



A web-based multi-language CodeFix Agent MVP.



Users can upload a single source file or a zip project, describe the bug in natural language, and the agent will automatically route the task to different repair skills, call an LLM to generate fixes, and return fixed code, diff, and repair reports.



\## Features



\- FastAPI web interface

\- Single file code repair

\- Zip project upload

\- Multi-language adapter design

\- Skill Router

\- LangGraph workflow

\- LangChain + LLM patch generation

\- Python pytest-based test-driven repair

\- Multi-round repair loop

\- Static project repair without test scripts

\- Fixed project zip download

\- Sandbox runner prototype

\- MCP tool server prototype



\## Supported Task Routes



\### 1. Single File Repair



Upload one source file and describe the bug.



The system routes the task to:



`SingleFileFixSkill`



\### 2. Python Test-Driven Project Repair



Upload a zip project with pytest tests and provide a test command:



`pytest`



The system routes the task to:



`PythonTestFixSkill`



It runs tests, reads failure logs, repairs the source code, and can perform multiple repair rounds until tests pass or the repair limit is reached.



\### 3. Static Project Repair



Upload a zip project without test scripts and leave the test command empty.



The system routes the task to:



`ProjectStaticFixSkill`



It scans source files, skips test files, generates fixed files, and provides a downloadable fixed project zip.



\## Project Structure



```text

.

├── adapters/

├── skills/

├── templates/

├── agent\_graph.py

├── skill\_router.py

├── language\_detector.py

├── memory\_manager.py

├── task\_manager.py

├── llm\_patch\_generator.py

├── web\_app.py

├── sandbox\_runner.py

├── mcp\_server.py

├── Dockerfile

├── docker-compose.yml

├── run\_web.bat

├── requirements.txt

└── README.md

````



\## Local Run



Install dependencies:



```bash

pip install -r requirements.txt

```



Run the web app:



```bash

uvicorn web\_app:app --host 127.0.0.1 --port 8000

```



Or on Windows:



```bash

run\_web.bat

```



Open:



```text

http://127.0.0.1:8000

```



\## Environment Variables



The LLM API key should be configured locally and must not be committed to GitHub.



Example:



```text

DEEPSEEK\_API\_KEY=your\_api\_key\_here

```



Do not upload `.env` files.



\## Current Status



This is an MVP project. It focuses on the complete product loop:



Upload code → Route skill → Run repair → Generate diff/report → Download result



Future improvements may include stronger cross-file reasoning, safer sandbox isolation, richer frontend interaction, and more language-specific repair skills.



\## Tech Stack



\* Python

\* FastAPI

\* LangGraph

\* LangChain

\* LLM API

\* Pytest

\* Docker prototype

\* MCP tool server prototype





