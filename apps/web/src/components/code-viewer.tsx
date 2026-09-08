import { useMemo, useState } from "react";
import type { FileDetail, SourceSymbol } from "@/lib/repositories";
import { highlightSource } from "@/lib/highlight";

const LINES_PER_PAGE = 200;

export function CodeViewer({ file }: { file: FileDetail }) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<SourceSymbol | null>(null);
  const [symbolQuery, setSymbolQuery] = useState("");
  const lines = useMemo(() => file.source.split(/\r?\n/), [file.source]);
  const start = page * LINES_PER_PAGE;
  const visible = lines.slice(start, start + LINES_PER_PAGE);
  const code = visible.join("\n");
  const highlighted = highlightSource(code, file.language);
  const matches = file.symbols.filter((symbol) => symbol.name.toLowerCase().includes(symbolQuery.toLowerCase()));

  function select(symbol: SourceSymbol) {
    setSelected(symbol);
    setPage(Math.floor((symbol.start_line - 1) / LINES_PER_PAGE));
  }

  return <>
    <section className="code-panel" aria-label={`Source code: ${file.path}`}>
      <div className="panel-heading code-heading"><span title={file.path}>{file.path}</span><span>{file.language}</span></div>
      {file.warning && <p className="notice warning" role="status">{file.warning}</p>}
      {selected && <div className="location-label">{selected.name} · lines {selected.start_line}–{selected.end_line}</div>}
      <div className="code-scroll" tabIndex={0} aria-label="Scrollable source code">
        <div className="line-numbers" aria-hidden="true">{visible.map((_, index) => <span key={index}
          className={selected && start + index + 1 >= selected.start_line && start + index + 1 <= selected.end_line ? "highlighted-line" : ""}>{start + index + 1}</span>)}</div>
        <pre><code>{highlighted === null ? code : <span dangerouslySetInnerHTML={{ __html: highlighted }} />}</code></pre>
      </div>
      <div className="code-pagination"><span>Lines {start + 1}–{Math.min(start + LINES_PER_PAGE, lines.length)} of {lines.length}</span>
        <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
        <button disabled={start + LINES_PER_PAGE >= lines.length} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </section>
    <aside className="symbol-panel" aria-label="File symbols">
      <div className="panel-heading">SYMBOLS <span>{file.symbols.length}</span></div>
      <label className="sr-only" htmlFor="symbol-filter">Filter symbols</label>
      <input id="symbol-filter" className="file-filter" placeholder="Find a symbol…" value={symbolQuery} onChange={(event) => setSymbolQuery(event.target.value)} />
      <div className="symbol-list">{matches.slice(0, 200).map((symbol) => <button
        key={symbol.id} className={selected?.id === symbol.id ? "symbol-entry selected" : "symbol-entry"}
        onClick={() => select(symbol)} title={`${symbol.name}(${symbol.parameters.join(", ")})`}>
        <span className="symbol-kind">{symbol.kind}</span><strong>{symbol.name}</strong><small>L{symbol.start_line}–{symbol.end_line}</small>
      </button>)}</div>
      {!matches.length && <p className="panel-empty">No matching symbols in this file.</p>}
      {matches.length > 200 && <p className="panel-empty">Showing 200 of {matches.length}. Refine your search.</p>}
      {selected && <div className="symbol-detail"><p className="eyebrow">PARAMETERS</p><code>{selected.parameters.join(", ") || "None"}</code>
        {selected.parent_id && <p>Inside {file.symbols.find((symbol) => symbol.id === selected.parent_id)?.name ?? "parent symbol"}</p>}
      </div>}
      {!!file.imports.length && <details className="import-list"><summary>Imports · {file.imports.length}</summary>{file.imports.map((item) => <code key={item}>{item}</code>)}</details>}
    </aside>
  </>;
}
