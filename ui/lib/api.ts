// Fetch ChatKit thread state for the Agent panel
export async function fetchThreadState(threadId: string) {
  try {
    const res = await fetch(`/chatkit/state?thread_id=${encodeURIComponent(threadId)}`, {
      credentials: "include",
    });
    if (!res.ok) throw new Error(`State API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error fetching thread state:", err);
    return null;
  }
}

export async function fetchBootstrapState() {
  try {
    const res = await fetch(`/chatkit/bootstrap`, { credentials: "include" });
    if (!res.ok) throw new Error(`Bootstrap API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error bootstrapping state:", err);
    return null;
  }
}

export async function sendChatMessage(message: string, threadId?: string | null) {
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message, thread_id: threadId ?? null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
            : detail
              ? JSON.stringify(detail)
              : `Chat API error: ${res.status}`;
      throw new Error(msg || `Chat API error: ${res.status}`);
    }
    return res.json() as Promise<{ thread_id: string; reply: string }>;
  } catch (err) {
    console.error("Error sending chat message:", err);
    throw err;
  }
}

export async function login(username: string, password: string) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "登录失败");
  }
  return res.json();
}

export async function fetchMe() {
  const res = await fetch("/api/auth/me", { credentials: "include" });
  if (!res.ok) throw new Error("unauthorized");
  return res.json();
}

export async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
}
