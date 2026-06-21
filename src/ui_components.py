import streamlit as st


def render_recommendation_card(rec: dict):
    with st.container(border=True):
        if rec.get("image_url"):
            st.image(rec["image_url"], width=200)

        if rec.get("title"):
            st.markdown(f'<h4 style="margin-bottom: 0;">{rec["title"]}</h4>', unsafe_allow_html=True)

        if rec.get("title_original"):
            st.caption(rec["title_original"])

        if rec.get("score") is not None:
            st.markdown(f"⭐ {rec['score']}/10")

        if rec.get("tags"):
            badge_html = " ".join(
                f'<span style="background-color:{_tag_color(tag)};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.8em;margin-right:4px;">{tag}</span>'
                for tag in rec["tags"]
            )
            st.markdown(badge_html, unsafe_allow_html=True)

        if rec.get("reason"):
            st.markdown(f"📝 {rec['reason']}")

        if rec.get("match_points"):
            match_html = "\n".join(f"- {point}" for point in rec["match_points"])
            st.markdown(f"**匹配点:**\n{match_html}")

        if rec.get("bangumi_id"):
            st.markdown(f"[🔗 Bangumi 条目](https://bgm.tv/subject/{rec['bangumi_id']})")


_TAG_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#e67e22", "#9b59b6",
    "#1abc9c", "#f39c12", "#e91e63", "#00bcd4", "#8bc34a",
    "#ff5722", "#3f51b5", "#009688", "#cddc39", "#795548",
]


def _tag_color(tag: str) -> str:
    return _TAG_COLORS[hash(tag) % len(_TAG_COLORS)]


def render_filter_panel() -> dict:
    st.sidebar.markdown("## 🔧 筛选条件")

    if "filter_reset" not in st.session_state:
        st.session_state.filter_reset = False

    type_default = [] if st.session_state.filter_reset else st.session_state.get("filter_params", {}).get("type") or []
    year_default = (2000, 2026) if st.session_state.filter_reset else st.session_state.get("filter_params", {}).get("year_range", (2000, 2026))
    score_default = 0.0 if st.session_state.filter_reset else st.session_state.get("filter_params", {}).get("min_score") or 0.0
    tags_default = [] if st.session_state.filter_reset else st.session_state.get("filter_params", {}).get("tags") or []

    selected_types = st.sidebar.multiselect(
        "动漫类型",
        ["TV", "剧场版", "OVA", "WEB", "其他"],
        default=type_default,
        key="filter_type",
    )

    year_range = st.sidebar.slider("播出年代", 1960, 2026, year_default, key="filter_year")

    min_score = st.sidebar.slider("最低评分", 0.0, 10.0, score_default, 0.1, key="filter_score")

    available_tags = [
        "治愈", "热血", "悬疑", "异世界", "恋爱", "科幻",
        "搞笑", "奇幻", "战斗", "校园", "日常", "美食",
        "音乐", "运动", "推理", "致郁", "百合", "耽美",
    ]
    selected_tags = st.sidebar.multiselect("标签/风格", available_tags, default=tags_default, key="filter_tags")

    if st.sidebar.button("🔄 重置过滤器"):
        st.session_state.filter_reset = True
        st.session_state.filter_params = {"type": None, "year_range": None, "min_score": None, "tags": None}
        st.rerun()

    st.session_state.filter_reset = False

    return {
        "type": selected_types or None,
        "year_range": year_range,
        "min_score": min_score if min_score > 0 else None,
        "tags": selected_tags or None,
    }


def render_tavily_progress(tavily_count: int):
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Tavily 搜索用量")
    st.sidebar.progress(min(tavily_count / 2, 1.0))
    st.sidebar.caption(f"已使用 {tavily_count}/2 次")
    if tavily_count >= 2:
        st.sidebar.warning("⚠️ 本次对话 Tavily 搜索次数已用完")


def render_preferences_summary(preferences: dict):
    if not preferences or not isinstance(preferences, dict):
        return

    parts = []
    if preferences.get("fav_genres"):
        parts.append(", ".join(preferences["fav_genres"]))
    if preferences.get("avoid_genres"):
        parts.append(f"排除: {', '.join(preferences['avoid_genres'])}")
    if preferences.get("mood"):
        parts.append(preferences["mood"])
    if preferences.get("style"):
        parts.append(preferences["style"])
    if preferences.get("era"):
        parts.append(preferences["era"])

    if parts:
        st.sidebar.markdown("---")
        summary = " | ".join(parts)
        st.sidebar.markdown(f"🎯 偏好: {summary}")


def render_execution_path(path: list):
    if not path:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔀 执行路径")

    mermaid_lines = ["graph LR"]
    for i in range(len(path) - 1):
        mermaid_lines.append(f"  {path[i]}[{path[i]}] --> {path[i+1]}[{path[i+1]}]")

    mermaid_code = "\n".join(mermaid_lines)
    st.sidebar.markdown(f"```mermaid\n{mermaid_code}\n```")


def render_chat_message(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def render_workflow_process(process_log: list):
    if not process_log:
        return

    with st.expander("🔍 查看推荐分析过程", expanded=False):
        st.markdown("### 🧠 智能体工作流程")

        steps = {
            "📋": "标签解析与意图理解",
            "🏷️": "偏好提取",
            "🌐": "网络评价搜索",
            "📰": "搜索结果处理",
            "🔍": "Bangumi数据库搜索",
            "🚫": "低质量过滤",
            "🔧": "硬性条件筛选",
            "📊": "候选池确定",
            "🔄": "搜索策略优化",
            "💡": "优化依据",
            "🧹": "数据清洗",
            "🤖": "AI推荐生成",
            "⭐": "质量偏好",
            "📝": "推荐输出",
            "🔎": "质量审查",
            "📦": "最终输出",
        }

        for log_line in process_log:
            parts = None
            for sep in ["：", ":"]:
                if sep in log_line:
                    idx = log_line.index(sep)
                    parts = (log_line[:idx], log_line[idx + len(sep):])
                    break
            if parts and len(parts) == 2:
                header = parts[0].strip()
                content_text = parts[1].strip()
            else:
                header = log_line.strip()
                content_text = ""

            icon = ""
            step_title = "处理步骤"
            for step_icon, step_name in steps.items():
                if header.startswith(step_icon):
                    icon = step_icon
                    step_title = step_name
                    break

            if not icon and len(header) >= 2:
                icon = header[:2]
                if icon in steps:
                    step_title = steps[icon]
                else:
                    icon = header[0] if header else ""

            st.markdown(f"**{icon} {step_title}**：{content_text}")

        st.markdown("---")
        st.caption("💡 以上展示了推荐系统从标签解析到最终输出的完整决策链。系统通过多智能体协作（意图分析→数据搜索→质量审查→结果优化）确保推荐质量。")