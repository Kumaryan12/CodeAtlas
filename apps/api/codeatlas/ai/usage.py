"""Run-local HTTP usage capture. Never stores prompts, source, keys, or response bodies."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field


class TokenPrices(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input: float = Field(ge=0, le=1_000_000)
    output: float = Field(ge=0, le=1_000_000)
    cached_input: float | None = Field(default=None, ge=0, le=1_000_000)
    cache_write: float | None = Field(default=None, ge=0, le=1_000_000)


class UsageRecord(BaseModel):
    provider: str
    model: str
    operation: str
    duration_ms: int
    response_received: bool
    http_status: int | None = None
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    cache_write_tokens: int | None
    estimated_cost_usd: float | None
    prices_usd_per_million: TokenPrices | None


class UsageSummary(BaseModel):
    recorded_calls: int
    tokens_complete: bool
    known_input_tokens: int
    known_output_tokens: int
    provider_duration_ms: int
    estimated_cost_usd: float | None


@dataclass
class Capture:
    prices: dict[str, TokenPrices]
    pending: list[dict] = field(default_factory=list)


active_capture: ContextVar[Capture | None] = ContextVar("codeatlas_usage", default=None)


def drain_usage() -> list[dict]:
    capture = active_capture.get()
    if capture is None:
        return []
    rows, capture.pending = capture.pending, []
    return rows


def integer(value):
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def record_usage(url, model, data, duration_ms, http_status=None):
    capture = active_capture.get()
    if capture is None:
        return
    provider = "anthropic" if url == "https://api.anthropic.com/v1/messages" else "openai"
    operation = "embedding" if url.endswith("/embeddings") else "reasoning"
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    cached = integer(usage.get("cache_read_input_tokens", 0))
    written = integer(usage.get("cache_creation_input_tokens", 0))
    incoming = integer(usage.get("input_tokens"))
    outgoing = integer(usage.get("output_tokens"))
    if provider == "openai":
        details = usage.get("input_tokens_details", {})
        cached = integer(details.get("cached_tokens", 0)) if isinstance(details, dict) else None
        written = (
            integer(details.get("cache_write_tokens", 0)) if isinstance(details, dict) else None
        )
        if operation == "embedding":
            incoming, outgoing = integer(usage.get("prompt_tokens")), 0
            cached, written = 0, 0
        # OpenAI input_tokens includes cache reads/writes; Anthropic excludes them.
        if None not in (incoming, cached, written):
            incoming = incoming - cached - written if incoming >= cached + written else None
    prices = capture.prices.get(f"{provider}:{model}")
    cost = None
    if prices and None not in (incoming, outgoing, cached, written):
        if (not cached or prices.cached_input is not None) and (
            not written or prices.cache_write is not None
        ):
            cost = (
                incoming * prices.input
                + outgoing * prices.output
                + cached * (prices.cached_input or 0)
                + written * (prices.cache_write or 0)
            ) / 1_000_000
    capture.pending.append(
        UsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            duration_ms=duration_ms,
            response_received=data is not None or http_status is not None,
            http_status=http_status,
            input_tokens=incoming,
            output_tokens=outgoing,
            cached_input_tokens=cached,
            cache_write_tokens=written,
            estimated_cost_usd=cost,
            prices_usd_per_million=prices,
        ).model_dump()
    )


def summarize_usage(steps):
    rows = [row for step in steps for row in step.get("usage", [])]
    missing_steps = any(
        not step.get("usage")
        and (
            step.get("kind") == "model"
            or (
                step.get("action") == "search_code"
                and step.get("status") in {"running", "interrupted"}
            )
        )
        for step in steps
    )
    complete = (
        bool(rows)
        and not missing_steps
        and all(
            all(
                row.get(key) is not None
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "cached_input_tokens",
                    "cache_write_tokens",
                )
            )
            for row in rows
        )
    )
    return {
        "recorded_calls": len(rows),
        "tokens_complete": complete,
        "known_input_tokens": sum(
            (r.get("input_tokens") or 0)
            + (r.get("cached_input_tokens") or 0)
            + (r.get("cache_write_tokens") or 0)
            for r in rows
        ),
        "known_output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
        "provider_duration_ms": sum(r["duration_ms"] for r in rows),
        "estimated_cost_usd": sum(r["estimated_cost_usd"] for r in rows)
        if complete and all(r.get("estimated_cost_usd") is not None for r in rows)
        else None,
    }
