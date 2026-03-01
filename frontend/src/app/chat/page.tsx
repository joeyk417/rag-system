"use client";

import { useState } from "react";
import { getKeys } from "@/lib/auth";
import { postChat, type ChatResponse } from "@/lib/api";
import SourceCard from "@/components/SourceCard";

const PRESET_QUERIES = [
  { id: "1",  label: "#1", text: "What torque for M20 Grade 10.9 bolts lubricated?" },
  { id: "2",  label: "#2", text: "What PPE is required for screen installation?" },
  { id: "3",  label: "#3", text: "What are the slope angles on the HF-2160?" },
  { id: "4",  label: "#4", text: "What motor bolt size for the HF-2472?" },
  { id: "5",  label: "#5", text: "Shore A hardness for PU-500 panels?" },
  { id: "6",  label: "#6", text: "Max feed size for PU-600 series?" },
  { id: "7",  label: "#7", text: "What is NR-35-SA compound used for?" },
  { id: "8",  label: "#8", text: "Cure temperature for NR-55-HA?" },
  { id: "9",  label: "#9", text: "How many field technicians does EA employ?" },
  { id: "10", label: "#10", text: "What is the new hire competency timeline?" },
  { id: "B1", label: "Bonus #1", text: "What panel spec applies to the HF-2472?" },
  { id: "B2", label: "Bonus #2", text: "What are the training requirements before installation?" },
];

export default function ChatPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState("");
  const [activePreset, setActivePreset] = useState<string | null>(null);

  async function submit(q: string, presetId?: string) {
    if (!q.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    setActivePreset(presetId ?? null);
    try {
      const { tenantKey } = getKeys();
      const data = await postChat(tenantKey, q.trim());
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handlePreset(id: string, text: string) {
    setQuery(text);
    submit(text, id);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-2xl font-semibold">Chat</h1>
      <p className="mb-6 text-sm text-slate-500">
        Query the EA knowledge base. Click a validation query or type your own.
      </p>

      {/* Preset validation queries */}
      <section className="mb-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Validation Queries (click to run)
        </h2>
        <div className="flex flex-wrap gap-2">
          {PRESET_QUERIES.map(({ id, label, text }) => (
            <button
              key={id}
              onClick={() => handlePreset(id, text)}
              disabled={loading}
              title={text}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-40
                ${activePreset === id && loading
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-slate-300 text-slate-600 hover:border-brand-400 hover:text-brand-600"
                }`}
            >
              {label}
            </button>
          ))}
        </div>
        {activePreset && !loading && (
          <p className="mt-2 text-xs text-slate-400 italic truncate">
            {PRESET_QUERIES.find((p) => p.id === activePreset)?.text}
          </p>
        )}
      </section>

      {/* Free-form input */}
      <div className="flex gap-2">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(query);
            }
          }}
          rows={3}
          placeholder="Ask a question about EA documents… (Enter to send, Shift+Enter for newline)"
          className="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm
                     focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          onClick={() => submit(query)}
          disabled={loading || !query.trim()}
          className="self-end rounded-md bg-brand-600 px-5 py-2 text-sm font-medium
                     text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "…" : "Send"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Loading spinner */}
      {loading && (
        <div className="mt-8 flex items-center gap-2 text-sm text-slate-400">
          <span
            className="inline-block h-4 w-4 animate-spin rounded-full border-2
                       border-slate-200 border-t-brand-500"
          />
          Running CRAG agent…
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="mt-6 space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="mb-2 text-xs text-slate-400 italic">Query: {result.query}</p>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
              {result.answer}
            </div>
          </div>

          {result.sources.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Sources ({result.sources.length})
              </h3>
              <div className="grid gap-2 sm:grid-cols-2">
                {result.sources.map((src, i) => (
                  <SourceCard key={i} source={src} index={i} />
                ))}
              </div>
            </div>
          )}

          {result.sources.length === 0 && (
            <p className="text-xs text-slate-400 italic">
              No document sources cited (web search fallback was used or no relevant chunks found).
            </p>
          )}
        </div>
      )}
    </div>
  );
}
