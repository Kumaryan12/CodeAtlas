"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { RetrievalDiagnostics } from "@/components/retrieval-diagnostics";
import { request } from "@/lib/repositories";
import { citationLabel, type Answer, type Citation, type IndexStatus, type Retrieval } from "@/lib/qa";

type Turn = { question: string; answer: Answer };

export function RepositoryAsk({ repositoryId, onOpenSource }: {
  repositoryId: string;
  onOpenSource: (citation: Citation) => void;
}) {
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const [strategy, setStrategy] = useState<"semantic" | "hybrid">("hybrid");
  const [preview, setPreview] = useState<{ question: string; retrieval: Retrieval } | null>(null);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState<"index" | "ask" | "retrieve" | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const operation = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void request<IndexStatus>(`/${repositoryId}/index`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) { setIndex(data); setError(""); } })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => { controller.abort(); operation.current?.abort(); };
  }, [repositoryId, revision]);

  async function buildIndex() {
    const controller = new AbortController();
    operation.current = controller;
    setBusy("index"); setError("");
    try {
      const data = await request<IndexStatus>(`/${repositoryId}/index`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: controller.signal,
      });
      if (!controller.signal.aborted) setIndex(data);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Indexing failed.");
    } finally { if (!controller.signal.aborted) setBusy(null); }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy || index?.status !== "ready") return;
    const submitted = question.trim();
    const controller = new AbortController();
    operation.current = controller;
    setBusy("ask"); setError("");
    try {
      const answer = await request<Answer>(`/${repositoryId}/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: submitted, strategy }), signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setTurns((previous) => [...previous.slice(-9), { question: submitted, answer }]);
        setQuestion("");
      }
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Question failed.");
    } finally { if (!controller.signal.aborted) setBusy(null); }
  }

  async function previewContext() {
    if (!question.trim() || busy || index?.status !== "ready") return;
    const submitted = question.trim();
    const controller = new AbortController();
    operation.current = controller;
    setBusy("retrieve"); setError("");
    try {
      const retrieval = await request<Retrieval>(`/${repositoryId}/retrieve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: submitted, strategy }), signal: controller.signal,
      });
      if (!controller.signal.aborted) setPreview({ question: submitted, retrieval });
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Retrieval failed.");
    } finally { if (!controller.signal.aborted) setBusy(null); }
  }

  return <section className="ask-panel" aria-label="Ask about this snapshot">
    <div className="ask-heading"><div><p className="eyebrow">REPOSITORY ASSISTANT</p>
      <h2>Answers you can inspect.</h2><p className="muted">Ask about implementation, then follow the citations into source.</p></div>
      <span className="ask-state">{busy === "index" ? "Building index…" : index?.status.replaceAll("_", " ") ?? "Loading index…"}</span>
    </div>
    {error && <div className="notice error" role="alert">{error} <button disabled={!!busy} onClick={() => setRevision((value) => value + 1)}>Refresh status</button></div>}
    {index && <div className="ask-index">
      {!index.configured ? <p>Embeddings are not configured. Set <code>CODEATLAS_OPENAI_API_KEY</code> in the API server’s environment and restart the API, then refresh status.</p>
        : index.status !== "ready" ? <><p>{index.status === "stale" ? "The embedding model changed. Rebuild this snapshot’s index." : "Build a semantic index to enable questions for this snapshot."}</p>
          <p className="muted">This sends eligible source excerpts to {index.provider} for embeddings. Model usage may incur charges.</p>
          <button className="primary-button" disabled={!!busy} onClick={() => void buildIndex()}>{busy === "index" ? "Generating embeddings…" : "Build semantic index"}</button></>
          : <p><strong>{index.chunk_count.toLocaleString()} excerpts indexed</strong> · {index.embedding_model}</p>}
      {!index.reasoning_configured && <p>Answers require <code>{index.reasoning_key_name}</code> on the API server. Context preview only needs embeddings.</p>}
      <p className="muted">Answers: {index.reasoning_provider} · {index.answer_model}. Questions and retrieved excerpts are sent to this provider.</p>
      {index.skipped_long_lines > 0 && <p className="notice warning">{index.skipped_long_lines} oversized source lines were excluded from retrieval.</p>}
    </div>}
    <div className="ask-conversation" aria-live="polite" aria-busy={busy === "ask"}>
      {!turns.length && <div className="ask-empty"><span className="eyebrow">START WITH A SPECIFIC QUESTION</span>
        <p>“Where are incoming requests validated?”</p><p>“How does the login function handle errors?”</p></div>}
      {turns.map((turn, turnIndex) => <article className="ask-turn" key={turnIndex}>
        <h3>{turn.question}</h3>
        {turn.answer.status === "insufficient_context" ? <p className="notice warning">The retrieved code does not provide enough evidence to answer. Try naming a file, function, or narrower behavior.</p>
          : turn.answer.claims.map((claim, claimIndex) => <div className="ask-claim" key={claimIndex}><p>{claim.text}</p>
            <div className="citation-links">{[...new Set(claim.citation_ids)].map((id) => {
              const citation = turn.answer.citations.find((item) => item.id === id);
              return citation ? <button key={id} onClick={() => onOpenSource(citation)} title={citationLabel(citation)}>{citationLabel(citation)}</button> : null;
            })}</div></div>)}
        {turn.answer.citations.length > 0 && <details className="ask-evidence"><summary>Inspect supporting excerpts · {turn.answer.citations.length}</summary>
          {turn.answer.citations.map((citation) => <div key={citation.id}><button onClick={() => onOpenSource(citation)}>{citationLabel(citation)}</button>
            {citation.symbol && <span className="muted"> · {citation.symbol}</span>}<pre><code>{citation.source}</code></pre></div>)}
        </details>}
        <RetrievalDiagnostics retrieval={turn.answer.retrieval} onOpenSource={onOpenSource} />
        <p className="ask-meta">{turn.answer.model} · {(turn.answer.duration_ms / 1000).toFixed(1)} s · snapshot {turn.answer.commit_sha?.slice(0, 7) ?? "unknown"}</p>
      </article>)}
      {busy && <p role="status" className="muted">{busy === "index" ? "Embedding source excerpts. This may take up to two minutes." : busy === "retrieve" ? "Retrieving context without generating an answer…" : "Retrieving relevant code and composing a cited answer…"}</p>}
    </div>
    {preview && <section className="retrieval-preview" aria-label="Retrieval preview"><h3>Context preview: {preview.question}</h3>
      <RetrievalDiagnostics retrieval={preview.retrieval} onOpenSource={onOpenSource} />
      <button className="secondary-button" onClick={() => setPreview(null)}>Dismiss preview</button></section>}
    <form className="ask-form" onSubmit={(event) => void ask(event)}>
      <div className="retrieval-controls"><label htmlFor="retrieval-strategy">Retrieval mode</label>
        <select id="retrieval-strategy" value={strategy} disabled={!!busy} onChange={(event) => setStrategy(event.target.value as "semantic" | "hybrid")}>
          <option value="hybrid">Hybrid + dependencies</option><option value="semantic">Semantic baseline</option>
        </select></div>
      <label htmlFor="repository-question">Your question</label>
      <textarea id="repository-question" rows={3} maxLength={1500} value={question} onChange={(event) => setQuestion(event.target.value)}
        disabled={!!busy || !index?.configured || index.status !== "ready"} placeholder="How does this repository…" />
      <div><p className="muted">Each question is independent. Preview uses a query embedding without generating an answer. Answers can be wrong; inspect the source.</p>
        <button type="button" className="secondary-button" onClick={() => void previewContext()} disabled={!!busy || !question.trim() || !index?.configured || index.status !== "ready"}>Preview context</button>
        <button className="primary-button" disabled={!!busy || !question.trim() || !index?.configured || !index.reasoning_configured || index.status !== "ready"}>Ask</button></div>
    </form>
    <p className="ask-meta">The last 10 answers remain in this view until you switch snapshots or reload.</p>
  </section>;
}
