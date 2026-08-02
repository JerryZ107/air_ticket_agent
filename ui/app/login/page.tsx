"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("zhangsan");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      router.push("/");
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-100 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg bg-white p-8 shadow-md"
      >
        <h1 className="mb-2 text-xl font-semibold text-gray-900">航班订票助理</h1>
        <p className="mb-6 text-sm text-gray-500">请登录后使用 Agent（演示账号 zhangsan / demo123）</p>
        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
        <label className="mb-2 block text-sm font-medium text-gray-700">用户名</label>
        <input
          className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <label className="mb-2 block text-sm font-medium text-gray-700">密码</label>
        <input
          type="password"
          className="mb-6 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "登录中…" : "登录"}
        </button>
        <p className="mt-4 text-xs text-gray-400">管理员：admin / demo123</p>
      </form>
    </main>
  );
}
