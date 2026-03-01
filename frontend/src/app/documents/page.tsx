"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getKeys } from "@/lib/auth";
import {
  postIngest,
  getJobStatus,
  getDocuments,
  deleteDocument,
  type DocumentResponse,
  type JobStatusResponse,
} from "@/lib/api";

interface ActiveJob {
  jobId: string;
  filename: string;
  status: JobStatusResponse["status"];
  error: string | null;
}

const DOC_TYPES = ["", "SOP", "ENG-DRW", "ENG-MAT", "STRAT"];

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ingested:   "bg-green-100 text-green-700",
    completed:  "bg-green-100 text-green-700",
    pending:    "bg-yellow-100 text-yellow-700",
    processing: "bg-blue-100 text-blue-700",
    failed:     "bg-red-100 text-red-700",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        map[status] ?? "bg-slate-100 text-slate-600"
      }`}
    >
      {status}
    </span>
  );
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([]);
  const [docTypeFilter, setDocTypeFilter] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [docsError, setDocsError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Load documents ----
  const loadDocs = useCallback(async () => {
    const { tenantKey } = getKeys();
    try {
      const data = await getDocuments(tenantKey, docTypeFilter || undefined);
      setDocs(data);
      setDocsError("");
    } catch (e: unknown) {
      setDocsError(e instanceof Error ? e.message : "Failed to load documents");
    }
  }, [docTypeFilter]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  // ---- Poll ingest jobs ----
  useEffect(() => {
    const interval = setInterval(async () => {
      const pending = activeJobs.filter(
        (j) => j.status === "pending" || j.status === "processing"
      );
      if (pending.length === 0) return;

      const { tenantKey } = getKeys();
      const updated = await Promise.all(
        pending.map(async (job) => {
          try {
            const s = await getJobStatus(tenantKey, job.jobId);
            return { ...job, status: s.status, error: s.error };
          } catch {
            return job;
          }
        })
      );

      setActiveJobs((prev) =>
        prev.map((j) => updated.find((u) => u.jobId === j.jobId) ?? j)
      );

      if (updated.some((j) => j.status === "completed")) {
        loadDocs();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [activeJobs, loadDocs]);

  // ---- Upload ----
  async function handleUpload(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF files are accepted");
      return;
    }
    setUploadError("");
    const { tenantKey } = getKeys();
    try {
      const res = await postIngest(tenantKey, file);
      if (res.status === "completed") {
        // Duplicate — already ingested
        loadDocs();
        return;
      }
      if (res.job_id) {
        setActiveJobs((prev) => [
          ...prev,
          { jobId: res.job_id!, filename: file.name, status: "pending", error: null },
        ]);
      }
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }

  async function handleDelete(id: string, filename: string) {
    if (!confirm(`Delete "${filename}" and all its chunks?`)) return;
    const { tenantKey } = getKeys();
    try {
      await deleteDocument(tenantKey, id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-6 text-2xl font-semibold">Documents</h1>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`mb-4 flex cursor-pointer flex-col items-center justify-center rounded-lg
                    border-2 border-dashed p-10 transition-colors
                    ${dragging
                      ? "border-brand-500 bg-brand-50"
                      : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
                    }`}
      >
        <svg className="mb-2 h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p className="text-sm text-slate-500">
          Drag and drop a PDF, or{" "}
          <span className="text-brand-600 underline">click to browse</span>
        </p>
        <p className="mt-1 text-xs text-slate-400">PDF files only</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => { if (e.target.files?.[0]) handleUpload(e.target.files[0]); e.target.value = ""; }}
        />
      </div>

      {uploadError && (
        <p className="mb-4 rounded-md bg-red-50 px-4 py-2 text-sm text-red-600">{uploadError}</p>
      )}

      {/* Active jobs */}
      {activeJobs.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-600">Active Ingest Jobs</h2>
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-2 text-left">File</th>
                  <th className="px-4 py-2 text-left">Job ID</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Error</th>
                </tr>
              </thead>
              <tbody>
                {activeJobs.map((job) => (
                  <tr key={job.jobId} className="border-t border-slate-100">
                    <td className="px-4 py-2 font-medium">{job.filename}</td>
                    <td className="px-4 py-2 font-mono text-xs text-slate-400">
                      {job.jobId.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-2">
                      <StatusBadge status={job.status} />
                      {(job.status === "pending" || job.status === "processing") && (
                        <span className="ml-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-200 border-t-brand-500" />
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-red-500">{job.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Filter + refresh */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium text-slate-600">Filter by type:</label>
        <select
          value={docTypeFilter}
          onChange={(e) => setDocTypeFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm
                     focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {DOC_TYPES.map((t) => (
            <option key={t} value={t}>
              {t || "All"}
            </option>
          ))}
        </select>
        <button
          onClick={loadDocs}
          className="ml-auto text-xs text-brand-600 hover:underline"
        >
          Refresh
        </button>
      </div>

      {docsError && (
        <p className="mb-4 rounded-md bg-red-50 px-4 py-2 text-sm text-red-600">{docsError}</p>
      )}

      {/* Document list */}
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Doc Number</th>
              <th className="px-4 py-3 text-left">Title / Filename</th>
              <th className="px-4 py-3 text-left">Type</th>
              <th className="px-4 py-3 text-left">Rev</th>
              <th className="px-4 py-3 text-left">Pages</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Classification</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {docs.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">
                  No documents. Upload a PDF above.
                </td>
              </tr>
            ) : (
              docs.map((doc) => (
                <tr key={doc.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">
                    {doc.doc_number ?? "—"}
                  </td>
                  <td className="px-4 py-3 max-w-xs truncate">
                    {doc.title ?? doc.filename}
                  </td>
                  <td className="px-4 py-3">{doc.doc_type ?? "—"}</td>
                  <td className="px-4 py-3">{doc.revision ?? "—"}</td>
                  <td className="px-4 py-3">{doc.page_count ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="px-4 py-3">
                    {doc.classification ? (
                      <span
                        className={`text-xs font-medium ${
                          doc.classification.toUpperCase().includes("HIGH")
                            ? "text-red-600"
                            : "text-slate-500"
                        }`}
                      >
                        {doc.classification}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDelete(doc.id, doc.filename)}
                      className="text-xs text-red-400 hover:text-red-600"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-xs text-slate-400">
        {docs.length} document{docs.length !== 1 ? "s" : ""}
        {docTypeFilter ? ` of type ${docTypeFilter}` : ""}
      </p>
    </div>
  );
}
