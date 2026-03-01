import type { Metadata } from "next";
import "./globals.css";
import NavWrapper from "@/components/NavWrapper";

export const metadata: Metadata = {
  title: "RAG QA Tool",
  description: "Multi-tenant RAG system — Phase 1 sign-off interface",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden bg-white text-slate-900 antialiased">
        <NavWrapper />
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </body>
    </html>
  );
}
