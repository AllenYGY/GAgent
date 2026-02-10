# 数据库结构与存储布局（整合版）

本系统采用“主库 + 每个计划独立数据库”的分层存储方案。主库负责跨计划的索引、会话与异步动作，计划库负责任务树与执行日志。以下内容基于当前实现进行整理，便于定位数据与排障。

## 1) DB_ROOT 目录结构

数据库根目录由 `DB_ROOT` 控制（默认 `data/databases`）。初始化时创建以下子目录：

- `main/plan_registry.db`：主库（计划索引、会话、聊天记录、异步动作索引）。
- `plans/plan_{id}.sqlite`：每个计划的独立任务库。
- `jobs/system_jobs.sqlite`：未绑定计划的作业日志库（解构/动作日志）。
- `sessions/session_{id}.sqlite`：按会话隔离的记忆库。
- `cache/*.db`：嵌入/LLM缓存（如 `embedding_cache.db`, `llm_cache.db`）。
- `temp/`：临时库（实验/统计等）。
- `backups/`：迁移或备份文件。

注意：`DATABASE_URL` 仍存在于 settings 中，但当前计划与任务树的持久化由 `DB_ROOT` 驱动。

## 2) 主库（main/plan_registry.db）

由 `app/database.init_db()` 初始化。主要表：

- `plans`：计划索引与元信息。关键字段：
  - `id`, `title`, `description`, `metadata`, `plan_db_path`, `created_at`, `updated_at`
- `chat_sessions`：前端会话元信息与绑定计划。关键字段：
  - `id`, `plan_id`, `plan_title`, `name`, `name_source`, `is_user_named`, `current_task_id`, `current_task_name`, `last_message_at`, `metadata`
- `chat_messages`：对话消息归档。关键字段：
  - `session_id`, `role`, `content`, `metadata`, `created_at`
- `chat_action_runs`：异步结构化调用记录（/chat/message 触发的异步动作）。关键字段：
  - `id`, `session_id`, `plan_id`, `status`, `context_json`, `history_json`, `structured_json`, `result_json`, `errors_json`, `started_at`, `finished_at`
- `plan_decomposition_job_index`：作业索引（job_id → plan_id）。关键字段：
  - `job_id`, `plan_id`, `job_type`, `created_at`

## 3) 计划库（plans/plan_{id}.sqlite）

由 `app/repository/plan_storage.initialize_plan_database()` 创建。主要表：

### 3.1 `plan_meta`

键值存储计划元信息：

- `schema_version`, `title`, `description`, `metadata`

### 3.2 `tasks`

任务节点主表，每条记录对应一个 `PlanNode`：

| 字段 | 说明 |
| --- | --- |
| `id` | 节点 ID（主键） |
| `name`, `instruction` | 任务名称与说明 |
| `status` | 状态（默认 pending） |
| `parent_id`, `position`, `path`, `depth` | 树结构信息 |
| `metadata` | 扩展属性 JSON |
| `execution_result` | 最近一次执行结果 |
| `context_combined`, `context_sections`, `context_meta` | 上下文信息 |
| `context_updated_at`, `created_at`, `updated_at` | 时间戳 |

### 3.3 `task_dependencies`

依赖关系表：

- `task_id`, `depends_on`

### 3.4 `snapshots`

计划快照（用于回溯与调试）：

- `snapshot`, `note`, `created_at`

### 3.5 `decomposition_jobs` / `decomposition_job_logs`

解构作业记录（用于 plan/task decomposition）：

- `decomposition_jobs`：`job_id`, `job_type`, `mode`, `target_task_id`, `status`, `error`, `params_json`, `stats_json`, `result_json`, `metadata_json`, `started_at`, `finished_at`
- `decomposition_job_logs`：`job_id`, `timestamp`, `level`, `message`, `metadata_json`

### 3.6 `plan_action_logs`

动作执行日志（包含结构化 action 的去敏感细节）：

- `plan_id`, `job_id`, `job_type`, `sequence`, `session_id`, `user_message`
- `action_kind`, `action_name`, `status`, `success`, `message`, `details_json`

日志写入时会对敏感字段（如 `api_key`, `token` 等）做红线过滤，并对超长字段截断。

## 4) 系统作业库（jobs/system_jobs.sqlite）

当作业未绑定具体计划（plan_id=None）时，解构与动作日志写入系统作业库。结构与 `decomposition_jobs` / `plan_action_logs` 一致，用于全局追踪异步作业。

## 5) 会话记忆库（sessions/session_{id}.sqlite）

由 `IntegratedMemoryService` 创建，按会话隔离。主要表：

- `memories`：记忆条目（类型、重要性、关键词、关联任务等）
- `memory_embeddings`：记忆向量
- `tasks`：轻量 tasks 表（用于外键占位）

无 session_id 时，记忆默认写入主库。

## 6) 读写流程摘要

- **创建计划**：`PlanRepository.create_plan` 写入主库 `plans`，并创建 `plan_{id}.sqlite`。
- **加载计划**：`get_plan_tree(plan_id)` 读取 `plan_meta` + `tasks` + `task_dependencies` 组装 `PlanTree`。
- **更新任务**：`create_task` / `update_task` / `move_task` 直接写入计划库的 `tasks` 与依赖表。
- **持久化树**：`upsert_plan_tree` 重写 `tasks`/`task_dependencies`，可写入 `snapshots`。
- **异步动作**：`chat_action_runs` 记录请求与结果；动作日志写入 `plan_action_logs`。
- **解构作业**：`plan_decomposition_job_index` 维护索引，作业详情写入计划库或系统作业库。

## 7) 操作建议

- 业务层请通过 `PlanRepository` / `PlanSession` 读写，避免直接改 SQLite。
- 若需要定位 action 或 decomposition 问题，优先查 `chat_action_runs` 与 `plan_action_logs`。
- 迁移历史数据库时使用 `DatabaseConfig.migrate_existing_databases()`。
