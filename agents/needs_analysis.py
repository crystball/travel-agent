from __future__ import annotations

import re
from datetime import date

from date_utils import (
    infer_days,
    infer_end_date,
    parse_date_range,
    parse_days,
    remove_date_expressions,
)
from llm_client import DeepSeekClient
from state import TravelPlanState, TravelRequirement
from timing_utils import timed_step


REQUIRED_FIELDS = ("origin_city", "destination_city", "start_date", "days")


def analyze_needs(raw_user_input: str, today: date | None = None) -> TravelRequirement:
    today = today or date.today()
    llm_requirement = _try_llm_analysis(raw_user_input, today=today)
    if llm_requirement is not None and _requirement_looks_valid(llm_requirement):
        return llm_requirement
    return _analyze_with_rules(raw_user_input, today=today)


def _analyze_with_rules(
    raw_user_input: str, today: date | None = None
) -> TravelRequirement:
    today = today or date.today()
    start_date, explicit_end_date = parse_date_range(raw_user_input, today=today)
    days = parse_days(raw_user_input) or infer_days(start_date, explicit_end_date)
    end_date = explicit_end_date or infer_end_date(start_date, days)
    text_without_dates = remove_date_expressions(raw_user_input)

    requirement = TravelRequirement(
        origin_city=_extract_origin(text_without_dates),
        destination_city=_extract_destination(text_without_dates),
        start_date=start_date,
        end_date=end_date,
        days=days,
        travelers=_extract_travelers(raw_user_input),
        budget=_extract_budget(raw_user_input),
        preferences=_extract_preferences(raw_user_input),
        transport_preference=_extract_transport_preference(raw_user_input),
        hotel_preference=_extract_hotel_preference(raw_user_input),
        special_constraints=_extract_constraints(raw_user_input),
    )

    missing_fields = [
        field_name
        for field_name in REQUIRED_FIELDS
        if getattr(requirement, field_name) in (None, "", [])
    ]
    requirement.missing_fields = missing_fields
    requirement.clarification_needed = bool(missing_fields)
    requirement.normalized_query = _build_normalized_query(requirement)
    return requirement


def needs_analysis_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("needs_analysis"):
        requirement = analyze_needs(state["raw_user_input"])
        return {
            "requirement": requirement,
            "current_phase": "needs_analysis",
            "status": "running",
        }


def _extract_origin(text: str) -> str | None:
    match = re.search(r"从(.+?)(?:出发|去|到|前往)", text)
    if match:
        return _clean_city_text(match.group(1))
    match = re.search(r"(.+?)(?:出发)", text)
    return _clean_city_text(match.group(1)) if match else None


def _extract_destination(text: str) -> str | None:
    match = re.search(r"(?:去|到|前往)(.+?)(?:玩|旅游|旅行|[0-9一二两三四五六七八九十]+天|，|,|。|$)", text)
    return _clean_city_text(match.group(1)) if match else None


def _extract_travelers(text: str) -> int:
    match = re.search(r"(\d+)\s*(?:个)?人", text)
    if match:
        return int(match.group(1))
    if any(token in text for token in ("两个人", "两人", "2人")):
        return 2
    return 1


def _extract_budget(text: str) -> float | None:
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _extract_preferences(text: str) -> list[str]:
    match = re.search(r"喜欢(.+?)(?:。|$)", text)
    if not match:
        return []
    raw = match.group(1)
    return [
        item.strip()
        for item in re.split(r"[、，,和及]", raw)
        if item.strip()
    ]


def _extract_transport_preference(text: str) -> str | None:
    for preference in ("高铁优先", "飞机优先", "性价比优先"):
        if preference in text:
            return preference
    return None


def _extract_hotel_preference(text: str) -> str | None:
    for preference in ("经济型", "舒适型", "豪华型"):
        if preference in text:
            return preference
    return None


def _clean_city_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip(" ，,。；;")
    cleaned = re.sub(r"(出发|去|到|前往)$", "", cleaned).strip(" ，,。；;")
    return cleaned or None


def _requirement_looks_valid(requirement: TravelRequirement) -> bool:
    for city in (requirement.origin_city, requirement.destination_city):
        if not _city_field_looks_valid(city):
            return False
    if requirement.start_date and requirement.end_date and requirement.days is None:
        return False
    return True


def _city_field_looks_valid(value: str | None) -> bool:
    if not value:
        return True
    if re.search(r"20\d{2}|\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}", value):
        return False
    if any(token in value for token in ("出发", "前往")):
        return False
    if len(value) > 12 and any(token in value for token in ("去", "到")):
        return False
    return True


def _extract_constraints(text: str) -> list[str]:
    candidates = ("不想太赶", "带老人", "带孩子", "亲子", "无障碍")
    return [item for item in candidates if item in text]


def _build_normalized_query(requirement: TravelRequirement) -> str | None:
    if requirement.clarification_needed:
        return None
    preference_text = "、".join(requirement.preferences) or "无特殊偏好"
    return (
        f"{requirement.travelers}人从{requirement.origin_city}出发，"
        f"{requirement.start_date}至{requirement.end_date}前往"
        f"{requirement.destination_city}旅行，"
        f"预算{requirement.budget if requirement.budget is not None else '未指定'}元，"
        f"偏好{preference_text}。"
    )


def _try_llm_analysis(
    raw_user_input: str, today: date | None = None
) -> TravelRequirement | None:
    client = DeepSeekClient()
    if not client.configured:
        return None

    today = today or date.today()
    try:
        payload = client.chat_json(
            system_prompt=_build_system_prompt(today),
            user_prompt=_build_user_prompt(raw_user_input),
        )
        requirement = _requirement_from_llm_payload(payload, today=today)
        return requirement
    except Exception:
        return None


def _build_system_prompt(today: date) -> str:
    return f"""
你是旅行需求解析助手。
当前日期是 {today.isoformat()}。
你的任务是把用户的自然语言旅行需求转换成 JSON。

要求：
1. 只返回 JSON，不要返回解释文字。
2. 如果用户只写了“6月15日”而没有年份，需要结合当前日期推断最近的未来日期。
3. 如果用户只给出出发日期和天数，请自动计算结束日期。
4. 如果缺少关键字段，请把字段名写入 missing_fields，并将 clarification_needed 设为 true。
5. 关键字段包括：origin_city、destination_city、start_date、days。
6. 所有日期必须输出为 YYYY-MM-DD。

JSON 格式：
{{
  "origin_city": "string or null",
  "destination_city": "string or null",
  "start_date": "YYYY-MM-DD or null",
  "end_date": "YYYY-MM-DD or null",
  "days": "integer or null",
  "travelers": "integer",
  "budget": "number or null",
  "preferences": ["string"],
  "transport_preference": "string or null",
  "hotel_preference": "string or null",
  "special_constraints": ["string"],
  "missing_fields": ["string"],
  "clarification_needed": "boolean",
  "normalized_query": "string or null"
}}
""".strip()


def _build_user_prompt(raw_user_input: str) -> str:
    return f"请把下面的旅行需求解析成 JSON：\n{raw_user_input}"


def _requirement_from_llm_payload(
    payload: dict, today: date | None = None
) -> TravelRequirement:
    today = today or date.today()
    normalized = dict(payload)

    start_date_raw = normalized.get("start_date")
    end_date_raw = normalized.get("end_date")
    normalized["start_date"] = (
        date.fromisoformat(start_date_raw) if start_date_raw else None
    )
    normalized["end_date"] = (
        date.fromisoformat(end_date_raw) if end_date_raw else None
    )

    if normalized.get("days") is None and normalized["start_date"] and normalized["end_date"]:
        normalized["days"] = (
            normalized["end_date"] - normalized["start_date"]
        ).days + 1

    if normalized["start_date"] and normalized.get("days"):
        normalized["end_date"] = infer_end_date(
            normalized["start_date"], normalized["days"]
        )

    requirement = TravelRequirement(**normalized)
    missing_fields = [
        field_name
        for field_name in REQUIRED_FIELDS
        if getattr(requirement, field_name) in (None, "", [])
    ]
    requirement.missing_fields = missing_fields
    requirement.clarification_needed = bool(missing_fields)
    if not requirement.normalized_query:
        requirement.normalized_query = _build_normalized_query(requirement)
    return requirement
