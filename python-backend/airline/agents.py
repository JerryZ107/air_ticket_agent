from __future__ import annotations as _annotations

import random
import string

from agents import Agent, RunContextWrapper, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from llm_config import MODEL, MODEL_FLASH, MODEL_PRO

from .context import AirlineAgentChatContext
from .demo_data import apply_itinerary_defaults
from .guardrails import jailbreak_guardrail, relevance_guardrail
from .hydrate import hydrate_first_booking
from .grounding import STRICT_GROUNDING
from .mcp_integration import mcp_actor_hint
from .tools import (
    assign_special_service_seat,
    book_new_flight,
    cancel_flight,
    display_seat_map,
    faq_lookup_tool,
    flight_status_tool,
    get_matching_flights,
    get_trip_details,
    issue_compensation,
    list_bookings_tool,
    list_customer_bookings_tool,
    rebook_flight_tool,
    tools_for_agent,
    update_seat,
)

_ZH = "请始终使用简体中文与客户交流。\n" + STRICT_GROUNDING + "\n"


def _admin_on_behalf_hint(ctx: AirlineAgentChatContext) -> str:
    if ctx.user_role != "admin":
        return ""
    return (
        "\n你是管理员会话：list_bookings 列出全库最近订单（含旅客用户名）；"
        "查某一旅客用 list_customer_bookings(customer_username=...)。"
        "代客取消/改签/换座时必须在工具中传入 on_behalf_of_username=旅客用户名，"
        "并与确认号所属旅客一致；写操作会记入 audit on_behalf_of。\n"
    )


def _login_booking_hint(ctx: AirlineAgentChatContext) -> str:
    if not ctx.username:
        return ""
    return (
        f"\n客户已登录（{ctx.username}），订单与写操作工具已绑定该账户。"
        f"若确认号未知，先调用 list_bookings 或 get_trip_details，勿索要确认号；"
        f"列表为空时再说明无订单。\n"
    )


def seat_services_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[未知]"
    flight = ctx.flight_number or "[未知]"
    seat = ctx.seat_number or "[未分配]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{_ZH}"
        "你是选座与特殊服务专员，负责处理选座变更及医疗/特殊服务请求。\n"
        f"1. 客户确认号为 {confirmation}，航班 {flight}，当前座位 {seat}。"
        "若信息缺失则先 list_bookings 再办理；若已有信息则直接办理，并记录特殊需求。\n"
        "2. 可提供座位图或记录具体座位。前排/医疗需求用 assign_special_service_seat，"
        "普通换座用 update_seat；若客户想可视化选座，调用 display_seat_map。\n"
        "3. 确认新座位并告知已保存至确认号。\n"
        "重要：请求明确且数据齐全时，可在同一轮连续调用多个工具，无需等待用户回复。"
        "完成后最多转接一次：若需延误补偿支持则转退款与补偿专员，否则返回分诊客服。\n"
        "若与选座或特殊服务无关，转回分诊客服。"
        f"{mcp_actor_hint(ctx.username)}"
        f"{_login_booking_hint(ctx)}"
        f"{_admin_on_behalf_hint(ctx)}"
    )


seat_special_services_agent = Agent[AirlineAgentChatContext](
    name="Seat and Special Services Agent",
    model=MODEL,
    handoff_description="办理选座变更及医疗/特殊服务座位。",
    instructions=seat_services_instructions,
    tools=tools_for_agent(
        "seat_special_services_agent",
        [update_seat, assign_special_service_seat, display_seat_map],
    ),
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def flight_information_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[未知]"
    flight = ctx.flight_number or "[未知]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{_ZH}"
        "你是航班信息专员，提供航班状态、联程风险及备选方案。\n"
        f"1. 确认号 {confirmation}，航班 {flight}。未知时先 list_bookings；有数据时不要阻塞。\n"
        "2. 立即使用 flight_status_tool 告知当前状态，并说明延误是否导致错过后续联程。\n"
        "3. 若延误或取消影响行程，调用 search_flights（或 get_matching_flights）提供备选，再转订票改签专员完成改签。\n"
        "4. 已登录时描述「客户订单」必须先 list_bookings，仅引用工具返回的确认号，禁止编造或混用演示行程。\n"
        "自主执行：可链式调用多个工具，数据齐全时每条消息只转接一次，无需等待用户确认。"
        "若客户询问行李、退款等，单次转接至对应专员。"
        f"{mcp_actor_hint(ctx.username)}"
        f"{_login_booking_hint(ctx)}"
        f"{_admin_on_behalf_hint(ctx)}"
    )


flight_information_agent = Agent[AirlineAgentChatContext](
    name="Flight Information Agent",
    model=MODEL,
    handoff_description="查询航班状态、联程影响及备选航班。",
    instructions=flight_information_instructions,
    tools=tools_for_agent(
        "flight_information_agent",
        [flight_status_tool, get_matching_flights],
    ),
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def booking_cancellation_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[未知]"
    flight = ctx.flight_number or "[未知]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{_ZH}"
        "你是订票改签专员，负责取消、预订或改签。\n"
        f"1. 基于确认号 {confirmation} 和航班 {flight} 办理；未知时先 list_bookings，齐全则直接操作。\n"
        "2. 客户需新航班时，先 search_flights 查备选；有确认号改签用 rebook_flight（确认号不变），"
        "全新预订可用 book_new_flight。\n"
        "3. 取消时确认详情后使用 cancel_flight（须 actor_username）；订座偏好可转选座专员。\n"
        "4. 总结变更内容，告知更新后的确认号与座位。\n"
        "自主执行：数据齐全时同一轮可多次调用工具，每条消息只转接一次。"
        "改签后优先转选座专员（有座位偏好）或退款与补偿专员（遇延误），否则回分诊客服。"
        f"{mcp_actor_hint(ctx.username)}"
        f"{_login_booking_hint(ctx)}"
        f"{_admin_on_behalf_hint(ctx)}"
    )


booking_cancellation_agent = Agent[AirlineAgentChatContext](
    name="Booking and Cancellation Agent",
    model=MODEL_PRO,
    handoff_description="办理新订、延误改签及航班取消。",
    instructions=booking_cancellation_instructions,
    tools=tools_for_agent(
        "booking_cancellation_agent",
        [cancel_flight, get_matching_flights, book_new_flight, rebook_flight_tool, list_bookings_tool],
    ),
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def refunds_compensation_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[未知]"
    case_id = ctx.compensation_case_id or "[未创建]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{_ZH}"
        "你是退款与补偿专员，帮助客户了解并获取延误补偿。\n"
        f"1. 基于确认号 {confirmation} 办理；未知时先 list_bookings。\n"
        "2. 若遇延误或错过后续航班，先用 faq_lookup_tool 查询补偿政策，"
        f"再汇总问题并用 issue_compensation 创建案例、发放酒店/餐券。当前案例号：{case_id}。\n"
        "3. 说明已发放内容及需保留的单据；完成后回分诊客服。\n"
        "自主执行：数据齐全时链式调用工具，每条消息只转接一次。"
        f"{mcp_actor_hint(ctx.username)}"
        f"{_login_booking_hint(ctx)}"
        f"{_admin_on_behalf_hint(ctx)}"
    )


refunds_compensation_agent = Agent[AirlineAgentChatContext](
    name="Refunds and Compensation Agent",
    model=MODEL,
    handoff_description="创建补偿案例，发放酒店/餐券等延误支持。",
    instructions=refunds_compensation_instructions,
    tools=tools_for_agent(
        "refunds_compensation_agent",
        [issue_compensation, faq_lookup_tool],
    ),
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def faq_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{_ZH}"
        "你是常见问题（FAQ）专员，通常由分诊客服转接而来。\n"
        "1. 识别客户最后一个问题。\n"
        "2. 必须调用 faq_lookup_tool；仅根据返回内容用中文回答。\n"
        "3. 若返回含「手册未收录」或「未检索到」，原样告知客户手册暂无该信息，禁止猜测。\n"
        "4. 若需补偿或行李协助，可提议转接对应专员（不要描述内部转接过程）。"
        f"{mcp_actor_hint(run_context.context.state.username)}"
    )


faq_agent = Agent[AirlineAgentChatContext](
    name="FAQ Agent",
    model=MODEL_FLASH,
    handoff_description="解答政策、行李、座位、补偿等常见问题。",
    instructions=faq_instructions,
    tools=tools_for_agent("faq_agent", [faq_lookup_tool]),
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def triage_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    login_block = ""
    if ctx.username:
        login_block = (
            f"客户已登录（{ctx.username}）。若询问自己的订单、有无订票、行程或确认号且未提供编号，"
            f"必须先调用 get_trip_details，用工具结果直接中文回答；"
            f"仅列单即可时不要转专员。无订单则明确告知。\n"
        )
    if ctx.user_role == "admin":
        login_block += (
            "管理员查全库最近订单须转订票改签专员并调用 list_bookings，"
            "或查指定旅客用 list_customer_bookings。仅列单时不要多余转接。\n"
        )
    return (
        f"{RECOMMENDED_PROMPT_PREFIX} "
        f"{_ZH}"
        "你是分诊客服，将客户引导至最合适的专员："
        "航班信息专员（状态/备选）、订票改签专员（订退改）、"
        "选座与特殊服务专员（选座）、常见问题专员（政策）、"
        "退款与补偿专员（延误补偿）。\n"
        f"{login_block}"
        + (
            ""
            if ctx.username
            else "若消息提及巴黎/纽约/奥斯汀且上下文缺失，先调用 get_trip_details 填充航班/确认号。"
        )
        + "请求明确时立即转接，让专员自主完成多步操作，不要在每步工具调用后要求用户确认。"
        "每条消息最多转接一次：最多做一次准备（一个工具调用）然后转接。"
        f"{mcp_actor_hint(ctx.username)}"
        f"{_admin_on_behalf_hint(ctx)}"
    )


triage_agent = Agent[AirlineAgentChatContext](
    name="Triage Agent",
    model=MODEL_FLASH,
    handoff_description="将请求路由至合适的专员（航班、订票、选座、FAQ、补偿等）。",
    instructions=triage_instructions,
    tools=tools_for_agent("triage_agent", [get_trip_details, list_customer_bookings_tool]),
    handoffs=[],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


async def on_seat_booking_handoff(context: RunContextWrapper[AirlineAgentChatContext]) -> None:
    """Ensure context is hydrated when handing off to the seat and special services agent."""
    if context.context.state.user_id:
        await hydrate_first_booking(context.context.state)
        return
    if await hydrate_first_booking(context.context.state):
        return
    apply_itinerary_defaults(context.context.state)
    if context.context.state.flight_number is None:
        context.context.state.flight_number = f"FLT-{random.randint(100, 999)}"
    if context.context.state.confirmation_number is None:
        context.context.state.confirmation_number = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )


async def on_booking_handoff(
    context: RunContextWrapper[AirlineAgentChatContext]
) -> None:
    """Prepare context when handing off to booking and cancellation."""
    if context.context.state.user_id:
        await hydrate_first_booking(context.context.state)
        return
    if await hydrate_first_booking(context.context.state):
        return
    apply_itinerary_defaults(context.context.state)
    if context.context.state.confirmation_number is None:
        context.context.state.confirmation_number = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
    if context.context.state.flight_number is None:
        context.context.state.flight_number = f"FLT-{random.randint(100, 999)}"


triage_agent.handoffs = [
    flight_information_agent,
    handoff(agent=booking_cancellation_agent, on_handoff=on_booking_handoff),
    handoff(agent=seat_special_services_agent, on_handoff=on_seat_booking_handoff),
    faq_agent,
    refunds_compensation_agent,
]
faq_agent.handoffs.append(triage_agent)
seat_special_services_agent.handoffs.extend([refunds_compensation_agent, triage_agent])
flight_information_agent.handoffs.extend(
    [
        handoff(agent=booking_cancellation_agent, on_handoff=on_booking_handoff),
        triage_agent,
    ]
)
booking_cancellation_agent.handoffs.extend(
    [
        handoff(agent=seat_special_services_agent, on_handoff=on_seat_booking_handoff),
        refunds_compensation_agent,
        triage_agent,
    ]
)
refunds_compensation_agent.handoffs.extend([faq_agent, triage_agent])
