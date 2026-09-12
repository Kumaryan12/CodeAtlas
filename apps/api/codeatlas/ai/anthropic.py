"""Claude reasoning with separately configured OpenAI retrieval embeddings."""

import json

from codeatlas.ai.investigator import (
    DECISION_SCHEMA,
    DRAFT_INSTRUCTIONS,
    DRAFT_SCHEMA,
    EXECUTION_INSTRUCTIONS,
    EXECUTION_SCHEMA,
)
from codeatlas.ai.investigator import (
    INSTRUCTIONS as AGENT_INSTRUCTIONS,
)
from codeatlas.ai.provider import ANSWER_SCHEMA, INSTRUCTIONS, OpenAIProvider, post_json
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.schemas.agent import AgentDecision, DraftDecision, ExecutionDecision
from codeatlas.schemas.qa import ModelAnswer


class AnthropicProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        return OpenAIProvider(self.settings).embed(texts)

    def structured(self, instructions: str, state: dict, schema: dict, tokens: int) -> str:
        key = self.settings.anthropic_api_key.get_secret_value()
        if not key.strip():
            raise DomainError(
                "ai_not_configured",
                "Set CODEATLAS_ANTHROPIC_API_KEY on the API server and restart it.",
                503,
            )
        data = post_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": self.settings.reasoning_model,
                "max_tokens": tokens,
                "system": instructions,
                "messages": [{"role": "user", "content": json.dumps(state, ensure_ascii=False)}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            },
        )
        # A refusal or truncated response must never become an executable decision.
        if data.get("stop_reason") != "end_turn":
            raise ValueError("Incomplete output")
        blocks = data["content"]
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("Missing output")
        if any(
            block.get("type") not in {"text", "thinking", "redacted_thinking"} for block in blocks
        ):
            raise ValueError("Unexpected output block")
        # Independent structured decisions consume only answer text. Thinking is never persisted.
        return "".join(block["text"] for block in blocks if block["type"] == "text")

    def answer(self, question: str, excerpts: list[dict]) -> ModelAnswer:
        try:
            return ModelAnswer.model_validate_json(
                self.structured(
                    INSTRUCTIONS, {"question": question, "excerpts": excerpts}, ANSWER_SCHEMA, 2000
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "invalid_answer", "The model returned an invalid or incomplete answer.", 502
            ) from exc


class AnthropicInvestigator(AnthropicProvider):
    def decide(self, state: dict) -> AgentDecision:
        editing = state.get("mode") == "edit"
        execution = editing and state.get("test_profile") is not None
        schema = EXECUTION_SCHEMA if execution else DRAFT_SCHEMA if editing else DECISION_SCHEMA
        instructions = (
            EXECUTION_INSTRUCTIONS
            if execution
            else DRAFT_INSTRUCTIONS
            if editing
            else AGENT_INSTRUCTIONS
        )
        decision = ExecutionDecision if execution else DraftDecision if editing else AgentDecision
        try:
            return decision.model_validate_json(
                self.structured(instructions, state, schema, 6000 if editing else 2400)
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "invalid_agent_decision",
                "The model returned an invalid or incomplete investigation step.",
                502,
            ) from exc
