"use client";

import { PanelSection } from "./panel-section";
import { Card, CardContent } from "@/components/ui/card";
import { BookText } from "lucide-react";

interface ConversationContextProps {
  context: Record<string, any>;
}

const CONTEXT_LABELS: Record<string, string> = {
  passenger_name: "乘客姓名",
  confirmation_number: "确认号",
  seat_number: "座位号",
  flight_number: "航班号",
  account_number: "账户号",
  special_service_note: "特殊服务备注",
  origin: "出发地",
  destination: "目的地",
  vouchers: "补偿券",
};

export function ConversationContext({ context }: ConversationContextProps) {
  const formatValue = (value: any) => {
    if (value === null || value === undefined || value === "") return "空";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    if (Array.isArray(value)) {
      if (value.length === 0) return "[]";
      const primitives = value.every(
        (item) => ["string", "number", "boolean"].includes(typeof item)
      );
      if (primitives && value.length <= 3) {
        return value.join("，");
      }
      return `${value.length} 项`;
    }
    if (typeof value === "object") {
      const keys = Object.keys(value);
      if (keys.length === 0) return "对象";
      return `{${keys.slice(0, 3).join("，")}${keys.length > 3 ? "，…" : ""}}`;
    }
    return String(value);
  };

  return (
    <PanelSection
      title="会话上下文"
      icon={<BookText className="h-4 w-4 text-blue-600" />}
    >
      <Card className="bg-gradient-to-r from-white to-gray-50 border-gray-200 shadow-sm">
        <CardContent className="p-3">
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(context).map(([key, value]) => (
              <div
                key={key}
                className="flex items-center gap-2 bg-white p-2 rounded-md border border-gray-200 shadow-sm transition-all"
              >
                {(() => {
                  const rendered = formatValue(value);
                  return (
                    <>
                      <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                      <div className="text-xs space-y-1">
                        <div className="text-zinc-500 font-light">
                          {CONTEXT_LABELS[key] ?? key}：
                        </div>
                        <span
                          className={
                            value ? "text-zinc-900 font-light break-words" : "text-gray-400 italic"
                          }
                        >
                          {rendered}
                        </span>
                      </div>
                    </>
                  );
                })()}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </PanelSection>
  );
}
