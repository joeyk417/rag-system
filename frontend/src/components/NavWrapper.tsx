"use client";

import { usePathname } from "next/navigation";
import Nav from "@/components/Nav";

export default function NavWrapper() {
  const pathname = usePathname();
  if (pathname === "/setup") return null;
  return <Nav />;
}
