from __future__ import annotations as _annotations

from copy import deepcopy

from .context import AirlineAgentContext

MOCK_ITINERARIES = {
    "disrupted": {
        "name": "Paris to New York to Austin",
        "passenger_name": "Morgan Lee",
        "confirmation_number": "IR-D204",
        "seat_number": "14C",
        "baggage_tag": "BG20488",
        "segments": [
            {
                "flight_number": "PA441",
                "origin": "Paris (CDG)",
                "destination": "New York (JFK)",
                "departure": "2024-12-09 14:10",
                "arrival": "2024-12-09 17:40",
                "status": "因天气延误 5 小时，预计 19:55 起飞",
                "gate": "B18",
            },
            {
                "flight_number": "NY802",
                "origin": "New York (JFK)",
                "destination": "Austin (AUS)",
                "departure": "2024-12-09 19:10",
                "arrival": "2024-12-09 22:35",
                "status": "因首段延误导致错过后续联程",
                "gate": "C7",
            },
        ],
        "rebook_options": [
            {
                "flight_number": "NY950",
                "origin": "New York (JFK)",
                "destination": "Austin (AUS)",
                "departure": "2024-12-10 09:45",
                "arrival": "2024-12-10 12:30",
                "seat": "2A (front row)",
                "note": "已为受影响旅客自动协调合作伙伴航班",
            },
            {
                "flight_number": "NY982",
                "origin": "New York (JFK)",
                "destination": "Austin (AUS)",
                "departure": "2024-12-10 13:20",
                "arrival": "2024-12-10 16:05",
                "seat": "3C",
                "note": "若早班已满时的备选",
            },
        ],
        "vouchers": {
            "hotel": "JFK T5 合作酒店过夜，最高报销 180 美元",
            "meal": "延误餐券 60 美元",
            "ground": "往返酒店地面交通券 40 美元",
        },
    },
    "on_time": {
        "name": "On-time commuter flight",
        "passenger_name": "Taylor Lee",
        "confirmation_number": "LL0EZ6",
        "seat_number": "23A",
        "baggage_tag": "BG55678",
        "segments": [
            {
                "flight_number": "FLT-123",
                "origin": "San Francisco (SFO)",
                "destination": "Los Angeles (LAX)",
                "departure": "2024-12-09 16:10",
                "arrival": "2024-12-09 17:35",
                "status": "准点，按计划运行",
                "gate": "A10",
            }
        ],
        "rebook_options": [],
        "vouchers": {},
    },
}


def apply_itinerary_defaults(ctx: AirlineAgentContext, scenario_key: str | None = None) -> None:
    """Populate the context with a demo itinerary if missing."""
    target_key = scenario_key or ctx.scenario or "disrupted"
    data = MOCK_ITINERARIES.get(target_key) or next(iter(MOCK_ITINERARIES.values()))
    ctx.scenario = target_key
    ctx.passenger_name = ctx.passenger_name or data.get("passenger_name")
    ctx.confirmation_number = ctx.confirmation_number or data.get("confirmation_number")
    segments = data.get("segments", [])
    if ctx.flight_number is None and segments:
        ctx.flight_number = segments[0].get("flight_number")
    ctx.seat_number = ctx.seat_number or data.get("seat_number")
    if ctx.itinerary is None:
        ctx.itinerary = deepcopy(segments)
    # Set trip endpoints for display without exposing the full itinerary
    if segments:
        ctx.origin = ctx.origin or segments[0].get("origin")
        ctx.destination = ctx.destination or segments[-1].get("destination")


def get_itinerary_for_flight(flight_number: str | None) -> tuple[str, dict] | None:
    """Return (scenario_key, itinerary) if the flight is present in a mock itinerary."""
    if not flight_number:
        return None
    for key, itinerary in MOCK_ITINERARIES.items():
        for segment in itinerary.get("segments", []):
            if segment.get("flight_number", "").lower() == flight_number.lower():
                return key, itinerary
        for segment in itinerary.get("rebook_options", []):
            if segment.get("flight_number", "").lower() == flight_number.lower():
                return key, itinerary
    return None


def active_itinerary(ctx: AirlineAgentContext) -> tuple[str, dict]:
    """Resolve the active itinerary for the current context."""
    if ctx.scenario and ctx.scenario in MOCK_ITINERARIES:
        return ctx.scenario, MOCK_ITINERARIES[ctx.scenario]
    match = get_itinerary_for_flight(ctx.flight_number)
    if match:
        ctx.scenario = match[0]
        return match
    ctx.scenario = "disrupted"
    return ctx.scenario, MOCK_ITINERARIES["disrupted"]
