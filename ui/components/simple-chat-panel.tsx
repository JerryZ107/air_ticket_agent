"use client";

import { useCallback, useRef, useState } from "react";
import { Send } from "lucide-react";
import { sendChatMessage } from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type SimpleChatPanelProps = {
  threadId?: string | null;
  onThreadChange?: (threadId: string) => void;
  onResponseEnd?: (threadId: string) => void;
};

const START_PROMPTS = [
  { label: "更换座位", prompt: "请帮我把座位改到 14C。" },
  { label: "航班状态", prompt: "FLT-123 航班现在是什么状态？" },
  {
    label: "错过后续航班",
    prompt:
      "我从巴黎经纽约飞奥斯汀，第一段延误了，错过后续航班，能帮我处理吗？",
  },
];

export function SimpleChatPanel({
  threadId,
  onThreadChange,
  onResponseEnd,
}: SimpleChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeThreadRef = useRef<string | null>(threadId ?? null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;

      setError(null);
      setLoading(true);
      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", content: trimmed },
      ]);
      setInput("");
      scrollToBottom();

      try {
        const data = await sendChatMessage(trimmed, activeThreadRef.current);
        if (!data) {
          setError("发送失败，请确认后端是否在 8001 端口运行。");
          return;
        }
        activeThreadRef.current = data.thread_id;
        onThreadChange?.(data.thread_id);
        setMessages((prev) => [
          ...prev,
          { id: `a-${Date.now()}`, role: "assistant", content: data.reply },
        ]);
        onResponseEnd?.(data.thread_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "未知错误");
      } finally {
        setLoading(false);
        scrollToBottom();
      }
    },
    [loading, onResponseEnd, onThreadChange, scrollToBottom]
  );

  const showStartScreen = messages.length === 0 && !loading;

  return (
    <div className="flex flex-col h-full flex-1 bg-white shadow-sm border border-gray-200 border-t-0 rounded-xl min-h-0">
      <div className="bg-blue-600 text-white h-12 px-4 flex items-center rounded-t-xl shrink-0">
        <h2 className="font-semibold text-sm sm:text-base lg:text-lg">
          客户视图
        </h2>
        <span className="ml-auto text-xs opacity-80">在线客服</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {showStartScreen && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-8">
            <p className="text-lg text-gray-700 font-medium">
              您好！我是您的航空助手，今天需要什么帮助？
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {START_PROMPTS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => void sendMessage(item.prompt)}
                  className="px-3 py-2 text-sm rounded-full border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl px-4 py-2 text-sm text-gray-500">
              思考中…
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t p-3 shrink-0">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void sendMessage(input);
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息…"
            disabled={loading}
            className="flex-1 rounded-full border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="h-10 w-10 flex items-center justify-center rounded-full bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
