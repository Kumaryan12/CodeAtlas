import { citationLabel, formatRetrievalScore, type Citation, type Retrieval } from "@/lib/qa";

export function RetrievalDiagnostics({ retrieval, onOpenSource }: {
  retrieval: Retrieval;
  onOpenSource: (citation: Citation) => void;
}) {
  return <details className="retrieval-diagnostics">
    <summary>Retrieved context · {retrieval.hits.length} excerpts · {retrieval.strategy}</summary>
    <p className="ask-meta">Searched {retrieval.candidate_count.toLocaleString()} indexed excerpts in {(retrieval.duration_ms / 1000).toFixed(2)} s. Scores are ranking signals, not confidence.</p>
    <div className="retrieval-table-scroll"><table>
      <thead><tr><th scope="col">Source / selection</th><th scope="col">Cosine</th><th scope="col">Keyword</th><th scope="col">Exact match</th><th scope="col">Fusion</th></tr></thead>
      <tbody>{retrieval.hits.map((hit) => <tr key={hit.chunk_id}>
        <td><button onClick={() => onOpenSource(hit)}>{hit.id} · {citationLabel(hit)}</button>
          <span>{hit.symbol ?? "Module excerpt"} · {hit.reason === "dependency" ? "Dependency expansion" : hit.reason === "semantic" ? "Semantic baseline" : "Hybrid ranking"}</span>
          {hit.via_file_path && <small>Adjacent to {hit.via_file_path}</small>}</td>
        <td>{formatRetrievalScore(hit.semantic_score)}</td><td>{formatRetrievalScore(hit.keyword_score)}</td>
        <td>{hit.symbol_score > 0 ? "Yes" : "—"}</td><td>{formatRetrievalScore(hit.fusion_score, 4)}</td>
      </tr>)}</tbody>
    </table></div>
    {retrieval.notes.map((note, i) => <p key={i} className="ask-meta">{note}</p>)}
    <p className="ask-meta">Retrieval version: {retrieval.version}. Context selection can differ from score order when dependency expansion is used.</p>
  </details>;
}
