import { NextRequest, NextResponse } from "next/server";
import { isAllowedOrigin, allowedRepositoryPath } from "@/lib/proxy-policy";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path?: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const parts = (await context.params).path ?? [];
  if (!allowedRepositoryPath(parts, request.method)) {
    return NextResponse.json({ error: { code: "not_found", message: "Unknown repository route." } }, { status: 404 });
  }
  let body: string | undefined;
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    if (!isAllowedOrigin(origin, request.headers.get("host"), request.nextUrl.protocol)) {
      return NextResponse.json({ error: { code: "invalid_origin", message: "Cross-origin requests are not allowed." } }, { status: 403 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ error: { code: "invalid_request", message: "Send an application/json request." } }, { status: 415 });
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
          return NextResponse.json({ error: { code: "request_too_large", message: "Request is too large." } }, { status: 413 });
        }
        chunks.push(value);
      }
    }
    body = Buffer.concat(chunks).toString("utf8");
  }
  const upstream = new URL(`${process.env.API_BASE_URL ?? "http://127.0.0.1:8000"}/api/repositories${parts.length ? `/${parts.join("/")}` : ""}`);
  for (const key of ["limit", "offset", "file_id", "view"]) {
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
      message: "The API did not respond. Refresh status before retrying; the operation may still be running.",
    } }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
