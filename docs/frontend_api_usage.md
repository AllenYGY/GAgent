# 前端接口使用情况速览（基于 web-ui）

> 基于 `web-ui/src/api`、`web-ui/src/store` 与相关组件，汇总当前前端**实际调用**的后端接口，便于清理遗留依赖或对齐新接口。

## 1) 已接入且在代码中被调用

| 接口 | 方法 | 前端入口 | 主要用途 |
| --- | --- | --- | --- |
| `/chat/message` | POST | `web-ui/src/api/chat.ts` → `store/chat.ts` | 结构化聊天入口。若返回 `actions`，响应带 `metadata.status=pending` 与 `tracking_id`；前端随后轮询 `/chat/actions/{tracking_id}`。 |
| `/chat/actions/{tracking_id}` | GET | `web-ui/src/api/chat.ts` | 轮询异步动作执行状态与结果（含 `tool_results`）。 |
| `/chat/history/{session_id}` | GET | `store/chat.ts` | 恢复会话历史（包含 `metadata.tool_results`）。 |
| `/chat/sessions` | GET | `web-ui/src/api/chat.ts` | 会话列表。 |
| `/chat/sessions/{id}` | PATCH | `web-ui/src/api/chat.ts` | 更新会话名称、默认搜索源等。 |
| `/chat/sessions/{id}` | DELETE | `web-ui/src/api/chat.ts` | 删除/归档会话。 |
| `/chat/sessions/{id}/autotitle` | POST | `web-ui/src/api/chat.ts` | 自动生成/刷新会话标题。 |
| `/chat/sessions/autotitle/bulk` | POST | `web-ui/src/api/chat.ts` | 批量自动命名。 |
| `/plans/{plan_id}/tree` | GET | `web-ui/src/api/planTree.ts` | 获取完整 PlanTree。 |
| `/plans/{plan_id}/subgraph` | GET | `web-ui/src/api/planTree.ts` | 获取局部子图。 |
| `/plans/{plan_id}/results` | GET | `web-ui/src/api/planTree.ts` | 计划内任务执行结果。 |
| `/plans/{plan_id}/execution/summary` | GET | `web-ui/src/api/planTree.ts` | 执行统计摘要。 |
| `/tasks/{task_id}/result` | GET | `web-ui/src/api/planTree.ts` | 单任务执行结果详情。 |
| `/tasks/{task_id}/decompose` | POST | `web-ui/src/api/planTree.ts` | 任务分解（后端已实现）。 |
| `/health` / `/health/llm?ping=true` | GET | `web-ui/src/api/client.ts` | 前端启动健康检查。 |
| `/system/health` | GET | `web-ui/src/services/intentAnalysis.ts` | 仪表盘综合状态。 |
| `/mcp/save_memory` | POST | `web-ui/src/api/memory.ts` | 保存记忆。 |
| `/mcp/query_memory` | POST | `web-ui/src/api/memory.ts` | 记忆检索。 |
| `/mcp/memory/stats` | GET | `web-ui/src/api/memory.ts` | 记忆统计。 |
| `/mcp/memory/auto_save_task` | POST | `web-ui/src/api/memory.ts` | 自动保存任务输出。 |

## 2) 已封装但当前未被调用

| 接口 | 现状 | 说明 |
| --- | --- | --- |
| `/chat/status` | API 已封装（`api/chat.ts`），但无实际调用 | 若需要状态面板可启用。 |

## 3) 需要注意的遗留封装

| 位置 | 说明 |
| --- | --- |
| `web-ui/src/api/tasks.ts` / `web-ui/src/api/plans.ts` | 仍指向旧 `/tasks/*`、`/plans/*` 旧接口；建议清理或合并为 `planTree` 服务。 |
| `web-ui/src/services/intentAnalysis.ts` 中的旧接口 | 存在历史调用路径，建议统一迁移到 `/system/health` 与 `/chat/message`。 |

## 4) 建议

1. 任务与计划修改仍以 `/chat/message` 结构化动作为主；只读需求使用 `/plans/...`。
2. 统一 planTree API，删去未用旧封装，避免前端误调用已废弃接口。
3. Memory 功能若要扩展，可补前端入口调用 `/mcp/memory/hooks/*`。
