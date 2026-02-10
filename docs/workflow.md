# 系统工作流（与当前实现一致）

本文件描述 `/chat/message` 的实际处理流程，以及计划存储、提示构造、动作执行与持久化的真实行为。

## 1) 会话绑定与存储结构

- 前端通过 `POST /chat/message` 发送消息。  
  若请求包含 `session_id`，后端会读取/创建 `chat_sessions` 并取出已有 `plan_id`。  
  若未绑定，则保持 **unbound** 状态，仅允许 `create_plan` / `list_plans`。

- 数据库存储结构（默认 `DB_ROOT=data/databases`）：
  - 主库：`data/databases/main/plan_registry.db`
  - 每个计划一个 SQLite：`data/databases/plans/plan_{id}.sqlite`

## 2) 计划树加载与大纲

`PlanSession.refresh()` 会从 `plan_{id}.sqlite` 重建 `PlanTree`。  
LLM 提示中的大纲由 `PlanTree.to_outline()` 生成，默认：

- **提示用大纲**：`max_depth=4`, `max_nodes=60`
- **响应中的 plan_outline**：`max_depth=4`, `max_nodes=80`

如果未绑定计划，大纲会显示 `"(no plan bound)"`，并补充当前可用计划摘要列表（最多 10 条）。

## 3) 提示构建

提示包含：

1. 最近 10 条对话历史  
2. 可选的记忆检索片段（若 `MEMORY_RETRIEVE_ENABLED=true`）  
3. 计划大纲（Plan Overview）  
4. 结构化 JSON Schema（`LLMStructuredResponse`）  
5. Action catalog（随绑定状态与 allow 标志变动）  
6. Guidelines（动作格式、限制、执行要求）  
7. 用户消息正文

> 注意：`extra_context` 不会直接注入提示，仅用于控制 action catalog 与执行行为。

## 4) LLM 响应解析与规范化

- 先去除 code fence，再用 Pydantic 校验 JSON（最多 **2 次**）。
- 对每个 action 做 `normalize_action`：
  - 丢弃未定义参数
  - 类型强制转换
  - 无法校验的 action 会被丢弃
- 若 `create_task` 缺失 `instruction`，会回退为用户消息正文以避免指令丢失。

## 5) Action 执行

按 `order` 顺序执行，失败会记录在 `errors`，但不会阻止后续动作。

### 计划类动作

- `create_plan`：在主库创建计划，并初始化 `plan_{id}.sqlite`，随后自动绑定。  
  如开启 `DECOMP_AUTO_ON_CREATE`，会触发自动分解。
- `list_plans`：返回可用计划列表。
- `execute_plan`：执行当前绑定计划（受 `enable_execute_actions` 控制）。
- `delete_plan`：删除主库记录并清理 `plan_{id}.sqlite`。

### 任务类动作

- `create_task` / `update_task` / `update_task_instruction` / `move_task` / `delete_task`
- `decompose_task`：调用 PlanDecomposer，按 BFS 展开
- `rerun_task` / `query_status` / `show_tasks`

### context_request

- `request_subgraph`：返回局部子图大纲与节点详情（默认 `max_depth=2`）

### tool_operation

- `web_search` / `graph_rag`：工具结果会写入 `metadata.tool_results`，并缓存到 `recent_tool_results`（最多 5 条）

## 6) 持久化

只要有写操作就会标记 `_dirty`。响应前会：

1. `refresh` 计划树（强制 reload）
2. `upsert_plan_tree` 写回 `plan_{id}.sqlite`
3. `plan_persisted=True`

## 7) 响应返回

响应包含：

- `reply`（自然语言，默认附带 action summary，可通过 `include_action_summary=false` 关闭）
- `actions` 执行详情（成功/失败、异常信息）
- `plan_outline`（如已绑定）
- `plan_persisted`
- `tool_results`（若有工具调用）
- `errors`

## 8) 自动分解配置（PlanDecomposer）

由 `app/config/decomposer_config.py` 控制：

- `DECOMP_MODEL` / `DECOMP_PROVIDER` / `DECOMP_API_URL` / `DECOMP_API_KEY`
- `DECOMP_MAX_DEPTH` / `DECOMP_MIN_CHILDREN` / `DECOMP_MAX_CHILDREN`
- `DECOMP_TOTAL_NODE_BUDGET`
- `DECOMP_AUTO_ON_CREATE`（创建计划后自动分解）

## 9) 执行器配置（PlanExecutor）

由 `app/config/executor_config.py` 控制：

- `PLAN_EXECUTOR_MODEL` / `PLAN_EXECUTOR_PROVIDER` / `PLAN_EXECUTOR_API_URL` / `PLAN_EXECUTOR_API_KEY`
- `PLAN_EXECUTOR_MAX_RETRIES` / `PLAN_EXECUTOR_TIMEOUT`
- `PLAN_EXECUTOR_SERIAL`
- `PLAN_EXECUTOR_USE_CONTEXT`
- `PLAN_EXECUTOR_INCLUDE_OUTLINE`
- `PLAN_EXECUTOR_DEP_THROTTLE`
- `PLAN_EXECUTOR_MAX_TASKS`

## 10) 本地示例

生成演示计划：

```bash
python example/generate_demo_plan.py
```

使用自定义 DB_ROOT：

```bash
DB_ROOT=data/demo_db python example/generate_demo_plan.py
```
