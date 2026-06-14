from pathlib import Path
from datetime import datetime
import json
import os
import re
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_store"
LOCAL_MEMORY_PATH = MEMORY_DIR / "memory.json"


class MemoryManager:
    """
    CodeFix Agent memory manager.

    Three memory layers:
    1. short_term: current task state
    2. episodic: historical repair cases
    3. procedural: repair rules and routing experience

    Backend:
    - Redis first
    - Local JSON fallback
    """

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = None
        self.backend = "json"

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._init_local_memory()
        self._try_connect_redis()

    # =========================
    # Backend initialization
    # =========================

    def _try_connect_redis(self) -> None:
        """
        Try Redis first. If Redis is not available, use local JSON.
        """
        try:
            import redis

            client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()

            self.redis_client = client
            self.backend = "redis"
        except Exception:
            self.redis_client = None
            self.backend = "json"

    def _init_local_memory(self) -> None:
        """
        Create local memory file if it does not exist.
        """
        if not LOCAL_MEMORY_PATH.exists():
            data = {
                "short_term": {},
                "episodic": [],
                "procedural": {},
            }
            LOCAL_MEMORY_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _load_local_memory(self) -> dict:
        self._init_local_memory()
        return json.loads(LOCAL_MEMORY_PATH.read_text(encoding="utf-8"))

    def _save_local_memory(self, data: dict) -> None:
        LOCAL_MEMORY_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # =========================
    # Short-term memory
    # =========================

    def remember_short_term(self, task_id: str, state: dict) -> None:
        """
        Save current task state.
        """
        payload = {
            "task_id": task_id,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "state": state,
        }

        if self.backend == "redis":
            key = f"codefix:short_term:{task_id}"
            self.redis_client.set(key, json.dumps(payload, ensure_ascii=False))
            return

        data = self._load_local_memory()
        data["short_term"][task_id] = payload
        self._save_local_memory(data)

    def get_short_term(self, task_id: str) -> dict | None:
        """
        Get current task state.
        """
        if self.backend == "redis":
            key = f"codefix:short_term:{task_id}"
            value = self.redis_client.get(key)
            return json.loads(value) if value else None

        data = self._load_local_memory()
        return data["short_term"].get(task_id)

    # =========================
    # Episodic memory
    # =========================

    def remember_episodic(self, case: dict) -> None:
        """
        Save one historical repair case.

        Example case:
        {
            "skill_name": "PythonTestFixSkill",
            "language": "python",
            "error_type": "AssertionError",
            "user_requirement": "...",
            "error_log_preview": "...",
            "fix_summary": "...",
            "success": True,
            "diff_preview": "..."
        }
        """
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "case": case,
        }

        if self.backend == "redis":
            key = "codefix:episodic"
            self.redis_client.rpush(key, json.dumps(payload, ensure_ascii=False))
            return

        data = self._load_local_memory()
        data["episodic"].append(payload)
        self._save_local_memory(data)

    def list_episodic(self, limit: int = 10) -> list:
        """
        List recent historical repair cases.
        """
        if self.backend == "redis":
            key = "codefix:episodic"
            items = self.redis_client.lrange(key, -limit, -1)
            return [json.loads(item) for item in items]

        data = self._load_local_memory()
        return data["episodic"][-limit:]

    def search_episodic(self, query: str, top_k: int = 3) -> list[dict]:
        """
        Search similar historical repair cases.

        This is a simple keyword-based memory search.
        It is not ChromaDB yet, but it is enough to make memory participate
        in the repair workflow.
        """
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        memories = self.list_episodic(limit=200)
        scored = []

        for item in memories:
            case = item.get("case", {})

            memory_text = "\n".join(
                [
                    str(case.get("skill_name", "")),
                    str(case.get("language", "")),
                    str(case.get("error_type", "")),
                    str(case.get("user_requirement", "")),
                    str(case.get("error_log_preview", "")),
                    str(case.get("fix_summary", "")),
                    str(case.get("diff_preview", "")),
                ]
            )

            memory_tokens = self._tokenize(memory_text)
            score = len(query_tokens.intersection(memory_tokens))

            if score > 0:
                scored.append(
                    {
                        "score": score,
                        "created_at": item.get("created_at", ""),
                        "case": case,
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def build_retrieved_context(self, query: str, top_k: int = 3) -> str:
        """
        Build retrieved_context for LLM prompt.

        This text will be passed into generate_patch(..., retrieved_context=...).
        """
        results = self.search_episodic(query=query, top_k=top_k)

        if not results:
            return ""

        parts = [
            "Historical repair memories found. Use them only if they are relevant.",
            "Do not blindly copy old fixes. Current code and current test log are the main evidence.",
            "",
        ]

        for index, item in enumerate(results, start=1):
            case = item["case"]

            parts.append(
                f"""Memory {index}:
- Score: {item["score"]}
- Time: {item.get("created_at", "")}
- Skill: {case.get("skill_name", "")}
- Language: {case.get("language", "")}
- Error Type: {case.get("error_type", "")}
- Previous Requirement: {case.get("user_requirement", "")}
- Previous Success: {case.get("success", "")}
- Previous Fix Summary:
{case.get("fix_summary", "")}

- Previous Diff Preview:
{case.get("diff_preview", "")}
"""
            )

        return "\n".join(parts)

    # =========================
    # Procedural memory
    # =========================

    def remember_procedural(self, rule_name: str, rule_value: dict) -> None:
        """
        Save repair rules or routing rules.
        """
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "rule": rule_value,
        }

        if self.backend == "redis":
            key = f"codefix:procedural:{rule_name}"
            self.redis_client.set(key, json.dumps(payload, ensure_ascii=False))
            return

        data = self._load_local_memory()
        data["procedural"][rule_name] = payload
        self._save_local_memory(data)

    def get_procedural(self, rule_name: str) -> dict | None:
        """
        Get a procedural rule.
        """
        if self.backend == "redis":
            key = f"codefix:procedural:{rule_name}"
            value = self.redis_client.get(key)
            return json.loads(value) if value else None

        data = self._load_local_memory()
        return data["procedural"].get(rule_name)

    # =========================
    # Utilities
    # =========================

    def describe_backend(self) -> str:
        return self.backend

    def _tokenize(self, text: str) -> set[str]:
        """
        Simple tokenizer for English words, code tokens, and Chinese chunks.
        """
        return set(
            re.findall(
                r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[\u4e00-\u9fff]+",
                text.lower(),
            )
        )


def main():
    print("=== Memory Manager Test ===")

    memory = MemoryManager()
    print("memory backend:", memory.describe_backend())

    memory.remember_episodic(
        {
            "skill_name": "PythonTestFixSkill",
            "language": "python",
            "error_type": "AssertionError",
            "user_requirement": "修复银行账户系统里的余额计算错误。",
            "error_log_preview": "assert account.deposit, self.balance -= amount",
            "fix_summary": "Changed deposit logic from subtraction to addition.",
            "success": True,
            "diff_preview": "- self.balance -= amount\n+ self.balance += amount",
        }
    )

    query = "pytest AssertionError deposit self.balance -= amount"
    context = memory.build_retrieved_context(query=query, top_k=3)

    print("\nretrieved context:")
    print(context)

    print("\nMemory manager test finished.")


if __name__ == "__main__":
    main()