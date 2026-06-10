@echo off
echo Starting Web Multi-Language CodeFix Agent...

call conda activate agent-learning

E:
cd E:\agent-learning-projects

uvicorn agent_harness_projects.codefix_agent.web_app:app --host 127.0.0.1 --port 8000

pause