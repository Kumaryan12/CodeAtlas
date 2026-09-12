"""Safe schema diagnostics: field categories and error types, never response values."""

from pydantic import ValidationError

FIELDS = frozenset(
    {
        "plan",
        "summary",
        "action",
        "arguments",
        "answer",
        "status",
        "claims",
        "text",
        "citation_ids",
        "query",
        "prefix",
        "offset",
        "file_id",
        "start_line",
        "end_line",
        "path",
        "expected_sha256",
        "old_text",
        "new_text",
        "content",
    }
)
TYPES = frozenset(
    {
        "too_short",
        "too_long",
        "string_too_short",
        "string_too_long",
        "missing",
        "extra_forbidden",
        "literal_error",
        "json_invalid",
        "value_error",
        "string_type",
        "int_type",
        "list_type",
        "model_type",
        "dict_type",
        "greater_than_equal",
        "less_than_equal",
    }
)


def validation_summary(error: ValidationError) -> str:
    details = []
    for item in error.errors(include_url=False, include_context=False, include_input=False)[:6]:
        path = (
            ".".join(
                "item" if isinstance(part, int) else part if part in FIELDS else "unknown"
                for part in item["loc"]
            )
            or "response"
        )
        kind = item["type"] if item["type"] in TYPES else "invalid"
        details.append(f"{path}: {kind}")
    return "; ".join(details)
