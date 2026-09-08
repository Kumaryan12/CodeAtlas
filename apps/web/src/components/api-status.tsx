"use client";

import { useCallback, useEffect, useState } from "react";

export function ApiStatus() {
  const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");
  const check = useCallback(async (signal?: AbortSignal) => {
    setStatus("checking");
    try {
      const response = await fetch("/api/health", { signal, cache: "no-store" });
      if (!signal?.aborted) setStatus(response.ok ? "online" : "offline");
    } catch {
      if (!signal?.aborted) setStatus("offline");
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void check(controller.signal);
    return () => controller.abort();
  }, [check]);
  return <div className="api-status">
    <span role="status"><span className={`dot ${status}`} />API {status}</span>
    <button onClick={() => void check()} disabled={status === "checking"} aria-label="Recheck API connection">↻</button>
  </div>;
}
