export type Repository = {
  id: string;
  full_name: string;
  url: string;
  branch: string | null;
  commit_sha: string | null;
  description: string | null;
  status: "importing" | "ready" | "partial" | "failed";
  error_message: string | null;
  file_count: number;
  symbol_count: number;
  source_bytes: number;
  warning_count: number;
  languages: Record<string, number>;
  skipped: Record<string, number>;
  created_at: string;
};
export type SourceSymbol = {
  id: string;
  name: string;
  kind: string;
  start_line: number;
  end_line: number;
  parameters: string[];
  parent_id: string | null;
};
export type RepositoryFile = {
  id: string;
  repository_id: string;
  path: string;
  language: "python" | "javascript" | "typescript";
  size_bytes: number;
  symbol_count: number;
  warning: string | null;
};
export type FileDetail = RepositoryFile & { source: string; imports: string[]; symbols: SourceSymbol[] };
export type Page<T> = { items: T[]; total: number };

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/repositories${path}`, { ...options, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message ?? "The repository request failed.");
  return data as T;
}

export async function fetchFiles(repositoryId: string, signal: AbortSignal): Promise<RepositoryFile[]> {
  const files: RepositoryFile[] = [];
  let total: number;
  do {
    const page = await request<Page<RepositoryFile>>(`/${repositoryId}/files?limit=1000&offset=${files.length}`, { signal });
    files.push(...page.items);
    total = page.total;
    if (page.items.length === 0) break;
  } while (files.length < total);
  return files;
}
