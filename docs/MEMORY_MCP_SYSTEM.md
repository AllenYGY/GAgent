# Memory MCP 系统说明（更新版）

本文档说明当前 Memory-MCP 系统的能力、接口与数据流，内容与 `app/api/memory_api.py`、`app/services/memory/memory_service.py` 等实现一致。

## 1) 系统概述

Memory-MCP 提供可检索、可进化的记忆库，支持 MCP 风格接口。其核心能力包括：

- 自动抽取关键词 / 标签 / 上下文（由 LLM 完成）
- 语义检索 + 回退全文检索
- 记忆进化与关联（定期自动连接）
- 会话隔离存储（按 session_id 进入独立数据库）

## 2) 记忆模型

### 2.1 记忆类型（MemoryType）

当前支持：

- `conversation`
- `experience`
- `knowledge`
- `context`
- `task_output`（扩展）
- `evaluation`（扩展）

### 2.2 重要性（ImportanceLevel）

- `critical` / `high` / `medium` / `low` / `temporary`

## 3) 接口列表（/mcp 前缀）

### 3.1 保存记忆

`POST /mcp/save_memory`

请求体（支持 session_id / plan_id / tags / keywords / context）：

```json
{
  "content": "记忆内容",
  "memory_type": "experience",
  "importance": "medium",
  "tags": ["tag1", "tag2"],
  "keywords": ["kw1", "kw2"],
  "context": "上下文描述",
  "related_task_id": 123,
  "session_id": "session_abc",
  "plan_id": 41
}
```

响应（MCP 兼容格式）：

```json
{
  "context_id": "task_123_experience",
  "task_id": 123,
  "memory_type": "experience",
  "content": "记忆内容",
  "created_at": "2025-01-01T12:00:00",
  "embedding_generated": true,
  "meta": {
    "importance": "medium",
    "tags": ["tag1"],
    "agentic_keywords": ["kw1"],
    "agentic_context": "上下文描述"
  }
}
```

### 3.2 查询记忆

`POST /mcp/query_memory`

请求体（支持 session_id / plan_id / include_task_context）：

```json
{
  "search_text": "query text",
  "memory_types": ["conversation", "experience"],
  "limit": 10,
  "min_similarity": 0.6,
  "include_task_context": false,
  "session_id": "session_abc",
  "plan_id": 41
}
```

响应：

```json
{
  "memories": [
    {
      "memory_id": "uuid",
      "task_id": 123,
      "memory_type": "experience",
      "content": "记忆内容",
      "similarity": 0.85,
      "created_at": "2025-01-01T12:00:00",
      "meta": {
        "importance": "high",
        "tags": ["tag1"],
        "agentic_keywords": ["kw1"],
        "agentic_context": "上下文"
      }
    }
  ],
  "total": 1,
  "search_time_ms": 45.2
}
```

### 3.3 统计信息

`GET /mcp/memory/stats`

返回 `MemoryStats`：总量、类型分布、重要性分布、进化次数、嵌入覆盖率等。

### 3.4 MCP 工具列表

`GET /mcp/tools`  
返回 `save_memory` / `query_memory` 的 MCP 工具描述。

### 3.5 自动保存任务输出

`POST /mcp/memory/auto_save_task`

```json
{
  "task_id": 123,
  "task_name": "任务名称",
  "content": "任务输出"
}
```

### 3.6 记忆钩子（auto-save）

- `GET /mcp/memory/hooks/stats`：钩子统计
- `POST /mcp/memory/hooks/enable`：启用
- `POST /mcp/memory/hooks/disable`：禁用
- `POST /mcp/memory/chat/save`：保存聊天消息为记忆（带自动重要性判断）

## 4) 数据存储与隔离

Memory 模块使用 SQLite：

- 有 `session_id` 时：写入 `data/databases/sessions/session_<id>.sqlite`
- 无 `session_id` 时：写入主库

表结构（简化）：

- `memories`：记忆主表
- `memory_embeddings`：向量表
- `tasks`：轻量 tasks 表（外键占位）

详细字段可参考 `docs/Database_Schema_Overview.md`。

## 5) 执行流程

1. 接口接收请求 → `IntegratedMemoryService.save_memory`  
2. LLM 抽取关键词、标签、上下文（若调用可用）  
3. 生成嵌入向量（若嵌入服务可用）  
4. 写入 SQLite  
5. 返回 MCP 兼容格式  

查询流程：

1. 语义检索（嵌入向量）
2. 若向量不可用则回退全文检索

## 6) 常见问题

**嵌入失败 / 查询无结果**

- 嵌入服务不可用时，仍可通过全文检索返回结果
- 若全无结果，请检查是否写入了 session 对应库

**为什么 session_id 会影响可见记忆？**

- session 级记忆隔离用于避免不同会话交叉污染。如需跨会话共享，使用 `session_id = null` 或统一 session。

## 7) 参考实现

- API 路由：`app/api/memory_api.py`
- 核心服务：`app/services/memory/memory_service.py`
- 记忆钩子：`app/services/memory/memory_hooks.py`
- 聊天自动记忆：`app/services/memory/chat_memory_middleware.py`
