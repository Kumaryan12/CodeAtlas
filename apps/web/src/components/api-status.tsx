"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "online" | "offline";

async function fetchStatus(signal?: AbortSignal): Promise<Status> {
  try {
    const response = await fetch("/api/health", { signal, cache: "no-store" });
    return response.ok ? "online" : "offline";
  } catch {
    return "offline";
  }
}

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();
    void fetchStatus(controller.signal).then((result) => {
      if (!controller.signal.aborted) setStatus(result);
    });
    return () => controller.abort();
  }, []);

  async function refresh() {
    setStatus("checking");
    setStatus(await fetchStatus());
  }

  return <div className="api-status">
    <span role="status"><span className={`dot ${status}`} />API {status}</span>
    <button onClick={() => void refresh()} disabled={status === "checking"} aria-label="Recheck API connection">↻</button>
  </div>;
}
