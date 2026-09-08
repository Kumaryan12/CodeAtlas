import { useMemo, useState } from "react";
import { buildFileTree, type TreeNode } from "@/lib/file-tree";
import type { RepositoryFile } from "@/lib/repositories";

function Branch({ nodes, activeId, onSelect, depth = 0 }: {
  nodes: TreeNode[]; activeId: string | null; onSelect: (id: string) => void; depth?: number;
}) {
  return <ul className="file-branches">{nodes.map((node) => <li key={node.path}>
    {node.fileId ? <button className={node.fileId === activeId ? "file-entry selected" : "file-entry"}
      aria-current={node.fileId === activeId ? "true" : undefined} title={node.path}
      onClick={() => onSelect(node.fileId!)}><span aria-hidden="true">▤</span>{node.name}</button>
      : <details open={depth < 1}><summary title={node.path}>{node.name}</summary>
        <Branch nodes={node.children} activeId={activeId} onSelect={onSelect} depth={depth + 1} />
      </details>}
  </li>)}</ul>;
}

export function FileTree({ files, activeId, onSelect }: {
  files: RepositoryFile[]; activeId: string | null; onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => files.filter((file) => file.path.toLowerCase().includes(query.toLowerCase())), [files, query]);
  const tree = useMemo(() => buildFileTree(visible), [visible]);
  return <nav className="file-panel" aria-label="Repository files">
    <div className="panel-heading">FILES <span>{files.length}</span></div>
    <label className="sr-only" htmlFor="file-filter">Filter files by path</label>
    <input id="file-filter" className="file-filter" placeholder="Filter by path…" value={query} onChange={(event) => setQuery(event.target.value)} />
    {query ? <ul className="file-branches">{visible.map((file) => <li key={file.id}><button
      className={file.id === activeId ? "file-entry selected" : "file-entry"}
      title={file.path} onClick={() => onSelect(file.id)}>{file.path}</button></li>)}</ul>
      : <Branch nodes={tree} activeId={activeId} onSelect={onSelect} />}
    {!visible.length && <p className="panel-empty">No matching source files.</p>}
  </nav>;
}
