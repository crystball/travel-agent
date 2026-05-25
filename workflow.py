from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.attraction import attraction_node
from agents.booking import booking_node
from agents.budget import budget_node
from agents.itinerary import itinerary_node
from agents.needs_analysis import needs_analysis_node
from agents.transportation import transportation_node
from date_utils import build_routing_info
from state import TravelPlanState
from timing_utils import timed_step


def build_routing_info_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("build_routing_info"):
        return {
            "routing_info": build_routing_info(state["requirement"]),
            "current_phase": "parallel_planning",
        }


def join_results_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("join_results"):
        warnings = []
        if "attraction_result" not in state:
            warnings.append("景点结果缺失。")
        if "transportation_result" not in state:
            warnings.append("交通结果缺失。")
        if "booking_result" not in state:
            warnings.append("酒店结果缺失。")
        return {"warnings": warnings, "current_phase": "join_results"}


def clarification_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("clarification"):
        missing_fields = "、".join(state["requirement"].missing_fields)
        return {
            "warnings": [f"需求信息不足，缺少：{missing_fields}"],
            "current_phase": "clarification",
            "status": "partial",
        }


def partial_failure_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("partial_failure"):
        return {
            "warnings": ["可用结果不足，无法生成完整预算与行程。"],
            "current_phase": "partial_failure",
            "status": "failed",
        }


def route_after_needs(state: TravelPlanState) -> str:
    return (
        "clarification"
        if state["requirement"].clarification_needed
        else "build_routing_info"
    )


def route_after_join(state: TravelPlanState) -> str:
    enough_results = (
        "attraction_result" in state
        and (
            "transportation_result" in state
            or "booking_result" in state
        )
    )
    return "budget" if enough_results else "partial_failure"


def create_workflow():
    graph = StateGraph(TravelPlanState)

    graph.add_node("needs_analysis", needs_analysis_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("build_routing_info", build_routing_info_node)
    graph.add_node("attraction", attraction_node)
    graph.add_node("transportation", transportation_node)
    graph.add_node("booking", booking_node)
    graph.add_node("join_results", join_results_node)
    graph.add_node("budget", budget_node)
    graph.add_node("itinerary", itinerary_node)
    graph.add_node("partial_failure", partial_failure_node)

    graph.add_edge(START, "needs_analysis")
    graph.add_conditional_edges(
        "needs_analysis",
        route_after_needs,
        {
            "clarification": "clarification",
            "build_routing_info": "build_routing_info",
        },
    )
    graph.add_edge("clarification", END)

    graph.add_edge("build_routing_info", "attraction")
    graph.add_edge("build_routing_info", "transportation")
    graph.add_edge("attraction", "booking")

    graph.add_edge(["transportation", "booking"], "join_results")

    graph.add_conditional_edges(
        "join_results",
        route_after_join,
        {
            "budget": "budget",
            "partial_failure": "partial_failure",
        },
    )
    graph.add_edge("partial_failure", END)
    graph.add_edge("budget", "itinerary")
    graph.add_edge("itinerary", END)

    return graph.compile()


def run_workflow(raw_user_input: str) -> TravelPlanState:
    workflow = create_workflow()
    initial_state: TravelPlanState = {
        "raw_user_input": raw_user_input,
        "errors": [],
        "warnings": [],
        "status": "pending",
        "current_phase": None,
    }
    return workflow.invoke(initial_state)
