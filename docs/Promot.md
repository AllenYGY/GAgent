# 提示词结构与来源总览

本文整理本仓库**主要 LLM 提示词**的构成与位置，便于前后端协同检查、定位输出问题与对齐版本变化。

## 1) 结构化 Chat Agent（action 模式）

**位置**：`app/routers/chat_routes.py::_build_prompt`

**核心结构**（按拼接顺序）：

1. 固定开场语（系统身份）
2. 最近历史消息（`StructuredChatAgent.MAX_HISTORY`）
3. 记忆片段（若记忆检索命中）  
   - 以 `=== Retrieved Memories ===` 插入
4. Plan 概览  
   - `PlanSession.outline(max_depth=4, max_nodes=60)`  
   - 未绑定计划时追加 “Available plans” 列表
5. JSON Schema（`LLMStructuredResponse`）
6. Action Catalog（由 `build_action_catalog` 动态生成）
7. Guidelines（由 `_compose_guidelines` 生成）
8. 用户消息（`User message: ...`）
9. 固定收尾：`Respond with the JSON object now.`

**说明**：当前实现不再注入 `extra_context`/Plan 状态字段（已简化）。

**提示词持久化**：

- 当 `extra_context` 中包含 `simulation_run_id` 与 `simulation_turn_index` 时保存到  
  `CHAT_AGENT_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt`

## 2) action 模式模拟用户 / Judge

**位置**：`app/services/agents/simulation/prompts.py`

### 2.1 Simulated User Prompt

包含：

- Plan outline
- Action catalog
- improvement goal
- 参数约束（required fields / 禁止重复 create）
- “不要重复请求”的约束
- 近期对话历史（sim user / chat agent / judge）
- JSON 输出格式规范

**保存路径**：

- `SIM_USER_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt`

### 2.2 Judge Prompt

包含：

- Plan outline
- improvement goal
- simulated user 的期望 ACTION
- chat agent reply 与 actions
- JSON 输出规范（alignment_score / reason / confidence）

**保存路径**：

- `JUDGE_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt`

## 3) full_plan 模式（直接生成完整 plan）

**位置**：`scripts/parallel_simulation_experiment.py`

### 3.1 DEFAULT_FULL_PLAN_SIM_USER_PROMPT

- 输入：goal、baseline plan、history
- 输出：更新后的完整 plan JSON
- 约束：深度 ≤3、总任务 ≤30、禁止重复改动

### 3.2 DEFAULT_FULL_PLAN_CHAT_PROMPT

- 输入：goal、current plan、history
- 输出：改进后的完整 plan JSON
- 约束：深度 ≤3、总任务 ≤30、字段必须完整

### 3.3 DEFAULT_FULL_PLAN_JUDGE_PROMPT

- 输入：goal、baseline plan、agent plan
- 输出：alignment（aligned / misaligned）

**保存说明**：

full_plan 模式默认不保存 prompt，但会保存 raw/parsed 计划与 judge verdict。

## 4) Plan Quality 评估 Prompt

**位置**：`scripts/eval_plan_quality.py`

包含：

- Plan metadata（id/title/goal）
- Plan outline（`PlanTree.to_outline`）
- 评分维度与详细定义
- JSON 输出 schema

**保存路径**：

- 评估输出目录下的 `eval/Prompts/plan_<id>.txt`

## 5) Task 执行与修订 Prompt

### 5.1 TaskPromptBuilder（通用任务执行）

**位置**：`app/services/llm/llm_service.py`

- `build_initial_prompt`：任务执行默认 prompt
- `build_revision_prompt` / `build_evaluation_prompt`：内容修订与评分

### 5.2 PromptBuilder（上下文与修订增强）

**位置**：`app/execution/prompt_builder.py`

- `build_context_prompt`：注入任务上下文（`gather_context` + budget）
- `build_revision_prompt` / `build_llm_revision_prompt` / `build_multi_expert_revision_prompt`

## 6) Prompt 路径与环境变量

| 类型 | 保存路径 |
| --- | --- |
| Chat agent prompt | `CHAT_AGENT_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt` |
| Sim user prompt | `SIM_USER_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt` |
| Judge prompt | `JUDGE_PROMPT_OUTPUT_DIR/<run_id>/turn_XX_prompt.txt` |
| Plan quality prompt | `<eval_output_dir>/Prompts/plan_<id>.txt` |

## 7) 快速索引

| Prompt 类型 | 入口位置 |
| --- | --- |
| Chat agent | `app/routers/chat_routes.py::_build_prompt` |
| Sim user / Judge | `app/services/agents/simulation/prompts.py` |
| Full plan 模式 | `scripts/parallel_simulation_experiment.py` |
| Plan quality 评估 | `scripts/eval_plan_quality.py` |
| Task 执行/修订 | `app/services/llm/llm_service.py`, `app/execution/prompt_builder.py` |

如需定位某类 prompt 的变更或输出异常，请从上述入口文件开始检查。
