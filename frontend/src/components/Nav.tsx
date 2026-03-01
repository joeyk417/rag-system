"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import HealthBadge from "@/components/HealthBadge";
import { clearKeys } from "@/lib/auth";

const links = [
  { href: "/chat", label: "Chat" },
  { href: "/documents", label: "Documents" },
  { href: "/admin", label: "Admin" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearKeys();
    router.push("/setup");
  }

  return (
    <nav className="flex h-screen w-52 flex-shrink-0 flex-col border-r border-slate-200 bg-slate-50 px-4 py-6">
      <div className="mb-8">
        <span className="text-lg font-semibold text-slate-800">RAG QA</span>
        <p className="mt-0.5 text-xs text-slate-400">Phase 1 Sign-off</p>
      </div>

      <ul className="flex flex-col gap-1">
        {links.map(({ href, label }) => {
          const active = pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-brand-600 text-white"
                    : "text-slate-600 hover:bg-slate-200"
                }`}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto flex flex-col gap-3">
        <HealthBadge />
        <button
          onClick={handleLogout}
          className="rounded-md px-3 py-1.5 text-left text-xs text-slate-500 hover:bg-slate-200"
        >
          Change keys
        </button>
      </div>
    </nav>
  );
}
