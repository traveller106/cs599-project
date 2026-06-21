from typing import TypedDict, Annotated
import operator


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    user_query: str
    preferences: dict
    filter_params: dict
    search_keywords: str
    browse_tags: list
    need_tavily: bool
    tavily_results: str
    bangumi_data: list
    candidate_recommendations: list
    final_recommendations: list
    reflection_count: int
    tavily_call_count: int
    pass_evaluation: bool
    evaluation_feedback: str
    need_refetch: bool
    execution_path: Annotated[list, operator.add]
    process_log: Annotated[list, operator.add]