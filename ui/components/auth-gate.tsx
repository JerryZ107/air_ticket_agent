"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchMe } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    fetchMe()
      .then(() => setReady(true))
      .catch(() => router.replace("/login"));
  }, [router]);

  if (!ready) {
    return (
      <main className="flex h-screen items-center justify-center bg-gray-100 text-gray-600">
        正在验证登录…
      </main>
    );
  }

  return <>{children}</>;
}
