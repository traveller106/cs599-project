import streamlit as st
from graph import build_graph
from state import AgentState
from ui_components import (
    render_recommendation_card,
    render_filter_panel,
    render_preferences_summary,
    render_chat_message,
    render_workflow_process,
)
from tools import load_config
import time

st.set_page_config(page_title="动漫推荐助手", page_icon="🎬", layout="wide")
st.title("🎬 动漫推荐助手 - 多智能体版")
st.caption("基于 LangGraph + DeepSeek + Bangumi 的智能动漫推荐系统")

try:
    config = load_config()
except Exception as e:
    st.error(f"配置加载失败: {e}")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "tavily_call_count" not in st.session_state:
    st.session_state.tavily_call_count = 0

if "filter_params" not in st.session_state:
    st.session_state.filter_params = {}

if "preferences" not in st.session_state:
    st.session_state.preferences = {}

if "execution_path" not in st.session_state:
    st.session_state.execution_path = []


@st.cache_resource
def get_graph():
    return build_graph()


st.session_state.graph = get_graph()

render_preferences_summary(st.session_state.preferences)

filter_params = render_filter_panel()
st.session_state.filter_params = filter_params

if st.sidebar.button("🗑️ 清空对话"):
    st.session_state.messages = []
    st.session_state.tavily_call_count = 0
    st.session_state.preferences = {}
    st.session_state.execution_path = []
    st.session_state.filter_params = {}
    st.rerun()

for msg in st.session_state.messages:
    if msg["role"] == "user":
        render_chat_message("user", msg["content"])
    elif msg["role"] == "assistant":
        render_chat_message("assistant", msg.get("text", ""))
        if msg.get("recommendations"):
            for rec in msg["recommendations"]:
                render_recommendation_card(rec)
        if msg.get("process_log"):
            render_workflow_process(msg["process_log"])

user_input = st.chat_input("描述你想看的动漫类型...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    render_chat_message("user", user_input)

    initial_state = {
        "messages": st.session_state.messages,
        "user_query": user_input,
        "preferences": st.session_state.preferences,
        "filter_params": st.session_state.filter_params,
        "tavily_call_count": st.session_state.tavily_call_count,
        "reflection_count": 0,
        "search_keywords": "",
        "need_tavily": False,
        "tavily_results": "",
        "bangumi_data": [],
        "candidate_recommendations": [],
        "final_recommendations": [],
        "pass_evaluation": False,
        "evaluation_feedback": "",
        "execution_path": [],
    }

    with st.status("正在分析...", expanded=True) as status:
        try:
            result = st.session_state.graph.invoke(initial_state)
            status.update(label="分析完成!", state="complete")
        except Exception as e:
            status.update(label="分析失败", state="error")
            st.error(f"推荐生成失败: {e}")
            st.stop()

    st.session_state.tavily_call_count = result.get("tavily_call_count", st.session_state.tavily_call_count)
    st.session_state.preferences = result.get("preferences", st.session_state.preferences)
    st.session_state.execution_path = result.get("execution_path", [])

    final_recommendations = result.get("final_recommendations", [])

    if final_recommendations:
        n = len(final_recommendations)
        assistant_text = f"为您找到 {n} 部推荐动漫，详细如下："
    else:
        assistant_text = "抱歉，暂未找到符合条件的动漫推荐，请尝试调整筛选条件或重新描述需求。"

    assistant_msg = {
        "role": "assistant",
        "text": assistant_text,
        "recommendations": final_recommendations,
        "process_log": result.get("process_log", []),
    }
    st.session_state.messages.append(assistant_msg)

    st.rerun()