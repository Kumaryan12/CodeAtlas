"""Summarize saved RAG artifacts without making provider calls."""

# ruff: noqa: E501 -- report prose keeps complete sentences together.

import argparse
import json
import math
from pathlib import Path


def render(report):
    lines = [
        "# RAG benchmark results",
        "",
        f"Run: {report['created_at']}",
        "",
        "Eight synthetic Python modules; 24 authored cases, 18 with retrieval labels.",
        "",
        "| Retrieval | Recall@6 | MRR@6 | nDCG@6 | Complete evidence@6 |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, data in report["retrieval"].items():
        m = data["metrics"]
        lines.append(
            f"| {mode} | {m['recall@6']:.3f} | {m['mrr@6']:.3f} | "
            f"{m['ndcg@6']:.3f} | {m['complete_evidence@6']:.3f} |"
        )
    rows = report["answers"]
    if rows:
        success = [r for r in rows if not r.get("error")]
        negatives = [r for r in rows if not r["expected"]]
        latencies = sorted(r["answer"]["duration_ms"] for r in success)
        usage = [u for r in rows for u in r["http_usage"]]
        lines += [
            "",
            f"Answer attempts: {len(rows)}; provider/service errors: {len(rows) - len(success)}.",
            f"Expected answer/abstention outcome: {sum(r['expected_outcome'] for r in rows)}/{len(rows)} (errors count as failures).",
            f"Unsupported-case abstention: {sum(r['expected_outcome'] for r in negatives)}/{len(negatives)}.",
            f"Accepted response citation-reference checks: {len(success)}/{len(success)}; this does not measure entailment.",
        ]
        if latencies:
            lines += [
                f"Successful Q&A latency: p50 {latencies[math.ceil(len(latencies) * 0.5) - 1] / 1000:.2f}s; "
                f"p95 {latencies[math.ceil(len(latencies) * 0.95) - 1] / 1000:.2f}s (nearest rank; excludes errors)."
            ]
        incoming = sum(
            sum(
                u.get(k) or 0 for k in ["input_tokens", "cached_input_tokens", "cache_write_tokens"]
            )
            for u in usage
        )
        outgoing = sum(u.get("output_tokens") or 0 for u in usage)
        lines += [
            f"Known HTTP tokens: {incoming:,} input, {outgoing:,} output. Missing timeout usage is unknown, not free.",
            "",
            "## Case review",
            "",
            "| Case | Outcome | Error | Expected-citation recall |",
            "|---|---|---|---:|",
        ]
        for row in rows:
            recall = row.get("expected_citation_recall")
            lines.append(
                f"| {row['id']} | {'pass' if row['expected_outcome'] else 'flag'} | "
                f"{row.get('error') or '—'} | {f'{recall:.3f}' if recall is not None else '—'} |"
            )
    lines += ["", "## Limits", ""] + [f"- {item}" for item in report["limitations"]]
    lines += [
        "- Correctness and faithfulness require reviewing each claim against its cited excerpt; structural checks are not factual accuracy.",
        "- See the JSON artifact for exact questions, expected facts, retrieved/cited source, usage, and ungraded manual-review fields.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.input.read_text())))


if __name__ == "__main__":
    main()
