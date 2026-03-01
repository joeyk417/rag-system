const TENANT_KEY = "rag_tenant_api_key";
const ADMIN_KEY = "rag_admin_api_key";

export interface StoredKeys {
  tenantKey: string;
  adminKey: string;
}

export function getKeys(): StoredKeys {
  if (typeof window === "undefined") {
    return { tenantKey: "", adminKey: "" };
  }
  return {
    tenantKey: localStorage.getItem(TENANT_KEY) ?? "",
    adminKey: localStorage.getItem(ADMIN_KEY) ?? "",
  };
}

export function setKeys(keys: Partial<StoredKeys>): void {
  if (keys.tenantKey !== undefined) {
    localStorage.setItem(TENANT_KEY, keys.tenantKey);
  }
  if (keys.adminKey !== undefined) {
    localStorage.setItem(ADMIN_KEY, keys.adminKey);
  }
}

export function clearKeys(): void {
  localStorage.removeItem(TENANT_KEY);
  localStorage.removeItem(ADMIN_KEY);
}

export function hasKeys(): boolean {
  const { tenantKey } = getKeys();
  return tenantKey.length > 0;
}
