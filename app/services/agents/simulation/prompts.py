"""
Prompt builders for the simulated user mode agents.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .models import ActionSpec, ChatAgentTurn, SimulatedTurn

DEFAULT_SIM_USER_MODEL = "qwen3-max"
DEFAULT_JUDGE_MODEL = "qwen3-max"
DEFAULT_IMPROVEMENT_GOAL = (
    "Refine the currently bound plan to better accomplish its objectives."
)


def _format_action(action: Optional[ActionSpec]) -> str:
    if action is None:
        return "(no action)"
    params = action.parameters or {}
    params_repr = ", ".join(f"{k}={v}" for k, v in params.items()) or "{}"
    return f"{action.kind}:{action.name} params={params_repr}"


def _format_chat_actions(actions: Iterable[ActionSpec]) -> str:
    formatted = [_format_action(action) for action in actions]
    return "\n".join(f"- {item}" for item in formatted) or "- (no actions)"


def build_simulated_user_prompt(
    *,
    plan_outline: str,
    improvement_goal: Optional[str],
    previous_turns: Iterable[SimulatedTurn],
    action_catalog: str,
    max_actions: int = 2,
) -> str:
    """Compose the prompt used to simulate the next user utterance."""
    turns_text = []
    for turn in previous_turns:
        sim_line = f"Simulated user (you): {turn.simulated_user.message}"
        chat_line = f"Chat agent reply: {turn.chat_agent.reply}"
        judge_line = None
        # Only surface judge feedback when misaligned to avoid biasing future turns
        if turn.judge and turn.judge.alignment == "misaligned":
            judge_line = f"Judge verdict (misaligned): {turn.judge.explanation}"

        lines = [sim_line, chat_line]
        if judge_line:
            lines.append(judge_line)
        turns_text.append("\n".join(lines))

    history_block = "\n\n".join(turns_text) if turns_text else "(no prior turns)"
    goal_text = (improvement_goal or "").strip() or DEFAULT_IMPROVEMENT_GOAL

    return f"""
You are simulating a human user collaborating with a planning assistant.

Plan outline:
{plan_outline}

Action catalog (must use these ACTION kinds/names):
{action_catalog}

Action limit per turn:
Respond with no more than {max_actions} ACTION intention(s) per turn. Prefer a single, precise ACTION when possible.
- Do NOT repeat a request already made in previous turns; propose a new action or refinement that adds incremental value.

Current improvement goal:
{goal_text}

Action parameter requirements:
- Always include every required parameter for the chosen ACTION exactly as the schema expects; do not invent new fields.
- For `task_operation/create_task`, you must provide `name` (string). Include other applicable fields such as `instruction` and `parent_id` when relevant. An action missing a required field will be rejected.
- You MUST consult the plan outline before proposing `create_task`. If the same parent already contains a task with the same or very similar name/instruction, you are forbidden to create another. Instead, reference the existing task ID and request an update/refinement. Duplicate creates will be treated as an error.

Previous conversation transcript:
{history_block}

Respond with a JSON object containing:
{{
    "user_message": "<natural language message in English>",
    "desired_action": {{
        "kind": "<action kind from the ACTION catalog>",
        "name": "<action name>",
      "parameters": {{ ... }}  // include every required parameter explicitly (no placeholders)
    }}
}}

In `user_message`, restate the same parameters/constraints you put in `desired_action.parameters` so the assistant can follow them precisely.
The JSON must be the entire response with no extra commentary. Your desired_action must be executable against the ACTION catalog/schema (no invented fields, use the exact parameter names the action expects).
""".strip()


def build_judge_prompt(
    *,
    plan_outline: str,
    improvement_goal: Optional[str],
    simulated_user_action: Optional[ActionSpec],
    chat_agent_turn: ChatAgentTurn,
) -> str:
    """Compose the prompt for the judge agent."""
    goal_text = (improvement_goal or "").strip() or DEFAULT_IMPROVEMENT_GOAL
    sim_action_text = _format_action(simulated_user_action)
    chat_actions_text = _format_chat_actions(chat_agent_turn.actions)

    return f"""
You are the judge overseeing whether the assistant's ACTIONS match the simulated user's intent.

Plan outline:
{plan_outline}

Improvement goal:
{goal_text}

Simulated user's desired ACTION:
{sim_action_text}

Assistant reply:
{chat_agent_turn.reply}

Assistant ACTIONS:
{chat_actions_text}

Return a JSON object:
{{
    "alignment_score": 0 | 1,
    "reason": "<brief explanation identifying the mismatch>",
    "confidence": <number between 0 and 1, optional>
}}

Use score 0 for aligned behavior and 1 when the assistant is misaligned.
Respond with JSON only.
""".strip()
