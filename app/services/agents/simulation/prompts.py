"""
Prompt builders for the simulated user mode agents.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .models import ActionSpec, ChatAgentTurn, SimulatedTurn

DEFAULT_SIM_USER_MODEL = "qwen3-max"
DEFAULT_JUDGE_MODEL = "qwen3-max"
DEFAULT_IMPROVEMENT_GOAL = "Refine the currently bound plan to better accomplish its objectives."


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
) -> str:
    """Compose the prompt used to simulate the next user utterance."""
    turns_text = []
    for turn in previous_turns:
        sim_line = f"Simulated user: {turn.simulated_user.message}"
        action_line = f"Desired ACTION: {_format_action(turn.simulated_user.desired_action)}"
        chat_line = f"Chat agent reply: {turn.chat_agent.reply}"
        chat_actions = _format_chat_actions(turn.chat_agent.actions)
        judge_line = (
            f"Judge verdict: {turn.judge.alignment} ({turn.judge.explanation})"
            if turn.judge
            else "Judge verdict: (pending)"
        )
        turns_text.append("\n".join([sim_line, action_line, chat_line, chat_actions, judge_line]))

    history_block = "\n\n".join(turns_text) if turns_text else "(no prior turns)"
    goal_text = (improvement_goal or "").strip() or DEFAULT_IMPROVEMENT_GOAL

    return f"""
You are simulating a human user collaborating with a planning assistant.

Plan outline:
{plan_outline}

Current improvement goal:
{goal_text}

Previous conversation transcript:
{history_block}

Respond with a JSON object containing:
{{
  "user_message": "<natural language message in English>",
  "desired_action": {{
      "kind": "<action kind from the ACTION catalog>",
      "name": "<action name>",
      "parameters": {{ ... }}
  }}
}}

Do not execute the action; only describe the desired ACTION.
The JSON must be the entire response with no extra commentary.
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
  "alignment": "aligned" | "misaligned" | "unclear",
  "explanation": "<short explanation>",
  "confidence": <number between 0 and 1, optional>
}}

Respond with JSON only.
""".strip()
