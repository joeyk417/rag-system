// All fetch wrappers — types mirror backend Pydantic schemas exactly.
// In local dev, requests go to /api/* which Next.js proxies to the backend (no CORS).
// In Docker/staging, NEXT_PUBLIC_API_URL is set and requests go directly to the backend.

const apiBase = (): string =>
  typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL ?? "");

// ---- Types ----------------------------------------------------------------

export interface HealthResponse {
  status: string;
  env: string;
}

export interface IngestResponse {
  job_id: string | null;
  status: "pending" | "completed";
  document_id: string | null;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  document_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Source {
  doc_number: string | null;
  title: string | null;
  page_number: number;
  s3_key: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  query: string;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  doc_number: string | null;
  doc_type: string | null;
  revision: string | null;
  title: string | null;
  classification: string | null;
  page_count: number | null;
  status: string;
  created_at: string;
}

export interface TenantResponse {
  id: string;
  tenant_id: string;
  name: string;
  schema_name: string;
  s3_prefix: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface TenantCreateResponse extends TenantResponse {
  api_key: string; // shown once only
}

// ---- Helpers ---------------------------------------------------------------

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = (body.detail as string) ?? (body.message as string) ?? detail;
    } catch {
      // body is not JSON
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

function tenantHeaders(tenantKey: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-API-Key": tenantKey,
  };
}

function adminHeaders(adminKey: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Admin-Key": adminKey,
  };
}

// ---- Public API ------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${apiBase()}/api/v1/health`);
  return handleResponse<HealthResponse>(res);
}

export async function postIngest(
  tenantKey: string,
  file: File
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);
  // Do NOT set Content-Type — browser sets multipart/form-data with boundary automatically
  const res = await fetch(`${apiBase()}/api/v1/ingest`, {
    method: "POST",
    headers: { "X-API-Key": tenantKey },
    body: form,
  });
  return handleResponse<IngestResponse>(res);
}

export async function getJobStatus(
  tenantKey: string,
  jobId: string
): Promise<JobStatusResponse> {
  const res = await fetch(`${apiBase()}/api/v1/ingest/${jobId}`, {
    headers: tenantHeaders(tenantKey),
  });
  return handleResponse<JobStatusResponse>(res);
}

export async function postChat(
  tenantKey: string,
  query: string
): Promise<ChatResponse> {
  const res = await fetch(`${apiBase()}/api/v1/chat`, {
    method: "POST",
    headers: tenantHeaders(tenantKey),
    body: JSON.stringify({ query }),
  });
  return handleResponse<ChatResponse>(res);
}

export async function getDocuments(
  tenantKey: string,
  docType?: string
): Promise<DocumentResponse[]> {
  const params = docType ? `?doc_type=${encodeURIComponent(docType)}` : "";
  const res = await fetch(`${apiBase()}/api/v1/documents${params}`, {
    headers: tenantHeaders(tenantKey),
  });
  return handleResponse<DocumentResponse[]>(res);
}

export async function deleteDocument(
  tenantKey: string,
  documentId: string
): Promise<void> {
  const res = await fetch(`${apiBase()}/api/v1/documents/${documentId}`, {
    method: "DELETE",
    headers: { "X-API-Key": tenantKey },
  });
  return handleResponse<void>(res);
}

export async function createTenant(
  adminKey: string,
  payload: { tenant_id: string; name: string; config: Record<string, unknown> }
): Promise<TenantCreateResponse> {
  const res = await fetch(`${apiBase()}/api/v1/admin/tenants`, {
    method: "POST",
    headers: adminHeaders(adminKey),
    body: JSON.stringify(payload),
  });
  return handleResponse<TenantCreateResponse>(res);
}

export async function listTenants(adminKey: string): Promise<TenantResponse[]> {
  const res = await fetch(`${apiBase()}/api/v1/admin/tenants`, {
    headers: adminHeaders(adminKey),
  });
  return handleResponse<TenantResponse[]>(res);
}

export async function patchTenant(
  adminKey: string,
  tenantUuid: string,
  payload: { config?: Record<string, unknown>; is_active?: boolean }
): Promise<TenantResponse> {
  const res = await fetch(`${apiBase()}/api/v1/admin/tenants/${tenantUuid}`, {
    method: "PATCH",
    headers: adminHeaders(adminKey),
    body: JSON.stringify(payload),
  });
  return handleResponse<TenantResponse>(res);
}
