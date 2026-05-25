from __future__ import annotations

from agents.booking import estimated_room_count
from llm_client import DeepSeekClient
from state import BudgetResult, Hotel, TransportPlan, TravelPlanState
from timing_utils import timed_step


BUDGET_RESERVE_RATIO = 0.2


def analyze_budget(state: TravelPlanState) -> BudgetResult:
    requirement = state["requirement"]
    attraction_result = state["attraction_result"]
    transportation_result = state["transportation_result"]
    booking_result = state["booking_result"]

    travelers = requirement.travelers
    days = requirement.days or 1
    nights = max(days - 1, 0)

    ticket_cost = _calculate_known_ticket_cost(state)
    unknown_paid_attractions = _find_unknown_paid_attractions(state)
    budget_selection = _select_budget_controlled_options(
        state=state,
        ticket_cost=ticket_cost,
        nights=nights,
        travelers=travelers,
    )

    if budget_selection["transport_plan"] is not None:
        _set_recommended_transport_plan(state, budget_selection["transport_plan"])
    if budget_selection["hotel"] is not None:
        _set_primary_hotel(state, budget_selection["hotel"])

    transport_cost = _transport_cost(budget_selection["transport_plan"], travelers)
    hotel_cost = _hotel_cost(
        budget_selection["hotel"],
        nights=nights,
        travelers=travelers,
    )
    meal_cost = 0.0
    misc_cost = 0.0
    total_cost = round(transport_cost + hotel_cost + ticket_cost, 2)

    remaining_budget = (
        round(requirement.budget - total_cost, 2)
        if requirement.budget is not None
        else None
    )
    usable_budget = (
        round(requirement.budget * (1 - BUDGET_RESERVE_RATIO), 2)
        if requirement.budget is not None
        else None
    )
    reserved_buffer = (
        round(requirement.budget * BUDGET_RESERVE_RATIO, 2)
        if requirement.budget is not None
        else None
    )
    is_over_budget = (
        total_cost > usable_budget if usable_budget is not None else None
    )

    suggestions = _build_budget_suggestions(
        is_over_budget=is_over_budget,
        adjusted=budget_selection["adjusted"],
        still_insufficient=budget_selection["still_insufficient"],
        usable_budget=usable_budget,
        reserved_buffer=reserved_buffer,
        transport_cost=transport_cost,
        hotel_cost=hotel_cost,
        ticket_cost=ticket_cost,
    )
    suggestions = _append_unknown_ticket_warning(
        suggestions=suggestions,
        unknown_paid_attractions=unknown_paid_attractions,
    )
    confidence = _estimate_confidence(state)

    return BudgetResult(
        transport_cost=transport_cost,
        hotel_cost=hotel_cost,
        ticket_cost=ticket_cost,
        meal_cost=meal_cost,
        misc_cost=misc_cost,
        total_cost=total_cost,
        remaining_budget=remaining_budget,
        is_over_budget=is_over_budget,
        cost_breakdown={
            "transport": transport_cost,
            "hotel": hotel_cost,
            "tickets": ticket_cost,
            "meals": meal_cost,
            "misc": misc_cost,
            "reserved_buffer": reserved_buffer or 0,
            "usable_budget": usable_budget or 0,
        },
        suggestions=suggestions,
        confidence=confidence,
    )


def budget_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("budget"):
        budget_result = analyze_budget(state)
        return {
            "transportation_result": state["transportation_result"],
            "booking_result": state["booking_result"],
            "budget_result": budget_result,
            "current_phase": "budget",
        }


def _estimate_meal_cost(state: TravelPlanState) -> float:
    requirement = state["requirement"]
    attraction_result = state["attraction_result"]
    days = requirement.days or 1
    travelers = requirement.travelers
    average_costs = [
        item.average_cost for item in attraction_result.restaurants if item.average_cost
    ]
    per_person_per_day = (
        sum(average_costs) / len(average_costs)
        if average_costs
        else 120
    )
    return round(per_person_per_day * travelers * days, 2)


def _calculate_known_ticket_cost(state: TravelPlanState) -> float:
    travelers = state["requirement"].travelers
    ticket_cost = 0.0
    for item in state["attraction_result"].attractions:
        if item.admission_status == "known_paid" and item.ticket_price is not None:
            ticket_cost += item.ticket_price * travelers
    return round(ticket_cost, 2)


def _select_budget_controlled_options(
    *,
    state: TravelPlanState,
    ticket_cost: float,
    nights: int,
    travelers: int,
) -> dict:
    requirement = state["requirement"]
    transportation_result = state["transportation_result"]
    booking_result = state["booking_result"]

    plans = _available_transport_plans(transportation_result)
    hotels = booking_result.hotels or booking_result.recommended_hotels

    current_plan = transportation_result.recommended_plan or (plans[0] if plans else None)
    current_hotel = booking_result.recommended_hotels[0] if booking_result.recommended_hotels else (
        hotels[0] if hotels else None
    )

    if requirement.budget is None:
        return {
            "transport_plan": current_plan,
            "hotel": current_hotel,
            "adjusted": False,
            "still_insufficient": False,
        }

    usable_budget = requirement.budget * (1 - BUDGET_RESERVE_RATIO)
    current_total = _combined_core_cost(
        current_plan,
        current_hotel,
        ticket_cost=ticket_cost,
        nights=nights,
        travelers=travelers,
    )
    if current_total <= usable_budget:
        return {
            "transport_plan": current_plan,
            "hotel": current_hotel,
            "adjusted": False,
            "still_insufficient": False,
        }

    combinations = [
        (plan, hotel)
        for plan in (plans or [None])
        for hotel in (hotels or [None])
    ]
    indexed_plans = {id(plan): index for index, plan in enumerate(plans)}
    indexed_hotels = {id(hotel): index for index, hotel in enumerate(hotels)}

    feasible = [
        (plan, hotel)
        for plan, hotel in combinations
        if _combined_core_cost(
            plan,
            hotel,
            ticket_cost=ticket_cost,
            nights=nights,
            travelers=travelers,
        )
        <= usable_budget
    ]
    if feasible:
        plan, hotel = min(
            feasible,
            key=lambda item: (
                indexed_plans.get(id(item[0]), 999),
                indexed_hotels.get(id(item[1]), 999),
                _combined_core_cost(
                    item[0],
                    item[1],
                    ticket_cost=ticket_cost,
                    nights=nights,
                    travelers=travelers,
                ),
            ),
        )
        return {
            "transport_plan": plan,
            "hotel": hotel,
            "adjusted": plan is not current_plan or hotel is not current_hotel,
            "still_insufficient": False,
        }

    cheapest_plan, cheapest_hotel = min(
        combinations,
        key=lambda item: _combined_core_cost(
            item[0],
            item[1],
            ticket_cost=ticket_cost,
            nights=nights,
            travelers=travelers,
        ),
    )
    return {
        "transport_plan": cheapest_plan,
        "hotel": cheapest_hotel,
        "adjusted": cheapest_plan is not current_plan or cheapest_hotel is not current_hotel,
        "still_insufficient": True,
    }


def _available_transport_plans(transportation_result) -> list[TransportPlan]:
    plans = []
    if transportation_result.recommended_plan:
        plans.append(transportation_result.recommended_plan)
    plans.extend(transportation_result.alternative_plans)

    unique: list[TransportPlan] = []
    seen: set[tuple] = set()
    for plan in plans:
        key = _transport_plan_key(plan)
        if key in seen:
            continue
        seen.add(key)
        unique.append(plan)
    return unique


def _transport_plan_key(plan: TransportPlan) -> tuple:
    return (
        plan.outbound.mode,
        plan.outbound.raw_reference,
        plan.return_trip.raw_reference if plan.return_trip else None,
        plan.total_price,
    )


def _set_recommended_transport_plan(
    state: TravelPlanState,
    selected_plan: TransportPlan,
) -> None:
    transportation_result = state["transportation_result"]
    plans = _available_transport_plans(transportation_result)
    alternatives = [
        plan
        for plan in plans
        if _transport_plan_key(plan) != _transport_plan_key(selected_plan)
    ]
    transportation_result.recommended_plan = selected_plan
    transportation_result.alternative_plans = alternatives


def _set_primary_hotel(state: TravelPlanState, selected_hotel: Hotel) -> None:
    booking_result = state["booking_result"]
    candidates = booking_result.recommended_hotels + [
        hotel
        for hotel in booking_result.hotels
        if hotel.name not in {item.name for item in booking_result.recommended_hotels}
    ]

    selected: list[Hotel] = [selected_hotel]
    selected_names = {selected_hotel.name}
    used_bands = {_hotel_price_band(selected_hotel)}

    for hotel in candidates:
        if hotel.name in selected_names:
            continue
        band = _hotel_price_band(hotel)
        if band in used_bands:
            continue
        selected.append(hotel)
        selected_names.add(hotel.name)
        used_bands.add(band)
        if len(selected) >= 3:
            break

    for hotel in candidates:
        if len(selected) >= 3:
            break
        if hotel.name in selected_names:
            continue
        selected.append(hotel)
        selected_names.add(hotel.name)

    booking_result.recommended_hotels = selected


def _hotel_price_band(hotel: Hotel) -> str:
    price = hotel.price_per_night
    if price is None:
        return "unknown"
    if price < 200:
        return "budget"
    if price < 400:
        return "mid"
    return "premium"


def _combined_core_cost(
    plan: TransportPlan | None,
    hotel: Hotel | None,
    *,
    ticket_cost: float,
    nights: int,
    travelers: int,
) -> float:
    return round(
        _transport_cost(plan, travelers)
        + _hotel_cost(hotel, nights=nights, travelers=travelers)
        + ticket_cost,
        2,
    )


def _transport_cost(plan: TransportPlan | None, travelers: int) -> float:
    if plan is None or plan.total_price is None:
        return 0.0
    return round(plan.total_price * travelers, 2)


def _hotel_cost(
    hotel: Hotel | None,
    *,
    nights: int,
    travelers: int,
) -> float:
    if hotel is None:
        return 0.0
    price = _hotel_budget_price(hotel)
    return round(price * nights * estimated_room_count(travelers), 2)


def _hotel_budget_price(hotel: Hotel) -> float:
    price = hotel.price_per_night or 0
    if not hotel.price_is_starting:
        return price
    if price <= 0:
        return 0.0
    return price + (5 if price < 100 else 50)


def _find_unknown_paid_attractions(state: TravelPlanState) -> list[str]:
    return [
        item.name
        for item in state["attraction_result"].attractions
        if item.admission_status == "unknown_paid"
    ]


def _append_unknown_ticket_warning(
    *,
    suggestions: list[str],
    unknown_paid_attractions: list[str],
) -> list[str]:
    if not unknown_paid_attractions:
        return suggestions

    names = "、".join(unknown_paid_attractions[:8])
    suffix = "等" if len(unknown_paid_attractions) > 8 else ""
    warning = (
        f"以下景点标记为收费但未返回具体票价，暂未计入门票预算：{names}{suffix}。"
        "建议出行前单独确认门票或预留额外预算。"
    )
    return [*suggestions, warning]


def _build_budget_suggestions(
    *,
    is_over_budget: bool | None,
    adjusted: bool,
    still_insufficient: bool,
    usable_budget: float | None,
    reserved_buffer: float | None,
    transport_cost: float,
    hotel_cost: float,
    ticket_cost: float,
) -> list[str]:
    if is_over_budget is None:
        return ["用户未提供总预算，当前仅给出核心费用估算。"]

    if usable_budget is None or usable_budget <= 0:
        return ["预算信息不足，暂无法判断核心费用是否合理。"]

    core_cost = transport_cost + hotel_cost + ticket_cost
    reserve_text = (
        f"已预留约{reserved_buffer}元供用户自主协调。"
        if reserved_buffer is not None
        else "已预留一部分空间供用户自主协调。"
    )

    if still_insufficient:
        return [
            (
                "预算不足：即使交通和酒店都选择当前可用结果中的最低成本方案，核心费用仍超过预算；"
                "建议提高预算或缩短行程天数。"
            ),
        ]

    if core_cost < usable_budget:
        message = f"预算充足：核心费用低于预算的80%，{reserve_text}"
    elif core_cost <= (usable_budget / (1 - BUDGET_RESERVE_RATIO)):
        message = "核心费用已接近总预算，建议保留一部分空间给餐饮、市内交通和临时消费。"
    else:
        message = "预算不足：核心费用已超过总预算，建议提高预算或降低交通/住宿成本。"

    if adjusted and core_cost <= usable_budget:
        return [
            f"{message}已优先下调交通或酒店选择，以尽量保留预算弹性。"
        ]

    return [message]


def _estimate_confidence(state: TravelPlanState) -> str:
    fallback_flags = [
        state["attraction_result"].is_fallback,
        state["transportation_result"].is_fallback,
        state["booking_result"].is_fallback,
    ]
    if all(not flag for flag in fallback_flags):
        return (
            "medium"
            if _find_unknown_paid_attractions(state)
            else "high"
        )
    if sum(fallback_flags) <= 1:
        return "medium"
    return "low"


def _enhance_budget_suggestions_with_llm(
    *,
    state: TravelPlanState,
    base_suggestions: list[str],
    computed: dict,
) -> list[str]:
    client = DeepSeekClient()
    if not client.configured:
        return base_suggestions

    try:
        payload = client.chat_json(
            system_prompt=_build_budget_system_prompt(),
            user_prompt=_build_budget_user_prompt(state, computed),
            temperature=0.2,
        )
        suggestions = payload.get("suggestions")
        if isinstance(suggestions, list) and all(
            isinstance(item, str) for item in suggestions
        ):
            return suggestions
    except Exception:
        pass
    return base_suggestions


def _build_budget_system_prompt() -> str:
    return """
你是旅行预算分析助手。
请基于程序已经计算出的预算事实，生成预算建议 JSON。

要求：
1. 只返回 JSON，不要返回解释文字。
2. 不要重新计算或篡改给定金额。
3. 建议要围绕“是否超预算、哪一项最值得优化、用户还能如何取舍”展开。
4. 建议不超过 3 条，尽量具体。

JSON 格式：
{
  "suggestions": ["string"]
}
""".strip()


def _build_budget_user_prompt(state: TravelPlanState, computed: dict) -> str:
    requirement = state["requirement"].model_dump(mode="json")
    attraction_result = state["attraction_result"].model_dump(mode="json")
    transportation_result = state["transportation_result"].model_dump(mode="json")
    booking_result = state["booking_result"].model_dump(mode="json")

    return f"""
请基于以下预算事实生成建议：

requirement = {requirement}
attraction_result = {attraction_result}
transportation_result = {transportation_result}
booking_result = {booking_result}
computed_budget = {computed}
""".strip()
