"use client";

import { useEffect, useState } from "react";
import { getKeys } from "@/lib/auth";
import {
  createTenant,
  listTenants,
  patchTenant,
  type TenantResponse,
  type TenantCreateResponse,
} from "@/lib/api";

export default function AdminPage() {
  const [tenants, setTenants] = useState<TenantResponse[]>([]);
  const [loadError, setLoadError] = useState("");

  // Create form
  const [newTenantId, setNewTenantId] = useState("");
  const [newName, setNewName] = useState("");
  const [newConfig, setNewConfig] = useState("{}");
  const [createError, setCreateError] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Patch modal
  const [patchTarget, setPatchTarget] = useState<TenantResponse | null>(null);
  const [patchConfig, setPatchConfig] = useState("{}");
  const [patchError, setPatchError] = useState("");
  const [patching, setPatching] = useState(false);

  const { adminKey } = getKeys();

  async function loadTenants() {
    if (!adminKey) {
      setLoadError("No admin key stored. Go to Setup and enter your Admin API Key.");
      return;
    }
    try {
      const data = await listTenants(adminKey);
      setTenants(data);
      setLoadError("");
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : "Failed to load tenants");
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadTenants(); }, []);

  async function handleCreate() {
    setCreating(true);
    setCreateError("");
    setCreatedKey(null);
    try {
      const config = JSON.parse(newConfig);
      const res: TenantCreateResponse = await createTenant(adminKey, {
        tenant_id: newTenantId,
        name: newName,
        config,
      });
      setCreatedKey(res.api_key);
      setNewTenantId("");
      setNewName("");
      setNewConfig("{}");
      loadTenants();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(tenant: TenantResponse) {
    try {
      const updated = await patchTenant(adminKey, tenant.id, {
        is_active: !tenant.is_active,
      });
      setTenants((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Patch failed");
    }
  }

  function openPatch(tenant: TenantResponse) {
    setPatchTarget(tenant);
    setPatchConfig(JSON.stringify(tenant.config, null, 2));
    setPatchError("");
  }

  async function handlePatch() {
    if (!patchTarget) return;
    setPatching(true);
    setPatchError("");
    try {
      const config = JSON.parse(patchConfig);
      await patchTenant(adminKey, patchTarget.id, { config });
      setPatchTarget(null);
      loadTenants();
    } catch (e: unknown) {
      setPatchError(e instanceof Error ? e.message : "Patch failed");
    } finally {
      setPatching(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-6 text-2xl font-semibold">Admin — Tenants</h1>

      {!adminKey && (
        <div className="mb-6 rounded-md bg-yellow-50 px-4 py-3 text-sm text-yellow-700">
          No admin key stored.{" "}
          <a href="/setup" className="underline font-medium">
            Go to Setup
          </a>{" "}
          and enter your Admin API Key.
        </div>
      )}

      {/* Create tenant */}
      <section className="mb-8 rounded-lg border border-slate-200 p-6">
        <h2 className="mb-4 text-base font-semibold text-slate-700">Create Tenant</h2>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">Tenant ID (slug) *</span>
            <input
              value={newTenantId}
              onChange={(e) => setNewTenantId(e.target.value)}
              placeholder="new_tenant_au"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <span className="text-xs text-slate-400">Lowercase letters, numbers, underscores only</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">Display Name *</span>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="New Tenant Pty Ltd"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </label>
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">Config (JSON)</span>
            <textarea
              value={newConfig}
              onChange={(e) => setNewConfig(e.target.value)}
              rows={3}
              className="rounded-md border border-slate-300 px-3 py-2 font-mono text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </label>
        </div>

        {createError && (
          <p className="mt-3 text-sm text-red-600">{createError}</p>
        )}

        {createdKey && (
          <div className="mt-3 rounded-md bg-green-50 px-4 py-3">
            <p className="text-xs font-semibold text-green-700">
              Tenant created. Save this API Key — it is shown only once:
            </p>
            <code className="mt-1 block break-all font-mono text-sm text-green-800 select-all">
              {createdKey}
            </code>
          </div>
        )}

        <button
          onClick={handleCreate}
          disabled={creating || !newTenantId.trim() || !newName.trim() || !adminKey}
          className="mt-4 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium
                     text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {creating ? "Creating…" : "Create Tenant"}
        </button>
      </section>

      {/* Tenant list */}
      {loadError && (
        <p className="mb-4 rounded-md bg-red-50 px-4 py-2 text-sm text-red-600">{loadError}</p>
      )}

      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold text-slate-700">All Tenants</h2>
        <button onClick={loadTenants} className="text-xs text-brand-600 hover:underline">
          Refresh
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Tenant ID</th>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Schema</th>
              <th className="px-4 py-3 text-left">Active</th>
              <th className="px-4 py-3 text-left">Created</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {tenants.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                  {adminKey ? "No tenants found." : "Enter admin key to view tenants."}
                </td>
              </tr>
            ) : (
              tenants.map((t) => (
                <tr key={t.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs font-medium">{t.tenant_id}</td>
                  <td className="px-4 py-3">{t.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{t.schema_name}</td>
                  <td className="px-4 py-3">
                    {/* Toggle switch */}
                    <button
                      onClick={() => toggleActive(t)}
                      aria-label={t.is_active ? "Deactivate" : "Activate"}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                                  ${t.is_active ? "bg-green-500" : "bg-slate-300"}`}
                    >
                      <span
                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform
                                    ${t.is_active ? "translate-x-4.5" : "translate-x-0.5"}`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {new Date(t.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openPatch(t)}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      Edit config
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Patch config modal */}
      {patchTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-1 text-base font-semibold">Edit Config</h3>
            <p className="mb-3 text-xs text-slate-400">
              Tenant: <code className="font-mono">{patchTarget.tenant_id}</code>
            </p>
            <textarea
              value={patchConfig}
              onChange={(e) => setPatchConfig(e.target.value)}
              rows={10}
              className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            {patchError && (
              <p className="mt-2 text-sm text-red-600">{patchError}</p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setPatchTarget(null)}
                className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handlePatch}
                disabled={patching}
                className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium
                           text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >
                {patching ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
