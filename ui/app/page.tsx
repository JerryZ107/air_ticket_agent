"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AgentPanel } from "@/components/agent-panel";
import { AuthGate } from "@/components/auth-gate";
import { SimpleChatPanel } from "@/components/simple-chat-panel";
import type { Agent, AgentEvent, GuardrailCheck } from "@/lib/types";
import { fetchBootstrapState, fetchMe, fetchThreadState, logout } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [userLabel, setUserLabel] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [guardrails, setGuardrails] = useState<GuardrailCheck[]>([]);
  const [context, setContext] = useState<Record<string, any>>({});
  const [threadId, setThreadId] = useState<string | null>(null);

  const normalizeEvents = useCallback((items: AgentEvent[]) => {
    if (!items.length) return items;
    const now = Date.now();
    const latestNonProgress = items
      .filter((e) => e.type !== "progress_update")
      .reduce((max, e) => Math.max(max, e.timestamp.getTime()), 0);
    const pruned = items.filter((e) => {
      if (e.type !== "progress_update") return true;
      const ts = e.timestamp.getTime();
      // Drop old progress once a newer non-progress exists, or after 15s
      if (latestNonProgress && ts < latestNonProgress) return false;
      if (now - ts > 15000) return false;
      return true;
    });
    return pruned;
  }, []);

  const hydrateState = useCallback(async (id: string | null) => {
    if (!id) return;
    const data = await fetchThreadState(id);
    if (!data) return;

    setCurrentAgent(data.current_agent || "");
    setContext(data.context || {});
    if (Array.isArray(data.agents)) setAgents(data.agents);
    if (Array.isArray(data.events)) {
      setEvents(
        data.events.map((e: any) => ({
          ...e,
          timestamp: new Date(e.timestamp ?? Date.now()),
        }))
      );
    }
    if (Array.isArray(data.guardrails)) {
      setGuardrails(
        data.guardrails.map((g: any) => ({
          ...g,
          timestamp: new Date(g.timestamp ?? Date.now()),
        }))
      );
    }
  }, []);

  useEffect(() => {
    fetchMe().then((u) => setUserLabel(`${u.display_name || u.username} (${u.role})`));
  }, []);

  useEffect(() => {
    if (threadId) {
      void hydrateState(threadId);
    }
  }, [threadId, hydrateState]);

  useEffect(() => {
    (async () => {
      const bootstrap = await fetchBootstrapState();
      if (!bootstrap) return;
      setThreadId(bootstrap.thread_id || null);
      if (bootstrap.current_agent) setCurrentAgent(bootstrap.current_agent);
      if (Array.isArray(bootstrap.agents)) setAgents(bootstrap.agents);
      if (bootstrap.context) setContext(bootstrap.context);
      if (Array.isArray(bootstrap.events)) {
        setEvents(
          normalizeEvents(
            bootstrap.events.map((e: any) => ({
              ...e,
              timestamp: new Date(e.timestamp ?? Date.now()),
            }))
          )
        );
      }
      if (Array.isArray(bootstrap.guardrails)) {
        setGuardrails(
          bootstrap.guardrails.map((g: any) => ({
            ...g,
            timestamp: new Date(g.timestamp ?? Date.now()),
          }))
        );
      }
    })();
  }, []);

  const handleBindThread = useCallback((id: string) => {
    setThreadId(id);
  }, []);

  const handleResponseEnd = useCallback(
    (id: string) => {
      setThreadId(id);
      void hydrateState(id);
    },
    [hydrateState]
  );

  return (
    <AuthGate>
      <main className="flex h-screen flex-col gap-2 bg-gray-100 p-2">
        <header className="flex items-center justify-between rounded bg-white px-4 py-2 text-sm shadow-sm">
          <span className="font-medium text-gray-800">航班订票助理</span>
          <div className="flex items-center gap-3">
            {userLabel && <span className="text-gray-500">{userLabel}</span>}
            <button
              type="button"
              className="text-blue-600 hover:underline"
              onClick={async () => {
                await logout();
                router.push("/login");
              }}
            >
              退出
            </button>
          </div>
        </header>
        <div className="flex min-h-0 flex-1 gap-2">
          <AgentPanel
            agents={agents}
            currentAgent={currentAgent}
            events={events}
            guardrails={guardrails}
            context={context}
          />
          <SimpleChatPanel
            threadId={threadId}
            onThreadChange={handleBindThread}
            onResponseEnd={handleResponseEnd}
          />
        </div>
      </main>
    </AuthGate>
  );
}
