export type IndexStatus = {
  status: "not_indexed" | "ready" | "stale";
  configured: boolean;
  provider: string;
  embedding_model: string;
  answer_model: string;
  chunk_count: number;
  skipped_long_lines: number;
  indexed_at: string | null;
};

export type Citation = {
  id: string;
  file_id: string;
  file_path: string;
  symbol: string | null;
  start_line: number;
  end_line: number;
  source: string;
};

export type Retrieval = {
  repository_id: string;
  strategy: "semantic" | "hybrid";
  version: string;
  candidate_count: number;
  duration_ms: number;
  notes: string[];
  hits: (Citation & {
    chunk_id: string;
    semantic_score: number | null;
    keyword_score: number;
    symbol_score: number;
    fusion_score: number;
    reason: "semantic" | "hybrid" | "dependency";
    via_file_id: string | null;
    via_file_path: string | null;
  })[];
};

export function formatRetrievalScore(score: number | null, digits = 3): string {
  return score === null || !Number.isFinite(score) ? "—" : score.toFixed(digits);
}

export type Answer = {
  retrieval: Retrieval;
  repository_id: string;
  commit_sha: string | null;
  status: "answered" | "insufficient_context";
  claims: { text: string; citation_ids: string[] }[];
  citations: Citation[];
  model: string;
  duration_ms: number;
};

export function citationLabel(citation: Citation): string {
  return `${citation.file_path}:${citation.start_line}–${citation.end_line}`;
}

export function citationPage(startLine: number, linesPerPage = 200): number {
  return Math.floor((Math.max(1, startLine) - 1) / linesPerPage);
}
