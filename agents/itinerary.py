from __future__ import annotations

from datetime import date
from datetime import timedelta

from geo_utils import distance_km, has_location
from llm_client import DeepSeekClient
from state import Attraction, DayPlan, Hotel, ItineraryResult, TravelPlanState
from timing_utils import itinerary_llm_enabled, timed_step


CITY_TRAVEL_SPEED_KM_PER_HOUR = 18.0
ROUTE_DISTANCE_FACTOR = 1.35


def generate_itinerary(state: TravelPlanState) -> ItineraryResult:
    llm_result = _try_llm_itinerary(state)
    if llm_result is not None:
        return _finalize_itinerary(state, llm_result)
    return _finalize_itinerary(state, _generate_rule_based_itinerary(state))


def _generate_rule_based_itinerary(state: TravelPlanState) -> ItineraryResult:
    requirement = state["requirement"]
    attraction_result = state["attraction_result"]
    transportation_result = state["transportation_result"]
    booking_result = state["booking_result"]
    budget_result = state["budget_result"]

    attraction_names = _ordered_recommended_attraction_names(state)
    attraction_groups = _cluster_attractions_by_distance(
        attractions=attraction_result.attractions,
        preferred_names=attraction_names,
        day_count=requirement.days or 1,
    )
    selected_hotel = (
        booking_result.recommended_hotels[0]
        if booking_result.recommended_hotels
        else None
    )
    hotel_name = selected_hotel.name if selected_hotel else None

    day_count = requirement.days or 1
    days = []
    for index in range(day_count):
        day_date = (
            requirement.start_date + timedelta(days=index)
            if requirement.start_date
            else None
        )
        daily_group = (
            attraction_groups[index]
            if index < len(attraction_groups)
            else []
        )
        daily_attractions = (
            [item.name for item in daily_group]
            if daily_group
            else _slice_for_day(attraction_names, index, day_count)
        )

        morning = daily_attractions[:1]

        afternoon = daily_attractions[1:]
        days.append(
            DayPlan(
                date=day_date,
                theme=_build_day_theme(index, daily_attractions),
                weather=_weather_for_date(attraction_result.weather, day_date),
                morning=morning,
                afternoon=afternoon,
                transfer_notes=_build_transfer_notes(selected_hotel, daily_group),
                hotel=hotel_name,
                estimated_daily_cost=round(
                    budget_result.total_cost / day_count, 2
                )
                if day_count
                else None,
            )
        )

    warnings = (
        attraction_result.notes
        + transportation_result.limitations
        + booking_result.limitations
    )
    highlights = attraction_names[: min(3, len(attraction_names))]

    return ItineraryResult(
        days=days,
        summary=_build_summary(requirement.destination_city or "目的地", day_count),
        highlights=highlights,
        travel_tips=_build_travel_tips(state),
        budget_note=_build_budget_note(state),
        transport_note=transportation_result.selection_reason,
        warnings=warnings,
    )


def itinerary_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("itinerary"):
        return {
            "itinerary_result": generate_itinerary(state),
            "current_phase": "itinerary",
            "status": "completed",
        }


def _slice_for_day(items: list[str], index: int, total_days: int) -> list[str]:
    if not items:
        return ["城市代表性景点"]
    chunk_size = max(1, (len(items) + total_days - 1) // total_days)
    start = index * chunk_size
    end = start + chunk_size
    return items[start:end] or items[-1:]


def _ordered_recommended_attraction_names(state: TravelPlanState) -> list[str]:
    attraction_result = state["attraction_result"]
    names = [item.name for item in attraction_result.recommended_attractions]
    if names:
        return names
    return [item.name for item in attraction_result.attractions]


def _cluster_attractions_by_distance(
    *,
    attractions: list[Attraction],
    preferred_names: list[str],
    day_count: int,
) -> list[list[Attraction]]:
    if day_count <= 0:
        return []

    attraction_by_name = {item.name: item for item in attractions}
    ordered = [
        attraction_by_name[name]
        for name in preferred_names
        if name in attraction_by_name
    ]
    if not ordered:
        ordered = attractions[:]

    if not ordered:
        return [[] for _ in range(day_count)]

    target_group_size = max(1, (len(ordered) + day_count - 1) // day_count)
    groups: list[list[Attraction]] = []
    remaining = ordered[:]

    while remaining and len(groups) < day_count:
        group = [remaining.pop(0)]
        while remaining and len(group) < target_group_size:
            next_item = _pop_nearest_attraction(group, remaining)
            group.append(next_item)
        groups.append(group)

    while remaining:
        smallest_group = min(groups, key=len) if groups else []
        next_item = _pop_nearest_attraction(smallest_group, remaining)
        smallest_group.append(next_item)

    while len(groups) < day_count:
        groups.append([])

    return groups


def _pop_nearest_attraction(
    group: list[Attraction],
    candidates: list[Attraction],
) -> Attraction:
    if not group or not any(has_location(item) for item in group):
        return candidates.pop(0)

    best_index = 0
    best_distance = float("inf")
    for index, candidate in enumerate(candidates):
        candidate_distance = _distance_to_group(candidate, group)
        if candidate_distance < best_distance:
            best_index = index
            best_distance = candidate_distance
    return candidates.pop(best_index)


def _distance_to_group(candidate: Attraction, group: list[Attraction]) -> float:
    if not has_location(candidate):
        return float("inf")

    distances = [
        distance_km(candidate.location, item.location)
        for item in group
        if has_location(item)
    ]
    return min(distances) if distances else float("inf")


def _build_day_theme(index: int, attractions: list[str]) -> str:
    if attractions:
        return f"Day {index + 1}：{'、'.join(attractions[:2])}"
    return f"Day {index + 1}：自由探索"


def _build_transfer_notes(
    hotel: Hotel | None,
    attractions: list[Attraction],
) -> list[str]:
    notes: list[str] = []
    located_attractions = [item for item in attractions if has_location(item)]

    if hotel is not None and has_location(hotel) and located_attractions:
        notes.append(
            _format_transfer_note(
                "\u9152\u5e97",
                located_attractions[0].name,
                distance_km(hotel.location, located_attractions[0].location),
            )
        )

    if len(located_attractions) >= 2:
        notes.append(
            _format_transfer_note(
                located_attractions[0].name,
                located_attractions[1].name,
                distance_km(located_attractions[0].location, located_attractions[1].location),
            )
        )

    return notes


def _format_transfer_note(origin: str, destination: str, straight_distance_km: float) -> str:
    route_distance = straight_distance_km * ROUTE_DISTANCE_FACTOR
    minutes = max(5, round(route_distance / CITY_TRAVEL_SPEED_KM_PER_HOUR * 60))
    return (
        f"{origin} \u2192 {destination}\uff1a\u76f4\u7ebf\u8ddd\u79bb\u7ea6{straight_distance_km:.1f} km\uff0c"
        f"\u9884\u4f30\u5e02\u5185\u51fa\u884c\u7ea6{minutes}\u5206\u949f"
    )


def _build_summary(destination: str, day_count: int) -> str:
    return f"{day_count}天行程围绕{destination}的代表性体验展开，整体节奏适中。"


def _build_travel_tips(state: TravelPlanState) -> list[str]:
    tips = []
    if state["routing_info"].degraded_mode:
        tips.append("部分结果为参考信息，出行前请再次确认实时价格与天气。")
    if state["budget_result"].is_over_budget:
        tips.append("当前方案超预算，建议优先调整交通或住宿。")
    return tips


def _build_budget_note(state: TravelPlanState) -> str:
    budget_result = state["budget_result"]
    if budget_result.remaining_budget is None:
        return "用户未提供预算，当前仅展示费用估算。"
    if budget_result.is_over_budget:
        return f"当前预计超出预算约 {abs(budget_result.remaining_budget)} 元。"
    return f"预计仍有约 {budget_result.remaining_budget} 元弹性预算。"


def _try_llm_itinerary(state: TravelPlanState) -> ItineraryResult | None:
    if not itinerary_llm_enabled():
        return None

    client = DeepSeekClient()
    if not client.configured:
        return None

    try:
        payload = client.chat_json(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(state),
            temperature=0.3,
        )
        return _itinerary_from_payload(payload)
    except Exception:
        return None


def _build_system_prompt() -> str:
    return """
你是专业旅行规划师。
请基于给定的结构化旅行事实，生成最终行程 JSON。

要求：
1. 只返回 JSON，不要返回解释文字。
2. 不要编造未提供的真实预订信息。
3. 行程应结合天数、景点、酒店、预算、交通限制进行安排。
4. 如果上游结果中带有 limitations 或 warnings，请在 warnings 中保留。
5. 不要生成餐饮安排和晚间安排，除非上游事实中提供了可靠餐厅或夜间活动数据。
6. 每天主要包含 morning、afternoon；如能根据酒店和景点经纬度推断移动关系，可在 transfer_notes 中给出交通参考。
7. 如果预算超支，请在 budget_note 和 travel_tips 中明确提醒。

JSON 格式：
{
  "days": [
    {
      "date": "YYYY-MM-DD or null",
      "theme": "string or null",
      "morning": ["string"],
      "afternoon": ["string"],
      "transfer_notes": ["string"],
      "hotel": "string or null",
      "estimated_daily_cost": "number or null"
    }
  ],
  "summary": "string",
  "highlights": ["string"],
  "travel_tips": ["string"],
  "budget_note": "string or null",
  "transport_note": "string or null",
  "warnings": ["string"]
}
""".strip()


def _build_user_prompt(state: TravelPlanState) -> str:
    requirement = state["requirement"].model_dump(mode="json")
    attraction_result = state["attraction_result"].model_dump(mode="json")
    transportation_result = state["transportation_result"].model_dump(mode="json")
    booking_result = state["booking_result"].model_dump(mode="json")
    budget_result = state["budget_result"].model_dump(mode="json")

    return f"""
请基于以下事实生成旅行行程 JSON：

requirement = {requirement}
attraction_result = {attraction_result}
transportation_result = {transportation_result}
booking_result = {booking_result}
budget_result = {budget_result}
""".strip()


def _itinerary_from_payload(payload: dict) -> ItineraryResult:
    normalized = dict(payload)
    normalized_days = []
    for raw_day in normalized.get("days", []):
        day_payload = dict(raw_day)
        raw_date = day_payload.get("date")
        day_payload["date"] = date.fromisoformat(raw_date) if raw_date else None
        normalized_days.append(day_payload)
    normalized["days"] = [DayPlan(**item) for item in normalized_days]
    return ItineraryResult(**normalized)


def _finalize_itinerary(
    state: TravelPlanState,
    itinerary: ItineraryResult,
) -> ItineraryResult:
    requirement = state["requirement"]
    attraction_result = state["attraction_result"]
    booking_result = state["booking_result"]
    hotel = (
        booking_result.recommended_hotels[0]
        if booking_result.recommended_hotels
        else None
    )
    attraction_groups = _cluster_attractions_by_distance(
        attractions=attraction_result.attractions,
        preferred_names=_ordered_recommended_attraction_names(state),
        day_count=requirement.days or len(itinerary.days) or 1,
    )

    days: list[DayPlan] = []
    for index, day in enumerate(itinerary.days):
        transfer_notes = day.transfer_notes
        if not transfer_notes and index < len(attraction_groups):
            transfer_notes = _build_transfer_notes(hotel, attraction_groups[index])
        weather = day.weather or _weather_for_date(
            attraction_result.weather,
            day.date,
        )
        days.append(
            day.model_copy(
                update={
                    "weather": weather,
                    "lunch": [],
                    "dinner": [],
                    "evening": [],
                    "transfer_notes": transfer_notes,
                }
            )
        )

    return itinerary.model_copy(update={"days": days})


def _weather_for_date(weather, day_date: date | None) -> str | None:
    if weather is None or day_date is None or not getattr(weather, "is_available", True):
        return None
    day_text = day_date.isoformat()
    for item in weather.daily:
        if item.get("date") == day_text:
            text_day = item.get("text_day") or "-"
            text_night = item.get("text_night") or "-"
            low = item.get("low") or "-"
            high = item.get("high") or "-"
            return f"{text_day}/{text_night} {low}~{high}°C"
    return None
