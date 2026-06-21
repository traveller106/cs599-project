from state import AgentState
from agents import (
    understand_intent,
    search_tavily_node,
    fetch_bangumi,
    merge_data,
    generate_recommendations,
    evaluate_recommendations,
    refine_search,
    format_response,
)
from langgraph.graph import StateGraph, START, END


def decide_search(state: AgentState) -> str:
    need_tavily = state.get("need_tavily", False)
    tavily_call_count = state.get("tavily_call_count", 0)

    if need_tavily and tavily_call_count < 20:
        return "parallel"
    return "direct"


def decide_reflection(state: AgentState) -> str:
    pass_evaluation = state.get("pass_evaluation", True)
    reflection_count = state.get("reflection_count", 0)

    if not pass_evaluation and reflection_count < 2:
        return "refine"
    return "format"


def decide_refetch(state: AgentState) -> str:
    need_refetch = state.get("need_refetch", False)
    if need_refetch:
        return "refetch"
    return "recommend"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("understand_intent", understand_intent)
    builder.add_node("search_tavily", search_tavily_node)
    builder.add_node("fetch_bangumi", fetch_bangumi)
    builder.add_node("merge_data", merge_data)
    builder.add_node("generate_recommendations", generate_recommendations)
    builder.add_node("evaluate_recommendations", evaluate_recommendations)
    builder.add_node("refine_search", refine_search)
    builder.add_node("format_response", format_response)

    builder.add_edge(START, "understand_intent")

    builder.add_conditional_edges(
        "understand_intent",
        decide_search,
        {
            "parallel": "search_tavily",
            "direct": "fetch_bangumi",
        },
    )

    builder.add_edge("search_tavily", "fetch_bangumi")

    builder.add_edge("fetch_bangumi", "merge_data")

    builder.add_edge("merge_data", "generate_recommendations")
    builder.add_edge("generate_recommendations", "evaluate_recommendations")

    builder.add_conditional_edges(
        "evaluate_recommendations",
        decide_reflection,
        {
            "refine": "refine_search",
            "format": "format_response",
        },
    )

    builder.add_conditional_edges(
        "refine_search",
        decide_refetch,
        {
            "refetch": "fetch_bangumi",
            "recommend": "generate_recommendations",
        },
    )

    builder.add_edge("format_response", END)

    return builder.compile()