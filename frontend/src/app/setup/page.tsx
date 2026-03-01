"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setKeys } from "@/lib/auth";
import { getHealth } from "@/lib/api";

export default function SetupPage() {
  const router = useRouter();
  const [tenantKey, setTenantKey] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [status, setStatus] = useState<"idle" | "checking" | "error">("idle");
  const [error, setError] = useState("");

  async function handleConnect() {
    if (!tenantKey.trim()) {
      setError("Tenant API Key is required");
      return;
    }
    setStatus("checking");
    setError("");
    try {
      await getHealth();
      setKeys({ tenantKey: tenantKey.trim(), adminKey: adminKey.trim() });
      router.push("/chat");
    } catch (e: unknown) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Could not reach API");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-1 text-2xl font-semibold text-slate-800">RAG QA Tool</h1>
        <p className="mb-6 text-sm text-slate-500">
          Enter your API keys to start testing. Keys are stored in your browser only.
        </p>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium text-slate-700">
              Tenant API Key <span className="text-red-500">*</span>
            </span>
            <input
              type="password"
              value={tenantKey}
              onChange={(e) => setTenantKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              placeholder="ea-dev-key-local-testing-only"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium text-slate-700">
              Admin API Key{" "}
              <span className="font-normal text-slate-400">(optional — needed for Admin panel)</span>
            </span>
            <input
              type="password"
              value={adminKey}
              onChange={(e) => setAdminKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              placeholder="admin key from .env"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </label>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
          )}

          <button
            onClick={handleConnect}
            disabled={status === "checking"}
            className="mt-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium
                       text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {status === "checking" ? "Connecting…" : "Connect"}
          </button>
        </div>

        <p className="mt-6 text-xs text-slate-400">
          Keys are never sent to any server other than the RAG API at{" "}
          <code className="font-mono">
            {process.env.NEXT_PUBLIC_API_URL ?? "localhost:8000"}
          </code>
        </p>
      </div>
    </div>
  );
}
