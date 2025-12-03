"""
Integrated Memory Service.

Combines Memory-MCP capabilities with existing system infrastructure
"""

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config.database_config import get_database_config
from ...database import get_db, plan_db_connection
from ...llm import get_default_client
from ...models_memory import (
    ImportanceLevel,
    MemoryEvolutionResult,
    MemoryItem,
    MemoryNote,
    MemoryStats,
    MemoryType,
    QueryMemoryRequest,
    QueryMemoryResponse,
    SaveMemoryRequest,
    SaveMemoryResponse,
)
from ..embeddings import get_embeddings_service

logger = logging.getLogger(__name__)


class IntegratedMemoryService:
    """集成记忆服务 - 复用现有基础设施"""

    def __init__(self):
        self.llm_client = get_default_client()
        self.embeddings_service = get_embeddings_service()
        self.evolution_threshold = 10  # 每10个记忆触发一次进化
        self.evolution_count = 0
        self._initialized_dbs: set[str] = set()
        self.session_dir = get_database_config().get_session_store_dir()
        try:
            from ...services.foundation.settings import get_settings
            settings = get_settings()
            self.text_similarity_default = getattr(settings, "memory_text_similarity", 1.0)
        except Exception:
            self.text_similarity_default = 1.0
        # 默认确保主库表存在（用于无 session 场景）
        with get_db() as conn:
            self._ensure_memory_tables(conn, db_key="main")

    @contextmanager
    def _get_conn(self, session_id: Optional[str]):
        """根据 session_id 选择主库或 session 专属库."""
        if session_id:
            safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
            path = self.session_dir / f"session_{safe_id}.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            with plan_db_connection(path) as conn:
                self._ensure_memory_tables(conn, db_key=f"session:{safe_id}")
                yield conn
        else:
            with get_db() as conn:
                self._ensure_memory_tables(conn, db_key="main")
                yield conn

    def _ensure_memory_tables(self, conn, db_key: str):
        """确保记忆相关的数据库表存在"""
        if db_key in self._initialized_dbs:
            return

        # 保底创建 tasks 表（部分部署场景未运行计划模块，避免外键错误）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY
            )
        """
        )

        # 记忆主表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                importance TEXT NOT NULL,
                keywords TEXT,
                context TEXT DEFAULT 'General',
                tags TEXT,
                related_task_id INTEGER,
                links TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retrieval_count INTEGER DEFAULT 0,
                evolution_history TEXT,
                embedding_generated BOOLEAN DEFAULT FALSE,
                embedding_model TEXT,
                FOREIGN KEY (related_task_id) REFERENCES tasks (id) ON DELETE SET NULL
            )
        """
        )

        # 记忆嵌入向量表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding_vector TEXT NOT NULL,
                embedding_model TEXT DEFAULT 'embedding-2',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (memory_id) REFERENCES memories (id) ON DELETE CASCADE
            )
        """
        )

        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_task_id ON memories(related_task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model ON memory_embeddings(embedding_model)")

        self._initialized_dbs.add(db_key)

    async def save_memory(self, request: SaveMemoryRequest) -> SaveMemoryResponse:
        """保存记忆到系统中"""
        try:
            # 生成记忆ID
            memory_id = str(uuid.uuid4())

            # 分析内容生成元数据（如果未提供）
            keywords = request.keywords or []
            context = request.context or "General"
            tags = request.tags or []

            # 补充 plan/session 标签
            if request.session_id and not any(tag.startswith("session:") for tag in tags):
                tags.append(f"session:{request.session_id}")
            if request.plan_id is not None and not any(tag.startswith("plan:") for tag in tags):
                tags.append(f"plan:{request.plan_id}")

            # 如果缺少元数据，使用LLM分析
            if not keywords or context == "General" or not tags:
                analysis = await self._analyze_content(request.content)
                if not keywords:
                    keywords = analysis.get("keywords", [])
                if context == "General":
                    context = analysis.get("context", "General")
                if not tags:
                    tags = analysis.get("tags", [])

            # 创建记忆笔记
            memory_note = MemoryNote(
                id=memory_id,
                content=request.content,
                memory_type=request.memory_type,
                importance=request.importance,
                keywords=keywords,
                context=context,
                tags=tags,
                related_task_id=request.related_task_id,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
            )

            # 保存到数据库（按 session 分库）
            await self._store_memory(memory_note, session_id=request.session_id)

            # 生成嵌入向量
            embedding_generated = await self._generate_embedding(memory_note, session_id=request.session_id)
            memory_note.embedding_generated = embedding_generated

            # 记忆进化处理
            await self._process_memory_evolution(memory_note, session_id=request.session_id)

            return SaveMemoryResponse(
                memory_id=memory_id,
                task_id=request.related_task_id,
                memory_type=request.memory_type,
                content=request.content,
                created_at=memory_note.created_at,
                embedding_generated=embedding_generated,
                keywords=keywords,
                context=context,
                tags=tags,
            )

        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            raise

    async def query_memory(self, request: QueryMemoryRequest) -> QueryMemoryResponse:
        """查询记忆"""
        try:
            start_time = datetime.now()
            query_all = request.search_text.strip() == "" or request.search_text.strip() == "*"
            query_text = "" if query_all else request.search_text

            # 构建查询条件
            where_conditions = []
            params = []

            if request.memory_types:
                type_placeholders = ",".join(["?" for _ in request.memory_types])
                where_conditions.append(f"memory_type IN ({type_placeholders})")
                params.extend([t.value for t in request.memory_types])

            # session 过滤（基于 tags 模糊匹配）
            if request.session_id:
                where_conditions.append("tags LIKE ?")
                params.append(f"%session:{request.session_id}%")
            # plan 过滤（基于 tags 模糊匹配）
            if request.plan_id is not None:
                where_conditions.append("tags LIKE ?")
                params.append(f"%plan:{request.plan_id}%")

            # 如果有嵌入向量，使用语义搜索
            memories = await self._semantic_search(
                query=query_text,
                query_all=query_all,
                where_conditions=where_conditions,
                params=params,
                limit=request.limit,
                min_similarity=request.min_similarity,
                session_id=request.session_id,
            )

            # 转换为响应格式
            memory_items = []
            for memory_data in memories:
                memory_items.append(
                    MemoryItem(
                        memory_id=memory_data["id"],
                        task_id=memory_data.get("related_task_id"),
                        memory_type=MemoryType(memory_data["memory_type"]),
                        content=memory_data["content"],
                        similarity=memory_data.get("similarity", 0.0),
                        created_at=memory_data["created_at"],
                        keywords=json.loads(memory_data.get("keywords", "[]")),
                        context=memory_data.get("context", "General"),
                        tags=json.loads(memory_data.get("tags", "[]")),
                        importance=ImportanceLevel(memory_data["importance"]),
                    )
                )

            search_time = (datetime.now() - start_time).total_seconds() * 1000

            return QueryMemoryResponse(memories=memory_items, total=len(memory_items), search_time_ms=search_time)

        except Exception as e:
            logger.error(f"Failed to query memory: {e}")
            raise

    async def _analyze_content(self, content: str) -> Dict[str, Any]:
        """使用LLM分析内容生成元数据"""
        try:
            prompt = f"""
分析以下内容并提取关键信息：

内容：
{content}

请以JSON格式返回分析结果：
{{
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "context": "内容的主要上下文或领域",
    "tags": ["标签1", "标签2", "标签3"]
}}
"""

            # LLMClient.chat expects a plain string prompt; it will wrap into the
            # provider-specific `messages` format with `type: text` parts.
            response = self.llm_client.chat(prompt)

            # 处理响应格式
            if isinstance(response, dict):
                result_text = response.get("content", "")
            else:
                result_text = str(response)

            # 解析JSON
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_text = result_text[json_start:json_end]
                analysis = json.loads(json_text)
                return analysis
            else:
                # Fallback分析
                return self._fallback_analysis(content)

        except Exception as e:
            logger.warning(f"LLM content analysis failed: {e}")
            return self._fallback_analysis(content)

    def _fallback_analysis(self, content: str) -> Dict[str, Any]:
        """内容分析的fallback方法"""
        words = content.split()

        # 简单的关键词提取
        keywords = []
        for word in words[:10]:  # 取前10个词
            if len(word) > 2 and word.isalpha():
                keywords.append(word)

        # 基于内容长度和关键词推断上下文
        if any(kw in content.lower() for kw in ["噬菌体", "细菌", "病毒", "治疗"]):
            context = "生物医学研究"
            tags = ["生物学", "医学", "研究"]
        elif any(kw in content.lower() for kw in ["AI", "人工智能", "机器学习", "算法"]):
            context = "人工智能技术"
            tags = ["AI", "技术", "算法"]
        else:
            context = "一般内容"
            tags = ["信息", "内容"]

        return {"keywords": keywords[:5], "context": context, "tags": tags}

    async def _store_memory(self, memory_note: MemoryNote, session_id: Optional[str]):
        """将记忆存储到数据库"""
        def _ts(dt: Optional[datetime]):
            return dt.isoformat() if dt else None

        with self._get_conn(session_id) as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, content, memory_type, importance, keywords, context, tags,
                    related_task_id, links, created_at, last_accessed, retrieval_count,
                    evolution_history, embedding_generated, embedding_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    memory_note.id,
                    memory_note.content,
                    memory_note.memory_type.value,
                    memory_note.importance.value,
                    json.dumps(memory_note.keywords),
                    memory_note.context,
                    json.dumps(memory_note.tags),
                    memory_note.related_task_id,
                    json.dumps(memory_note.links),
                    _ts(memory_note.created_at),
                    _ts(memory_note.last_accessed),
                    memory_note.retrieval_count,
                    json.dumps(memory_note.evolution_history),
                    memory_note.embedding_generated,
                    memory_note.embedding_model,
                ),
            )

    async def _generate_embedding(self, memory_note: MemoryNote, session_id: Optional[str]) -> bool:
        """为记忆生成嵌入向量"""
        try:
            # 构建用于embedding的文本（内容+元数据）
            embedding_text = self._build_embedding_text(memory_note)

            # 生成嵌入向量
            embedding = self.embeddings_service.get_single_embedding(embedding_text)

            if embedding:
                # 存储嵌入向量
                embedding_json = json.dumps(embedding)
                with self._get_conn(session_id) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO memory_embeddings 
                        (memory_id, embedding_vector, embedding_model, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                        (memory_note.id, embedding_json, "embedding-2"),
                    )

                    # 更新记忆表的embedding状态
                    conn.execute(
                        """
                        UPDATE memories SET embedding_generated = TRUE, embedding_model = ?
                        WHERE id = ?
                    """,
                        ("embedding-2", memory_note.id),
                    )

                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Failed to generate embedding for memory {memory_note.id}: {e}")
            return False

    def _build_embedding_text(self, memory_note: MemoryNote) -> str:
        """构建用于生成embedding的文本"""
        parts = [memory_note.content]

        if memory_note.keywords:
            parts.append(f"关键词: {', '.join(memory_note.keywords)}")

        if memory_note.context and memory_note.context != "General":
            parts.append(f"上下文: {memory_note.context}")

        if memory_note.tags:
            parts.append(f"标签: {', '.join(memory_note.tags)}")

        return " | ".join(parts)

    async def _semantic_search(
        self,
        query: str,
        query_all: bool,
        where_conditions: List[str],
        params: List[Any],
        limit: int,
        min_similarity: float,
        session_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """语义搜索记忆"""
        try:
            if query_all:
                return await self._text_search(
                    query="",
                    where_conditions=where_conditions,
                    params=params,
                    limit=limit,
                    session_id=session_id,
                    match_all=True,
                )
            # 生成查询的嵌入向量
            query_embedding = self.embeddings_service.get_single_embedding(query)

            if not query_embedding:
                # Fallback到文本搜索
                return await self._text_search(query, where_conditions, params, limit, session_id, match_all=False)

            # 获取所有有嵌入向量的记忆
            where_clause = "WHERE embedding_generated = TRUE"
            if where_conditions:
                where_clause += " AND " + " AND ".join(where_conditions)

            with self._get_conn(session_id) as conn:
                query_sql = f"""
                    SELECT m.*, me.embedding_vector
                    FROM memories m
                    JOIN memory_embeddings me ON m.id = me.memory_id
                    {where_clause}
                    ORDER BY m.created_at DESC
                """

                rows = conn.execute(query_sql, params).fetchall()

            # 计算相似度并排序
            results = []
            for row in rows:
                try:
                    embedding_vector = json.loads(row["embedding_vector"])
                    similarity = self.embeddings_service.compute_similarity(query_embedding, embedding_vector)

                    if similarity >= min_similarity:
                        memory_data = {
                            "id": row["id"],
                            "content": row["content"],
                            "memory_type": row["memory_type"],
                            "importance": row["importance"],
                            "keywords": row["keywords"],
                            "context": row["context"],
                            "tags": row["tags"],
                            "related_task_id": row["related_task_id"],
                            "created_at": row["created_at"],
                            "similarity": similarity,
                        }
                        results.append(memory_data)

                except Exception as e:
                    logger.warning(f"Error processing memory row: {e}")
                    continue

            # 按相似度排序
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return await self._text_search(query, where_conditions, params, limit, session_id, match_all=False)

    async def _text_search(
        self,
        query: str,
        where_conditions: List[str],
        params: List[Any],
        limit: int,
        session_id: Optional[str],
        match_all: bool = False,
    ) -> List[Dict[str, Any]]:
        """文本搜索fallback"""
        where_clause = "WHERE 1=1" if match_all else "WHERE content LIKE ?"
        search_params = [] if match_all else [f"%{query}%"]

        if where_conditions:
            where_clause += " AND " + " AND ".join(where_conditions)
            search_params.extend(params)

        with self._get_conn(session_id) as conn:
            query_sql = f"""
                SELECT * FROM memories
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """
            search_params.append(limit)

            rows = conn.execute(query_sql, search_params).fetchall()

        results = []
        for row in rows:
            memory_data = {
                "id": row["id"],
                "content": row["content"],
                "memory_type": row["memory_type"],
                "importance": row["importance"],
                "keywords": row["keywords"],
                "context": row["context"],
                "tags": row["tags"],
                "related_task_id": row["related_task_id"],
                "created_at": row["created_at"],
                "similarity": self.text_similarity_default,
            }
            results.append(memory_data)

        return results

    async def _process_memory_evolution(self, memory_note: MemoryNote, session_id: Optional[str]):
        """处理记忆进化"""
        try:
            self.evolution_count += 1

            # 每达到阈值触发一次进化
            if self.evolution_count % self.evolution_threshold == 0:
                await self._evolve_memories(session_id)

            # 为新记忆寻找相关连接
            await self._find_memory_connections(memory_note, session_id)

        except Exception as e:
            logger.error(f"Memory evolution failed: {e}")

    async def _find_memory_connections(self, memory_note: MemoryNote, session_id: Optional[str]):
        """为新记忆寻找相关连接"""
        try:
            # 搜索相关记忆
            query_request = QueryMemoryRequest(
                search_text=memory_note.content,
                limit=5,
                min_similarity=0.6,
                session_id=session_id,
            )

            related_memories = await self.query_memory(query_request)

            # 建立连接
            connections = []
            for related in related_memories.memories:
                if related.memory_id != memory_note.id and related.similarity > 0.7:
                    connections.append(related.memory_id)

            if connections:
                # 更新记忆的连接
                memory_note.links.extend(connections[:3])  # 最多3个连接
                await self._update_memory_links(memory_note.id, memory_note.links, session_id)

        except Exception as e:
            logger.error(f"Failed to find memory connections: {e}")

    async def _update_memory_links(self, memory_id: str, links: List[str], session_id: Optional[str]):
        """更新记忆的连接"""
        with self._get_conn(session_id) as conn:
            conn.execute(
                """
                UPDATE memories SET links = ? WHERE id = ?
            """,
                (json.dumps(links), memory_id),
            )
            conn.commit()

    async def _evolve_memories(self, session_id: Optional[str]):
        """执行记忆进化"""
        try:
            logger.info("Starting memory evolution process...")

            # 获取最近的记忆进行进化分析
            with self._get_conn(session_id) as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM memories 
                    ORDER BY created_at DESC 
                    LIMIT 20
                """
                ).fetchall()

            # 分析记忆关系并更新标签和上下文
            for row in rows:
                try:
                    await self._evolve_single_memory(row)
                except Exception as e:
                    logger.warning(f"Failed to evolve memory {row['id']}: {e}")

            logger.info("Memory evolution process completed")

        except Exception as e:
            logger.error(f"Memory evolution failed: {e}")

    async def _evolve_single_memory(self, memory_row):
        """进化单个记忆"""
        # 这里可以实现更复杂的进化逻辑
        # 暂时简化实现
        pass

    async def get_memory_stats(self) -> MemoryStats:
        """获取记忆系统统计信息"""
        with get_db() as conn:
            # 总记忆数量
            total_memories = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

            # 记忆类型分布
            type_stats = conn.execute(
                """
                SELECT memory_type, COUNT(*) as count
                FROM memories
                GROUP BY memory_type
            """
            ).fetchall()

            # 重要性分布
            importance_stats = conn.execute(
                """
                SELECT importance, COUNT(*) as count
                FROM memories
                GROUP BY importance
            """
            ).fetchall()

            # 嵌入向量覆盖率
            embedding_count = conn.execute(
                """
                SELECT COUNT(*) FROM memories WHERE embedding_generated = TRUE
            """
            ).fetchone()[0]

            # 平均连接数
            avg_connections = (
                conn.execute(
                    """
                SELECT AVG(json_array_length(links)) as avg_links
                FROM memories
                WHERE links IS NOT NULL AND links != '[]'
            """
                ).fetchone()[0]
                or 0.0
            )

        return MemoryStats(
            total_memories=total_memories,
            memory_type_distribution={row[0]: row[1] for row in type_stats},
            importance_distribution={row[0]: row[1] for row in importance_stats},
            average_connections=avg_connections,
            embedding_coverage=embedding_count / total_memories if total_memories > 0 else 0.0,
            evolution_count=self.evolution_count,
        )


# 单例服务实例
_memory_service = None


def get_memory_service() -> IntegratedMemoryService:
    """获取记忆服务实例"""
    global _memory_service
    if _memory_service is None:
        _memory_service = IntegratedMemoryService()
    return _memory_service
