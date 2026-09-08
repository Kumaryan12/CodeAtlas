import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch(`${process.env.API_BASE_URL ?? "http://127.0.0.1:8000"}/api/health`, {
      cache: "no-store", signal: AbortSignal.timeout(4000),
    });
    const body: unknown = await response.json();
    if (!response.ok || typeof body !== "object" || body === null ||
        !("status" in body) || body.status !== "ok" ||
        !("service" in body) || body.service !== "codeatlas-api") {
      throw new Error("Invalid API health response");
    }
    return NextResponse.json({ status: "ok" });
  } catch {
    return NextResponse.json({ error: { code: "api_unavailable", message: "Cannot reach the CodeAtlas API." } }, { status: 503 });
  }
}
