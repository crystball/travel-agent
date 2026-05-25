from __future__ import annotations

from state import (
    AgentError,
    TransportOption,
    TransportPlan,
    TransportationResult,
    TravelPlanState,
)
from timing_utils import timed_step
from transport_clients import TransportClients


FLIGHT_BUDGET_SHARE_THRESHOLD = 0.4


def build_transportation_result(state: TravelPlanState) -> TransportationResult:
    requirement = state["requirement"]
    routing_info = state["routing_info"]
    clients = TransportClients()

    outbound_options: list[TransportOption] = []
    return_options: list[TransportOption] = []
    source_summary: list[str] = []
    limitations: list[str] = []

    if routing_info.train_query_available and requirement.start_date:
        outbound_options.extend(
            clients.query_12306_trains(
                requirement.origin_city or "",
                requirement.destination_city or "",
                requirement.start_date,
            )
        )
        if requirement.end_date:
            return_options.extend(
                clients.query_12306_trains(
                    requirement.destination_city or "",
                    requirement.origin_city or "",
                    requirement.end_date,
                )
            )
        source_summary.append("12306")
    else:
        limitations.append("12306 \u5f53\u524d\u4e0d\u53ef\u67e5\u8be2\uff0c\u672a\u63d0\u4f9b\u5b9e\u65f6\u9ad8\u94c1/\u52a8\u8f66\u65b9\u6848\u3002")

    if routing_info.flight_query_available and requirement.start_date:
        outbound_options.extend(
            clients.query_flyai_flights(
                requirement.origin_city or "",
                requirement.destination_city or "",
                requirement.start_date,
            )
        )
        if requirement.end_date:
            return_options.extend(
                clients.query_flyai_flights(
                    requirement.destination_city or "",
                    requirement.origin_city or "",
                    requirement.end_date,
                )
            )
        source_summary.append("FlyAI")
    else:
        limitations.append("\u5f53\u524d\u672a\u83b7\u53d6\u5230\u53ef\u7528\u673a\u7968\u5b9e\u65f6\u67e5\u8be2\u7ed3\u679c\u3002")

    train_plan = _build_mode_plan("train", outbound_options, return_options)
    flight_plan = _build_mode_plan("flight", outbound_options, return_options)
    available_plans = [plan for plan in (train_plan, flight_plan) if plan is not None]
    recommended_plan = _pick_recommended_plan(
        plans=available_plans,
        budget=requirement.budget,
        travelers=requirement.travelers,
    )
    alternative_plans = [
        plan for plan in available_plans if plan is not recommended_plan
    ]
    is_fallback = recommended_plan is None

    if is_fallback:
        limitations.append("\u4ea4\u901a\u6570\u636e\u6682\u4e0d\u53ef\u7528\uff0c\u5efa\u8bae\u540e\u7eed\u91cd\u65b0\u67e5\u8be2\u3002")

    selection_reason = (
        recommended_plan.reason
        if recommended_plan
        else "\u5f53\u524d\u6ca1\u6709\u8db3\u591f\u7684\u4ea4\u901a\u6570\u636e\u53ef\u4f9b\u63a8\u8350\u3002"
    )

    return TransportationResult(
        outbound_options=outbound_options,
        return_options=return_options,
        recommended_plan=recommended_plan,
        alternative_plans=alternative_plans,
        selection_reason=selection_reason,
        source_summary=source_summary,
        limitations=limitations,
        is_fallback=is_fallback,
    )


def transportation_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("transportation"):
        try:
            return {"transportation_result": build_transportation_result(state)}
        except Exception as exc:
            return {
                "transportation_result": TransportationResult(
                    limitations=["\u4ea4\u901a\u6a21\u5757\u6267\u884c\u5931\u8d25\uff0c\u672a\u80fd\u751f\u6210\u5b9e\u65f6\u4ea4\u901a\u65b9\u6848\u3002"],
                    is_fallback=True,
                ),
                "errors": [
                    AgentError(
                        agent_name="transportation",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        recoverable=True,
                        fallback_used=True,
                    )
                ],
            }


def _build_mode_plan(
    mode: str,
    outbound_options: list[TransportOption],
    return_options: list[TransportOption],
) -> TransportPlan | None:
    outbound_candidates = [item for item in outbound_options if item.mode == mode]
    if not outbound_candidates:
        return None

    outbound = _pick_best_option(outbound_candidates)
    return_candidates = [item for item in return_options if item.mode == mode]
    return_trip = _pick_best_option(return_candidates) if return_candidates else None

    prices = [item.price for item in (outbound, return_trip) if item and item.price]
    durations = [
        item.duration_minutes
        for item in (outbound, return_trip)
        if item and item.duration_minutes
    ]
    total_duration = sum(durations) if durations else None

    return TransportPlan(
        outbound=outbound,
        return_trip=return_trip,
        total_price=round(sum(prices), 2) if prices else None,
        total_duration_minutes=total_duration,
        reason=_build_mode_reason(mode=mode, total_price=sum(prices) if prices else None),
        reminders=_build_plan_reminders(mode, outbound, return_trip),
    )


def _pick_best_option(options: list[TransportOption]) -> TransportOption:
    return min(
        options,
        key=lambda item: (
            item.price if item.price is not None else float("inf"),
            item.duration_minutes if item.duration_minutes is not None else float("inf"),
        ),
    )


def _pick_recommended_plan(
    *,
    plans: list[TransportPlan],
    budget: float | None,
    travelers: int,
) -> TransportPlan | None:
    if not plans:
        return None
    if len(plans) == 1:
        plan = plans[0]
        plan.reason = f"\u5f53\u524d\u4ec5\u83b7\u53d6\u5230{_mode_label(plan.outbound.mode)}\u65b9\u6848\uff0c\u4f18\u5148\u5c55\u793a\u8be5\u65b9\u6848\u3002"
        return plan

    train_plan = _find_plan(plans, "train")
    flight_plan = _find_plan(plans, "flight")
    if train_plan is None or flight_plan is None:
        return _cheapest_plan(plans)

    if _budget_allows_flight(flight_plan, budget, travelers):
        flight_plan.reason = (
            "\u540c\u65f6\u83b7\u53d6\u5230\u9ad8\u94c1/\u52a8\u8f66\u548c\u98de\u673a\u65b9\u6848\uff1b\u5f53\u524d\u9884\u7b97\u53ef\u8986\u76d6\u98de\u673a\u4ea4\u901a\u6210\u672c\uff0c"
            "\u63a8\u8350\u98de\u673a\u4f5c\u4e3a\u66f4\u504f\u65f6\u95f4\u6548\u7387\u7684\u9009\u62e9\uff0c\u540c\u65f6\u4fdd\u7559\u9ad8\u94c1/\u52a8\u8f66\u4f5c\u4e3a\u4f4e\u4ef7\u5907\u9009\u3002"
        )
        return flight_plan

    train_plan.reason = (
        "\u540c\u65f6\u83b7\u53d6\u5230\u9ad8\u94c1/\u52a8\u8f66\u548c\u98de\u673a\u65b9\u6848\uff1b\u5f53\u524d\u9884\u7b97\u4e0b\u9ad8\u94c1/\u52a8\u8f66\u6210\u672c\u66f4\u4f4e\uff0c"
        "\u63a8\u8350\u9ad8\u94c1/\u52a8\u8f66\u4f5c\u4e3a\u66f4\u7a33\u59a5\u7684\u6027\u4ef7\u6bd4\u9009\u62e9\uff0c\u540c\u65f6\u4fdd\u7559\u98de\u673a\u4f5c\u4e3a\u65f6\u95f4\u6548\u7387\u5907\u9009\u3002"
    )
    return train_plan


def _budget_allows_flight(
    flight_plan: TransportPlan,
    budget: float | None,
    travelers: int,
) -> bool:
    if budget is None or flight_plan.total_price is None:
        return False
    flight_group_cost = flight_plan.total_price * max(travelers, 1)
    return flight_group_cost <= budget * FLIGHT_BUDGET_SHARE_THRESHOLD


def _find_plan(plans: list[TransportPlan], mode: str) -> TransportPlan | None:
    return next((plan for plan in plans if plan.outbound.mode == mode), None)


def _cheapest_plan(plans: list[TransportPlan]) -> TransportPlan:
    plan = min(
        plans,
        key=lambda item: item.total_price if item.total_price is not None else float("inf"),
    )
    plan.reason = "\u5f53\u524d\u6309\u53ef\u7528\u65b9\u6848\u4e2d\u7684\u6700\u4f4e\u4ef7\u683c\u63a8\u8350\u3002"
    return plan


def _build_plan_reminders(
    mode: str,
    outbound: TransportOption,
    return_trip: TransportOption | None,
) -> list[str]:
    reminders: list[str] = []
    if mode == "flight":
        reminders.append("\u98de\u673a\u65b9\u6848\u672a\u5c06\u63d0\u524d\u5230\u673a\u573a\u3001\u5b89\u68c0\u548c\u884c\u674e\u65f6\u95f4\u8ba1\u5165\u884c\u7a0b\u8017\u65f6\uff0c\u8bf7\u989d\u5916\u9884\u7559\u65f6\u95f4\u3002")
    elif mode == "train":
        reminders.append("\u9ad8\u94c1/\u52a8\u8f66\u65b9\u6848\u672a\u5c06\u63d0\u524d\u5230\u7ad9\u3001\u5b89\u68c0\u548c\u5019\u8f66\u65f6\u95f4\u8ba1\u5165\u884c\u7a0b\u8017\u65f6\uff0c\u8bf7\u989d\u5916\u9884\u7559\u65f6\u95f4\u3002")

    for label, option in (("\u53bb\u7a0b", outbound), ("\u8fd4\u7a0b", return_trip)):
        if option and option.transfer_cities:
            cities = "\u3001".join(option.transfer_cities)
            transfer_note = f"{label}\u9700\u5728{cities}\u4e2d\u8f6c"
            if option.transfer_duration_minutes is not None:
                transfer_note += f"\uff0c\u4e2d\u8f6c\u7b49\u5f85\u7ea6{option.transfer_duration_minutes}\u5206\u949f"
            transfer_note += "\uff0c\u8bf7\u9884\u7559\u6362\u4e58\u65f6\u95f4\u3002"
            reminders.append(transfer_note)
    return reminders


def _build_mode_reason(*, mode: str, total_price: float | None) -> str:
    price_text = f"\uff0c\u7968\u4ef7\u7ea6 {round(total_price, 2)} \u5143/\u4eba" if total_price is not None else ""
    if mode == "flight":
        return f"\u98de\u673a\u65b9\u6848\u901a\u5e38\u66f4\u504f\u65f6\u95f4\u6548\u7387{price_text}\u3002"
    if mode == "train":
        return f"\u9ad8\u94c1/\u52a8\u8f66\u65b9\u6848\u901a\u5e38\u66f4\u504f\u6027\u4ef7\u6bd4{price_text}\u3002"
    return f"\u4ea4\u901a\u65b9\u6848{price_text}\u3002"


def _mode_label(mode: str) -> str:
    return {"train": "\u9ad8\u94c1/\u52a8\u8f66", "flight": "\u98de\u673a"}.get(mode, mode)
