import asyncio
import sqlite3
from contextlib import contextmanager

from app.models_memory import QueryMemoryRequest
from app.routers.chat_routes import StructuredChatAgent
from app.services.memory import chat_memory_middleware as mw_module
from app.services.memory import memory_hooks as hooks_module
from app.services.memory import memory_service as ms
from app.services.memory.chat_memory_middleware import get_chat_memory_middleware

_FAKE_CONN = None


@contextmanager
def _fake_db():
    global _FAKE_CONN
    if _FAKE_CONN is None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                importance TEXT NOT NULL,
                keywords TEXT,
                context TEXT,
                tags TEXT,
                related_task_id INTEGER,
                links TEXT,
                created_at TIMESTAMP,
                last_accessed TIMESTAMP,
                retrieval_count INTEGER,
                evolution_history TEXT,
                embedding_generated BOOLEAN,
                embedding_model TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding_vector TEXT NOT NULL,
                embedding_model TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
        _FAKE_CONN = conn
    try:
        yield _FAKE_CONN
    finally:
        pass


class _DummyLLM:
    def chat(self, *args, **kwargs):
        return {"content": "{}"}


class _DummyEmb:
    def get_single_embedding(self, text):
        return None

    def compute_similarity(self, a, b):
        return 0.0


async def _dummy_analyze(self, content):
    return {"keywords": [], "context": "General", "tags": []}


def test_memory_write_and_query(monkeypatch):
    # 强制开启记忆开关
    monkeypatch.setenv("MEMORY_AUTO_SAVE_ENABLED", "true")
    monkeypatch.setenv("MEMORY_RETRIEVE_ENABLED", "true")

    # reset singletons and patch deps
    mw_module._chat_memory_middleware = None
    hooks_module._memory_hooks = None
    ms._memory_service = None
    monkeypatch.setattr(ms, "get_db", _fake_db)
    monkeypatch.setattr(ms, "get_default_client", lambda: _DummyLLM())
    monkeypatch.setattr(ms, "get_embeddings_service", lambda: _DummyEmb())
    monkeypatch.setattr(ms.IntegratedMemoryService, "_analyze_content", _dummy_analyze)
    monkeypatch.setattr(
        ms.IntegratedMemoryService, "_get_conn", lambda self, session_id: _fake_db()
    )
    monkeypatch.setattr(
        ms.IntegratedMemoryService, "_get_conn", lambda self, session_id: _fake_db()
    )

    mw = mw_module.get_chat_memory_middleware()

    async def _save_and_query():
        mid = await mw.process_message(
            content="Important decision: adopt vector index",
            role="user",
            session_id="test-session-123",
            plan_id=42,
            force_save=True,
        )
        assert mid

        svc = ms.get_memory_service()
        req = QueryMemoryRequest(
            search_text="vector index",
            limit=5,
            min_similarity=0.0,
        )
        resp = await svc.query_memory(req)
        assert resp.total >= 1
        ids = [m.memory_id for m in resp.memories]
        assert mid in ids

    asyncio.run(_save_and_query())


def test_chat_prompt_includes_memories(monkeypatch):
    monkeypatch.setenv("MEMORY_AUTO_SAVE_ENABLED", "true")
    monkeypatch.setenv("MEMORY_RETRIEVE_ENABLED", "true")

    mw_module._chat_memory_middleware = None
    hooks_module._memory_hooks = None
    ms._memory_service = None
    monkeypatch.setattr(ms, "get_db", _fake_db)
    monkeypatch.setattr(ms, "get_default_client", lambda: _DummyLLM())
    monkeypatch.setattr(ms, "get_embeddings_service", lambda: _DummyEmb())
    monkeypatch.setattr(ms.IntegratedMemoryService, "_analyze_content", _dummy_analyze)

    agent = StructuredChatAgent(session_id="test-session-456")

    async def _run():
        # 先存一条记忆
        mw = get_chat_memory_middleware()
        await mw.process_message(
            content="Earlier decision: use redis cache",
            role="user",
            session_id="test-session-456",
            plan_id=None,
            force_save=True,
        )
        # 构造 prompt，检查是否注入记忆片段
        prompt = agent._build_prompt(
            "What cache should we use?",
            memory_snippets="- [knowledge/medium] use redis cache",
        )
        assert "Retrieved Memories" in prompt
        assert "redis cache" in prompt

    asyncio.run(_run())
