# CodeFix Agent

A web-based multi-language code repair agent powered by LangGraph, Skill Routing, official MCP tools, and memory-assisted repair.

CodeFix Agent allows users to upload a buggy code project as a ZIP file, automatically detects the project language and task type, selects the proper repair skill, runs tests, generates code patches, writes back the fixed source file, and produces downloadable repair reports, error logs, diffs, and trace logs.

---

## 1. Project Overview

CodeFix Agent is designed as a practical code repair agent rather than a simple chatbot.

The system can:

* Accept project ZIP upload from a Web UI
* Detect programming language and task type
* Route the task to the correct repair skill
* Run test commands such as `pytest`
* Analyze test failures
* Generate fixed code with an LLM
* Use memory to retrieve previous repair experience
* Use official MCP-based tools for tool execution
* Generate repair reports, fixed files, error logs, and trace logs
* Return a structured repair result through the Web UI

The current stable demo focuses on Python test-driven repair, where the agent repairs a buggy Python project based on failing pytest cases.

---

## 2. Key Features

### Web-based ZIP Project Repair

Users can upload a `.zip` project through the browser. The system extracts the project into a task workspace and runs the repair workflow automatically.

### LangGraph Workflow Orchestration

The repair process is organized as a LangGraph workflow:

```text
detect_language
→ route_skill
→ remember_start
→ run_skill
→ remember_finish
→ save_final_message
```

This makes the repair process clear, modular, and extensible.

### Skill Router

The Skill Router analyzes the uploaded project and selects the proper repair skill.

Current supported skill:

```text
PythonTestFixSkill
```

It is used when the project is detected as a Python project with test-driven repair requirements.

### Official MCP Integration

The project integrates the official MCP Python SDK.

A test-driven repair requirements.

### Official MCP Integration

The project integrates the official MCP Python SDK dedicated CodeFix MCP Server is implemented using `FastMCP`, exposing tools such as:

```text
read_file
write_file
run_command
generate_code_patch
show_diff
save_report
```

The agent uses an official MCP Client to connect to the MCP Server through stdio transport and call tools through the MCP protocol.

### Memory-assisted Repair

The project includes a `MemoryManager` with three memory layers:

```text
short_term   current task state
episodic     historical repair cases
procedural   repair rules and routing experience
```

The current repair flow uses episodic memory to retrieve previous repair experience and pass it into the LLM as reference context.

### Test-driven Code Repair

For Python projects, the agent runs pytest, analyzes the error log, generates code patches, writes the repaired source code back into the project, and reruns tests.

### Repair Artifacts

Each repair task generates a structured workspace:

```text
workspaces/task_xxx/
├── uploaded/
├── project/
├── error_logs/
├── reports/
├── traces/
└── outputs/
```

Generated artifacts include:

```text
fixed source code
repair report
pytest error log
trace log
diff output
```

---

## 3. System Architecture

```text
User
 │
 │ uploads ZIP project
 ▼
Web UI / FastAPI
 │
 ▼
LangGraph Agent Workflow
 │
 ├── detect_language
 │
 ├── route_skill
 │     └── Skill Router selects PythonTestFixSkill
 │
 ├── remember_start
 │     └── MemoryManager saves task state
 │
 ├── run_skill
 │     └── PythonTestFixSkill
 │          ├── runs pytest
 │          ├── parses error logs
 │          ├── retrieves repair memories
 │          ├── calls official MCP tools
 │          ├── generates code patch
 │          ├── writes fixed code
 │          └── reruns tests
 │
 ├── remember_finish
 │
 └── save_final_message
```

---

## 4. Official MCP Design

This project does not use a simple local tool dictionary as the final implementation.

It uses an official MCP Client and MCP Server structure:

```text
PythonTestFixSkill
→ OfficialMCPClient
→ stdio transport
→ CodeFix MCP Server
→ MCP tools
```

### CodeFix MCP Server

File:

```text
codefix_mcp_server.py
```

This server exposes tools through official MCP `FastMCP` decorators.

Example tools:

```text
run_command          run pytest or shell commands
generate_code_patch  call the LLM patch generator
show_diff            generate unified diff
save_report          save Markdown reports
read_file            read local files
write_file           write local files
```

### Official MCP Client

File:

```text
official_mcp_client.py
```

The client connects to the CodeFix MCP Server through stdio transport, initializes an MCP session, lists available tools, and calls tools through MCP.

For Windows compatibility, the command execution tool includes a safe local subprocess fallback if MCP stdio transport encounters runtime issues while running pytest.

---

## 5. Memory Design

File:

```text
memory_manager.py
```

The memory system supports Redis-first storage with JSON fallback.

If Redis is available, the system uses Redis.
If Redis is not available, it automatically falls back to:

```text
memory_store/memory.json
```

### Memory Layers

```text
short_term
```

Stores the current task state, such as task ID, project path, selected skill, and repair stage.

```text
episodic
```

Stores historical repair cases, including error type, user requirement, fix summary, diff preview, and repair success.

```text
procedural
```

Stores reusable repair rules and routing experience. This layer is reserved for future enhancement.

---

## 6. Python Repair Flow

The Python repair skill follows this process:

```text
1. Receive project path and test command
2. Run pytest
3. Save pytest error log
4. Parse error type and failed test information
5. Locate source file
6. Retrieve historical repair memories
7. Call MCP tool generate_code_patch
8. Apply deterministic test-guided safety fixes
9. Generate diff through MCP tool show_diff
10. Write fixed code back to project
11. Rerun pytest
12. Save report, fixed file, error log, and trace log
13. Return final success status
```

---

## 7. Demo Result

Demo project:

```text
demo_bank_project.zip
```

The project contains several bugs in a bank account system:

```text
deposit logic error
withdraw logic error
transfer logic error
unfreeze logic error
compound interest logic error
```

Final Web UI result:

```text
Success: True
Message: Python test-driven repair finished.
```

Manual pytest result:

```text
6 passed in 0.02s
```

Generated output:

```text
reports/python_test_fix_report.md
outputs/fixed_bank_account.py
error_logs/python_test_error_log.txt
traces/python_test_fix_trace.txt
```

Example diff:

```diff
-        self.balance -= amount
+        self.balance += amount
```

```diff
-            return self.balance - amount
+            raise ValueError("Insufficient funds")
```

```diff
-        target_account.withdraw(amount)
+        target_account.deposit(amount)
```

```diff
-        self.is_frozen = True
+        self.is_frozen = False
```

```diff
-        balance = balance - balance * annual_rate
+        balance = balance + balance * annual_rate
```

---

## 8. Tech Stack

```text
Python
FastAPI
Uvicorn
LangGraph
LangChain
OpenAI-compatible LLM API
DeepSeek API
Official MCP Python SDK
pytest
Redis optional
JSON memory fallback
HTML Web UI
```

---

## 9. Project Structure

```text
CodeFix-Agent-GitHub/
├── web_app.py
├── agent_graph.py
├── codefix_mcp_server.py
├── official_mcp_client.py
├── llm_patch_generator.py
├── memory_manager.py
├── requirements.txt
├── README.md
│
├── skills/
│   ├── base_skill.py
│   └── python_test_fix_skill.py
│
├── adapters/
│   └── adapter_registry.py
│
├── memory_store/
│   └── memory.json
│
└── workspaces/
    └── task_xxx/
        ├── uploaded/
        ├── project/
        ├── error_logs/
        ├── reports/
        ├── traces/
        └── outputs/
```

Note:

```text
memory_store/
workspaces/
.env
__pycache__/
.pytest_cache/
```

should not be committed to GitHub.

---

## 10. Installation

Create and activate a Python environment.

Example with Conda:

```powershell
conda create -n agent-learning python=3.11
conda activate agent-learning
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

---

## 11. Environment Variables

Create a `.env` file in the project root.

Example:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

REDIS_URL=redis://localhost:6379/0
```

Do not upload `.env` to GitHub.

A safe `.env.example` file can be provided instead:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

REDIS_URL=redis://localhost:6379/0
```

---

## 12. Run the Web App

Start the web server:

```powershell
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

If port `8000` is already in use, use another port:

```powershell
uvicorn web_app:app --host 127.0.0.1 --port 8001
```

Open the browser:

```text
http://127.0.0.1:8000
```

or:

```text
http://127.0.0.1:8001
```

Upload a ZIP project and run the agent.

---

## 13. Test Official MCP Client

Run:

```powershell
python official_mcp_client.py
```

Expected output includes:

```text
Available MCP tools:
['read_file', 'write_file', 'run_command', 'generate_code_patch', 'show_diff', 'save_report']
```

This confirms that the MCP Client can connect to the CodeFix MCP Server and discover available tools.

---

## 14. Example Usage

1. Start the Web App.
2. Open the browser.
3. Upload a Python project ZIP.
4. Enter test command:

```text
pytest
```

5. Click run.
6. Download generated artifacts:

```text
fixed code
repair report
error log
trace log
```

---

## 15. Current Limitations

The current stable implementation focuses on Python pytest-based repair.

Multi-language support is designed through the Skill Router, but the current stable demo mainly validates:

```text
Python project repair
pytest failure analysis
official MCP tool invocation
memory-assisted repair
report generation
```

Future extensions can add:

```text
Java compile repair
C compile repair
JavaScript test repair
multi-file project repair
stronger static analysis
official remote MCP server support
more advanced memory retrieval
```

---

## 16. Future Plan

Planned improvements:

```text
1. Add more language-specific repair skills
2. Expand Skill Router for Java, C, JavaScript, and TypeScript
3. Add project-level memory isolation
4. Support official remote MCP servers
5. Add Docker-based sandbox execution
6. Improve frontend result visualization
7. Add benchmark evaluation with multiple buggy projects
```

---

## 17. Status

Current status:

```text
Web upload: working
Language detection: working
Skill Router: working
PythonTestFixSkill: working
Official MCP Client: working
CodeFix MCP Server: working
MemoryManager JSON fallback: working
Repair report generation: working
Final Python demo result: Success True
```

---

## 18. License

This project is for learning, research, and internship portfolio demonstration.
