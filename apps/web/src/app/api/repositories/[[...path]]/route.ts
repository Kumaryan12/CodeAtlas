import { NextRequest, NextResponse } from "next/server";
import { isAllowedOrigin } from "@/lib/proxy-policy";

export const dynamic = "force-dynamic";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Context = { params: Promise<{ path?: string[] }> };

function allowedPath(parts: string[]) {
  if (parts.length === 0) return true;
  if (!uuid.test(parts[0])) return false;
  if (parts.length === 1) return true;
  if (parts.length === 2) return ["files", "symbols", "graph"].includes(parts[1]);
  return parts.length === 3 && parts[1] === "files" && uuid.test(parts[2]);
}

async function proxy(request: NextRequest, context: Context) {
  const parts = (await context.params).path ?? [];
  if (!allowedPath(parts) || (request.method === "POST" && parts.length > 0)) {
    return NextResponse.json({ error: { code: "not_found", message: "Unknown repository route." } }, { status: 404 });
  }
  let body: string | undefined;
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    if (!isAllowedOrigin(origin, request.headers.get("host"), request.nextUrl.protocol)) {
      return NextResponse.json({ error: { code: "invalid_origin", message: "Cross-origin imports are not allowed." } }, { status: 403 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ error: { code: "invalid_request", message: "Send JSON with a repository URL." } }, { status: 415 });
    }
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 4096) {
          await reader.cancel();
          return NextResponse.json({ error: { code: "request_too_large", message: "Import request is too large." } }, { status: 413 });
        }
        chunks.push(value);
      }
    }
    body = Buffer.concat(chunks).toString("utf8");
  }
  const upstream = new URL(`${process.env.API_BASE_URL ?? "http://127.0.0.1:8000"}/api/repositories${parts.length ? `/${parts.join("/")}` : ""}`);
  for (const key of ["limit", "offset", "file_id"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) upstream.searchParams.set(key, value);
  }
  try {
    const response = await fetch(upstream, {
      method: request.method, body, headers: { "Content-Type": "application/json" },
      cache: "no-store", signal: AbortSignal.timeout(request.method === "POST" ? 150_000 : 10_000),
    });
    const data: unknown = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: {
      code: "api_unavailable",
      message: "The API did not respond. Refresh the repository list before retrying; an import may still be running.",
    } }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
