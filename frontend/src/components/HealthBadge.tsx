"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

type Status = "unknown" | "ok" | "error";

export default function HealthBadge() {
  const [status, setStatus] = useState<Status>("unknown");
  const [env, setEnv] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const data = await getHealth();
        if (!cancelled) {
          setStatus("ok");
          setEnv(data.env);
        }
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    check();
    const interval = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const dot =
    status === "ok"
      ? "bg-green-500"
      : status === "error"
        ? "bg-red-500"
        : "bg-yellow-400 animate-pulse";

  const label =
    status === "ok"
      ? `API · ${env}`
      : status === "error"
        ? "API offline"
        : "Checking…";

  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
