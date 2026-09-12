"""Pinned CPU MiniLM embeddings; token windows preserve long source tails."""

import argparse
from functools import lru_cache

from codeatlas.core.errors import DomainError

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
VERSION = "windows254-weighted-mean-v1"


@lru_cache(maxsize=1)
def load_model():
    try:
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            MODEL, revision=REVISION, trust_remote_code=False, token=False, local_files_only=True
        )
        model = (
            AutoModel.from_pretrained(
                MODEL,
                revision=REVISION,
                trust_remote_code=False,
                token=False,
                use_safetensors=True,
                local_files_only=True,
            )
            .to("cpu")
            .eval()
        )
        return tokenizer, model
    except (ImportError, OSError) as exc:
        raise DomainError(
            "local_embeddings_unavailable",
            "Install the API local extra; run python -m codeatlas.ai.local_embeddings --prepare.",
            503,
        ) from exc


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    tokenizer, model = load_model()
    import torch

    result = []
    with torch.inference_mode():
        for text in texts:
            ids = tokenizer.encode(text, add_special_tokens=False, truncation=False)
            windows = [ids[i : i + 254] for i in range(0, len(ids), 254)] or [[]]
            total = None
            weight = 0
            for window in windows:
                input_ids = torch.tensor(
                    [[tokenizer.cls_token_id, *window, tokenizer.sep_token_id]]
                )
                inputs = {"input_ids": input_ids, "attention_mask": torch.ones_like(input_ids)}
                output = model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1)
                pooled = (output * mask).sum(1) / mask.sum(1)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                size = max(1, len(window))
                total = pooled * size if total is None else total + pooled * size
                weight += size
            result.append(torch.nn.functional.normalize(total / weight, p=2, dim=1)[0].tolist())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.parse_args()
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL,
        revision=REVISION,
        token=False,
        allow_patterns=[
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
        ],
    )
    vector = embed(["CodeAtlas local embedding readiness check"])[0]
    print(f"Ready: {MODEL}@{REVISION}, dimensions={len(vector)}, CPU")


if __name__ == "__main__":
    main()
