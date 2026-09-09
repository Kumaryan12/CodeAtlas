export function isAllowedOrigin(origin: string | null, host: string | null, protocol: string): boolean {
  // Next.js can normalize nextUrl.hostname to localhost. The actual Host header
  // preserves the address the browser used (e.g. 127.0.0.1), so compare against it.
  return origin === null || (host !== null && origin === `${protocol}//${host}`);
}
