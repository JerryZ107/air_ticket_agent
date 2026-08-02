/** Agent 内部英文名 -> 界面中文名 */
export const AGENT_NAME_ZH: Record<string, string> = {
  "Triage Agent": "分诊客服",
  "Flight Information Agent": "航班信息专员",
  "Booking and Cancellation Agent": "订票改签专员",
  "Seat and Special Services Agent": "选座与特殊服务专员",
  "FAQ Agent": "常见问题专员",
  "Refunds and Compensation Agent": "退款与补偿专员",
};

export function agentDisplayName(name: string): string {
  return AGENT_NAME_ZH[name] ?? name;
}
