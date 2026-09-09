export function isAllowedOrigin(origin: string | null, host: string | null, protocol: string): boolean {
  // Next.js can normalize nextUrl.hostname to localhost. The actual Host header
  // preserves the address the browser used (e.g. 127.0.0.1), so compare against it.
  return origin === null || (host !== null && origin === `${protocol}//${host}`);
}


export function allowedRepositoryPath(parts: string[], method: string): boolean {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (method !== "POST" && method !== "GET") return false;
  if (parts.length === 0) return true;
  if (!uuid.test(parts[0])) return false;
  if (method === "POST") return parts.length === 2 && ["index", "ask"].includes(parts[1]);
  if (parts.length === 1) return true;
  if (parts.length === 2) return ["files", "symbols", "graph", "index"].includes(parts[1]);
  return parts.length === 3 && parts[1] === "files" && uuid.test(parts[2]);
}
