from pathlib import Path
from datetime import datetime
import json
import os


BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_store"
LOCAL_MEMORY_PATH = MEMORY_DIR / "memory.json"


class MemoryManager:
    """
    Redis-first memory manager with local JSON fallback.

    Three memory layers:
    1. short_term: current task state
    2. episodic: historical repair cases
    3. procedural: repair rules and skill routing experience
    """

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = None
        self.backend = "json"

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._init_local_memory()
        self._try_connect_redis()

    def _try_connect_redis(self) -> None:
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

    def remember_episodic(self, case: dict) -> None:
        """
        Save a historical repair case.
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
        List historical repair cases.
        """
        if self.backend == "redis":
            key = "codefix:episodic"
            items = self.redis_client.lrange(key, -limit, -1)
            return [json.loads(item) for item in items]

        data = self._load_local_memory()
        return data["episodic"][-limit:]

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

    def describe_backend(self) -> str:
        return self.backend


def main():
    print("=== Day 20 Memory Manager Test ===")

    memory = MemoryManager()

    print("memory backend:", memory.describe_backend())

    task_id = "demo_task_001"

    memory.remember_short_term(
        task_id,
        {
            "language": "python",
            "current_step": "generate_patch",
            "error_type": "AssertionError",
        },
    )

    memory.remember_episodic(
        {
            "language": "python",
            "error_type": "AssertionError",
            "fix_summary": "Changed subtraction to addition.",
            "success": True,
        }
    )

    memory.remember_procedural(
        "python_default_test_command",
        {
            "language": "python",
            "command": "pytest",
        },
    )

    print("\nshort term:")
    print(memory.get_short_term(task_id))

    print("\nepisodic:")
    print(memory.list_episodic(limit=3))

    print("\nprocedural:")
    print(memory.get_procedural("python_default_test_command"))

    print("\nMemory manager test finished.")


if __name__ == "__main__":
    main()