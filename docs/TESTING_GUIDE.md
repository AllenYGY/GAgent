# 测试指南（pytest）

本文档说明当前测试结构、运行方式与常见注意事项，基于 `test/` 目录与 `pytest.ini` 现有配置整理。

## 1) 测试目录结构

```shell
test/
  conftest.py
  simulation/
    test_orchestrator.py
    test_runtime.py
  tools/
    test_graph_rag_tool.py
  test_chat_routes_integration.py
  test_chat_routes_request_subgraph.py
  test_chat_sessions_routes.py
  test_llm_model_usage.py
  test_memory_integration.py
  test_plan_decomposer.py
  test_plan_executor.py
  test_plan_repository_basic.py
  test_plan_repository_contexts.py
  test_plan_repository_edge_cases.py
  test_plan_routes.py
  test_structured_agent_actions.py
  test_task_contexts.py
```

## 2) 各测试文件覆盖内容

- `test/conftest.py`：测试环境隔离与临时数据库初始化（DB_ROOT 重定向、连接池重置、计划库初始化）。
- `test/test_chat_routes_integration.py`：StructuredChatAgent 端到端动作执行（创建任务+执行计划）、动作失败汇总、插入任务位置、/chat/message 异步返回与 /chat/actions 状态查询。
- `test/test_chat_routes_request_subgraph.py`：context_request/request_subgraph 获取子图数据，验证节点与 execution_result 字段存在。
- `test/test_chat_sessions_routes.py`：/chat/sessions 列表、更新、删除、归档、默认搜索提供商设置、/chat/status 健康状态。
- `test/test_llm_model_usage.py`：LLM provider/model 配置读取（LLM_PROVIDER、DECOMP_MODEL、PLAN_EXECUTOR_MODEL），以及自定义 provider 覆盖。
- `test/test_memory_integration.py`：记忆系统保存/检索与记忆注入 prompt（替换 embeddings/LLM 依赖）。
- `test/test_plan_decomposer.py`：PlanDecomposer 生成任务、注入 context、跳过已有子任务的逻辑。
- `test/test_plan_executor.py`：PlanExecutor 执行顺序、失败中止、重试机制与执行结果写回。
- `test/test_plan_repository_basic.py`：PlanRepository 计划/任务 CRUD、上下文字段写入、快照与 upsert 逻辑。
- `test/test_plan_repository_contexts.py`：context_combined/sections/meta 的持久化与级联删除。
- `test/test_plan_repository_edge_cases.py`：任务位置重排、移动/提升、依赖去重、锚点插入、缺失计划文件与错误分支。
- `test/test_plan_routes.py`：/plans 树与子图接口、任务分解接口、执行结果汇总与执行状态统计。
- `test/test_structured_agent_actions.py`：StructuredChatAgent 动作流（create/update/move/delete/execute/decompose/show/query/rerun/help、web_search、graph_rag）。
- `test/test_task_contexts.py`：上下文更新与 context_updated_at 字段写入验证。
- `test/simulation/test_orchestrator.py`：仿真 orchestrator 单轮执行、plan outline 快照、消息持久化。
- `test/simulation/test_runtime.py`：SimulationRegistry 状态流转、自动终止、JSON 持久化时间戳。
- `test/tools/test_graph_rag_tool.py`：graph_rag 工具读取 triples、focus_entities 过滤、缺失文件错误。

## 3) 运行方式

在仓库根目录执行：

```bash
pytest
```

常用变体：

```bash
# 只跑某个文件
pytest test/test_plan_repository_basic.py

# 只跑包含关键字的用例
pytest -k "plan_executor"

# 更详细日志
pytest -vv -s

# 首个失败即停止
pytest --maxfail=1
```

## 4) 测试环境隔离

`test/conftest.py` 会在 session 级别自动完成以下动作：

- 将 `DB_ROOT` 指向 pytest 的临时目录
- 重新初始化主库与计划库
- 重置数据库连接池与单例缓存

因此测试对本地真实数据库无影响。

## 5) LLM 与外部依赖

当前测试大多使用 **stub/mock**：

- `test_llm_model_usage.py` 通过 monkeypatch 注入假 client / service
- `test_memory_integration.py` 替换嵌入服务与 LLM
- `test_structured_agent_actions.py` 用 stub LLM 输出固定 JSON

因此运行测试通常**不需要真实 API Key**，也不会触发网络请求。

## 6) 记忆系统测试

`test_memory_integration.py` 会：

- 使用内存 SQLite 替代真实数据库
- monkeypatch 记忆服务的 LLM/嵌入依赖
- 验证记忆保存与检索逻辑

如需调试，可使用：

```bash
pytest test/test_memory_integration.py -vv -s
```

## 7) simulation 测试

`test/simulation/` 主要验证：

- 仿真 orchestrator / runtime 行为
- 计划快照与状态流转

如需单独运行：

```bash
pytest test/simulation -vv
```

## 8) 常见问题

### Protobuf 版本警告

已在 `pytest.ini` 中忽略：

```shell
ignore:Protobuf gencode version .* is exactly one major version older than the runtime version:UserWarning
```

若仍出现大量 warning，可检查本地 protobuf 版本或更新依赖。

### 想查看更详细的日志

```bash
pytest -vv -s
```

或在运行前设置：

```bash
export LOG_LEVEL=DEBUG
```

## 9) 建议

- 新增测试时尽量 stub LLM / embeddings，避免依赖外部网络
- 涉及 Plan / Task 的测试，尽量依赖 `plan_repo` fixture
- 保持测试独立性：不要写入 `data/databases` 真库
