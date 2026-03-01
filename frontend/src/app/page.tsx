"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasKeys } from "@/lib/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (hasKeys()) {
      router.replace("/chat");
    } else {
      router.replace("/setup");
    }
  }, [router]);

  return null;
}
