from pathlib import Path
from state import AgentState
from tools import search_bangumi, search_bangumi_multi, filter_bangumi_data, tavily_multi_search, summarize_tavily_results, browse_bangumi_by_tags
from langchain_openai import ChatOpenAI
import json
import os
import re
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def get_llm():
    load_dotenv(_ENV_PATH)
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0.7,
    )


def _parse_score_hint(query):
    query_lower = query.lower()
    if any(w in query_lower for w in ["超高分", "神作", "评分9", "9分", "9.0"]):
        return 8.0
    if any(w in query_lower for w in ["评分8", "8分", "8.0"]):
        return 8.0
    if any(w in query_lower for w in ["高分", "评分高", "高评分"]):
        return 7.0
    if any(w in query_lower for w in ["评分7", "7分", "7.0"]):
        return 7.0
    return None


def _strip_score_words(keywords):
    for w in ["高分", "低分", "评分高", "高评分", "超高分", "神作"]:
        keywords = keywords.replace(w, "")
    return " ".join(keywords.split())


def understand_intent(state: AgentState) -> dict:
    user_query = state.get("user_query", "")
    filter_params = state.get("filter_params", {})
    tavily_call_count = state.get("tavily_call_count", 0)

    score_hint = _parse_score_hint(user_query)

    llm = get_llm()

    prompt = f"""你是一个动漫推荐系统的意图分析器。请分析以下用户查询，输出JSON格式的结果。

用户查询: {user_query}

当前筛选参数: {json.dumps(filter_params, ensure_ascii=False)}

当前已使用Tavily搜索次数: {tavily_call_count}（上限20次）

请执行以下分析:
1. 提取用于Bangumi关键词搜索的搜索词。关键词必须是简洁的类型/风格/主题词，例如"异世界 搞笑"、"治愈"、"热血 战斗"。注意：不要把"高分""低分""神作"等评分修饰词作为搜索关键词（这些词会在Bangumi中按作品名搜索导致结果偏差）。最多4个词，用空格分隔。
2. 提取用于Bangumi标签浏览的核心类型标签。这些标签必须是Bangumi上常见的动画分类标签，每个标签只含一个词，例如["恋爱"]、["异世界","搞笑"]、["热血","战斗"]。标签数量不超过2个，且只取最核心的类型标签。不要包含"日本""推荐""番剧"等非类型词。
3. 判断是否需要使用Tavily网络搜索：如果用户查询中包含"最新"、"最近"、"刚完结"、"网络口碑"、"今年"、"评价"、"推荐排行"、"热门"等时效性或网络热度相关词语，且tavily_call_count < 20，则将need_tavily设为true，否则设为false。如果tavily_call_count >= 20，强制设为false。
4. 从用户查询中提取偏好信息，包括: fav_genres(偏好的类型列表)、avoid_genres(想避开的类型列表)、mood(情绪倾向)、style(风格偏好)、era(年代偏好)等。

请严格输出以下JSON格式，不要包含任何其他内容:
{{
    "search_keywords": "简短的类型关键词，用空格分隔",
    "browse_tags": ["核心类型标签1"],
    "need_tavily": true或false,
    "preferences": {{
        "fav_genres": [],
        "avoid_genres": [],
        "mood": "",
        "style": "",
        "era": ""
    }}
}}"""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        result = json.loads(content)
        search_keywords = result.get("search_keywords", user_query)
        browse_tags = result.get("browse_tags", [])
        need_tavily = result.get("need_tavily", False)
        preferences = result.get("preferences", {})

        if tavily_call_count >= 20:
            need_tavily = False

        if not isinstance(preferences, dict):
            preferences = {}

        if not isinstance(browse_tags, list):
            browse_tags = []
        browse_tags = [t.strip() for t in browse_tags if isinstance(t, str) and t.strip()][:2]

        existing_preferences = state.get("preferences", {})
        if isinstance(existing_preferences, dict):
            merged_preferences = {**existing_preferences, **preferences}
        else:
            merged_preferences = preferences

        search_keywords = _strip_score_words(search_keywords)

        updated_filter_params = dict(filter_params)
        score_log = ""
        if score_hint is not None:
            existing_min = updated_filter_params.get("min_score")
            if existing_min is None or score_hint > existing_min:
                updated_filter_params["min_score"] = score_hint
                score_log = f" | 🎯 评分约束: ≥{score_hint}（从查询中解析）"

        query_lower = user_query.lower()
        wants_tv = any(w in query_lower for w in ["番剧", "番", "tv", "TV", "电视", "动画番", "新番", "季番"])
        wants_movie = any(w in query_lower for w in ["剧场版", "电影", "movie", "映画"])
        if wants_tv and not wants_movie and not updated_filter_params.get("type"):
            updated_filter_params["type"] = ["tv"]
        elif wants_movie and not updated_filter_params.get("type"):
            updated_filter_params["type"] = ["剧场版"]

        return {
            "search_keywords": search_keywords,
            "browse_tags": browse_tags,
            "need_tavily": need_tavily,
            "preferences": merged_preferences,
            "filter_params": updated_filter_params,
            "execution_path": ["understand_intent"],
            "process_log": [
                f"📋 意图分析: 从查询'{user_query}'中提取关键词'{search_keywords}'，标签{browse_tags}{score_log}",
                f"🏷️ 识别标签: {json.dumps(preferences.get('fav_genres', []), ensure_ascii=False)}",
                f"🌐 Tavily需求: {'是' if need_tavily else '否'}（已用{tavily_call_count}次）",
            ],
        }
    except (json.JSONDecodeError, Exception) as e:
        fallback_keywords = " ".join(re.findall(r"[\u4e00-\u9fff\w]+", user_query)[:5])
        if not fallback_keywords:
            fallback_keywords = user_query[:20]
        fallback_keywords = _strip_score_words(fallback_keywords)
        fallback_tags = [w for w in fallback_keywords.split() if w.strip()][:2]
        return {
            "search_keywords": fallback_keywords,
            "browse_tags": fallback_tags,
            "need_tavily": False,
            "preferences": state.get("preferences", {}),
            "execution_path": ["understand_intent"],
            "process_log": [f"📋 意图分析(回退): 提取关键词'{fallback_keywords}'，标签{fallback_tags}"],
        }


def search_tavily_node(state: AgentState) -> dict:
    search_keywords = state.get("search_keywords", "")
    preferences = state.get("preferences", {})
    filter_params = state.get("filter_params", {})
    api_key = os.getenv("TAVILY_API_KEY")

    try:
        multi_results = tavily_multi_search(search_keywords, preferences, filter_params, api_key)
    except Exception:
        multi_results = ""

    try:
        summary = summarize_tavily_results(multi_results, search_keywords, preferences, filter_params)
    except Exception:
        summary = ""

    current_count = state.get("tavily_call_count", 0)
    return {
        "tavily_results": summary,
        "tavily_call_count": current_count + 4,
        "execution_path": ["search_tavily"],
        "process_log": [
            f"🌐 Tavily多维度搜索: 基于'{search_keywords}'搜索网络评价与口碑",
            f"📰 搜索结果: 去重后获取{len(summary)}字符的评价信息" if summary else "📰 搜索未获取有效数据",
        ],
    }


def fetch_bangumi(state: AgentState) -> dict:
    search_keywords = state.get("search_keywords", "")
    browse_tags = state.get("browse_tags", [])
    filter_params = state.get("filter_params", {})
    need_refetch = state.get("need_refetch", False)

    min_score = filter_params.get("min_score")
    year_range = filter_params.get("year_range")

    seen_ids = set()
    all_raw = []
    browse_count = 0

    def _add_browse_results(data):
        nonlocal browse_count
        for item in data:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                all_raw.append(item)
        browse_count += len(data)

    browse_min_score = min_score
    if need_refetch:
        browse_min_score = None

    if browse_tags:
        try:
            primary = browse_bangumi_by_tags(
                tags=browse_tags,
                min_score=browse_min_score,
                year_range=year_range,
                sort="score",
                limit=50,
            )
            _add_browse_results(primary)
        except Exception:
            pass

    if len(all_raw) < 20 and browse_tags:
        expanded_tag_sets = _get_expanded_tags(browse_tags)
        for tag_set in expanded_tag_sets:
            if len(all_raw) >= 20:
                break
            try:
                extra = browse_bangumi_by_tags(
                    tags=tag_set,
                    min_score=browse_min_score,
                    year_range=year_range,
                    sort="score",
                    limit=50,
                )
                _add_browse_results(extra)
            except Exception:
                pass

    if len(all_raw) < 20:
        try:
            fallback = browse_bangumi_by_tags(
                tags=None,
                min_score=browse_min_score,
                year_range=None,
                sort="score",
                limit=50,
            )
            _add_browse_results(fallback)
        except Exception:
            pass

    kw_data = []
    try:
        kw_data = search_bangumi_multi(search_keywords)
    except Exception:
        try:
            kw_data = search_bangumi(search_keywords)
        except Exception:
            kw_data = []
    for item in kw_data:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            all_raw.append(item)
    kw_count = len(kw_data)

    raw_data = all_raw
    raw_count = len(raw_data)

    raw_data = [
        item for item in raw_data
        if not _is_low_quality(item) and not _is_unreleased(item)
    ]

    after_lq = len(raw_data)

    try:
        filtered_data = filter_bangumi_data(raw_data, filter_params)
    except Exception:
        filtered_data = raw_data

    after_filter = len(filtered_data)

    filter_desc = []
    if filter_params.get("type"):
        filter_desc.append(f"类型={'/'.join(filter_params['type'])}")
    if year_range:
        filter_desc.append(f"年代={year_range}")
    if min_score and not need_refetch:
        filter_desc.append(f"评分≥{min_score}")
    if need_refetch:
        filter_desc.append("评分无限制(重拉取)")
    if filter_params.get("tags"):
        filter_desc.append(f"标签={'/'.join(filter_params['tags'])}")

    log_sources = []
    if browse_count > 0:
        log_sources.append(f"标签浏览{browse_count}部(标签={browse_tags})")
    if need_refetch:
        log_sources.append("重拉取模式")
    if kw_count > 0:
        log_sources.append(f"关键词搜索{kw_count}部")
    source_desc = " + ".join(log_sources) if log_sources else f"关键词'{search_keywords}'"

    log = [
        f"🔍 Bangumi搜索: {source_desc} → 合并去重后{raw_count}部",
        f"🚫 低质过滤: {raw_count}→{after_lq}部（剔除学生作品等）",
    ]
    if filter_desc:
        log.append(f"🔧 硬性筛选: {', '.join(filter_desc)} → {after_filter}部")
    else:
        log.append(f"📊 候选池: {after_filter}部动漫")

    return {
        "bangumi_data": filtered_data,
        "need_refetch": False,
        "execution_path": ["fetch_bangumi"],
        "process_log": log,
    }


def _get_expanded_tags(core_tags):
    tag_map = {
        "恋爱": [["纯爱"], ["校园"], ["爱情"], ["恋爱", "喜剧"]],
        "搞笑": [["喜剧"], ["日常"], ["搞笑", "校园"]],
        "异世界": [["奇幻"], ["穿越"], ["冒险"]],
        "热血": [["战斗"], ["冒险"], ["少年"]],
        "治愈": [["日常"], ["温馨"], ["生活"]],
        "科幻": [["机甲"], ["未来"], ["宇宙"]],
        "悬疑": [["推理"], ["侦探"], ["犯罪"]],
        "恐怖": [["惊悚"], ["灵异"], ["悬疑"]],
        "战斗": [["热血"], ["冒险"], ["动作"]],
        "奇幻": [["冒险"], ["异世界"], ["魔法"]],
    }
    expanded = []
    for tag in core_tags:
        if tag in tag_map:
            expanded.extend(tag_map[tag])
    if not expanded and core_tags:
        expanded = [[core_tags[0]]]
    return expanded


_BLOCKED_PATTERNS = [
    "答辩", "毕设", "毕业设计", "毕业作品", "实习", "课程设计",
    "论文", "答辩会", "汇报演出", "招生", "培训",
]


def _is_low_quality(item):
    name_cn = (item.get("name_cn") or "") + (item.get("name") or "")
    for pattern in _BLOCKED_PATTERNS:
        if pattern in name_cn:
            return True
    summary = item.get("summary") or ""
    if len(summary) > 800:
        return True
    return False


def _is_unreleased(item):
    from datetime import datetime
    air_date = item.get("air_date") or item.get("date") or ""
    if not air_date:
        rating_total = item.get("rating_total") or 0
        if rating_total and rating_total < 10:
            return True
        return False
    try:
        air_dt = datetime.strptime(air_date[:10], "%Y-%m-%d")
        if air_dt > datetime.now():
            return True
    except ValueError:
        pass
    rating_total = item.get("rating_total") or 0
    rating_score = item.get("rating_score") or 0
    if rating_score >= 9.5 and rating_total < 30:
        return True
    return False


def merge_data(state: AgentState) -> dict:
    has_tavily = bool(state.get("tavily_results", ""))
    bangumi_count = len(state.get("bangumi_data", []))
    return {
        "execution_path": ["merge_data"],
        "process_log": [
            f"🔄 数据合并: Bangumi数据{bangumi_count}部 + Tavily{'有' if has_tavily else '无'}网络评价",
        ],
    }


def _auto_generate_from_top(bangumi_data, count=5):
    if not bangumi_data:
        return []
    scored = []
    seen_ids = set()
    for item in bangumi_data:
        item_id = item.get("id")
        if not item_id or item_id <= 0:
            continue
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        score_val = item.get("rating_score") or 0
        collect = item.get("collect_count") or 0
        final = score_val * 10 + min(collect, 1000) / 100
        scored.append((final, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    result = []
    for _, item in scored[:count]:
        name = item.get("name_cn") or item.get("name", "")
        score_val = item.get("rating_score") or 0
        summary = (item.get("summary") or "")[:150]
        tags = item.get("tags", [])[:5]
        tag_str = "、".join(tags) if tags else ""
        if summary:
            reason = summary.rstrip("。！？…") + "。"
        else:
            reason = f"标签: {tag_str}" if tag_str else "暂无描述"
        result.append({
            "title": name,
            "title_original": item.get("name", ""),
            "reason": reason,
            "match_points": tags[:3] if tags else ["类型匹配"],
            "score": item.get("rating_score"),
            "tags": tags,
            "image_url": item.get("images_large", ""),
            "bangumi_id": item.get("id"),
        })
    return result


def _auto_generate_with_llm(bangumi_data, user_query, preferences, count=5):
    top = _auto_generate_from_top(bangumi_data, count)
    if not top:
        return top

    items_text = []
    for i, item in enumerate(top, 1):
        items_text.append(f"{i}. {item['title']} (评分{item['score']}, bangumi_id={item['bangumi_id']})")

    llm = get_llm()
    prompt = f"""你是动漫推荐专家。以下是通过评分排序筛选出的作品，请为每部生成与用户查询紧密相关的个性化推荐理由和匹配点。

用户查询: {user_query}
用户偏好: {json.dumps(preferences, ensure_ascii=False)}

作品列表:
{chr(10).join(items_text)}

请为每部作品输出一个JSON对象，要求：
- reason: 结合用户查询的个性化推荐理由(50字内)，不要使用"Bangumi评分X.X"格式，要用自然语言描述这部作品为什么符合用户的需求
- match_points: 2-3个具体的匹配点，说明作品与用户查询的具体关联

只输出JSON数组:
[{{"index":1,"reason":"个性化推荐理由","match_points":["匹配点1","匹配点2"]}}]"""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            reasons = json.loads(json_match.group(0))
            if isinstance(reasons, list):
                for r in reasons:
                    if isinstance(r, dict):
                        idx = r.get("index", 0)
                        if 1 <= idx <= len(top):
                            top[idx - 1]["reason"] = r.get("reason", top[idx - 1]["reason"])
                            top[idx - 1]["match_points"] = r.get("match_points", top[idx - 1]["match_points"])
    except (json.JSONDecodeError, Exception):
        pass

    return top


def _parse_score_from_feedback(feedback):
    score_matches = re.findall(r"评分\s*(?:≥|>=|>|高于|不低于|至少)?\s*(\d+\.?\d*)", feedback)
    for s in score_matches:
        try:
            val = float(s)
            if 5.0 <= val <= 9.5:
                return val
        except ValueError:
            continue
    if "评分高" in feedback or "高分" in feedback:
        return 7.0
    if "评分低" in feedback or "评分不足" in feedback:
        return None
    return None


def _extract_rules_from_feedback(feedback):
    rules = []
    fb = feedback.lower()

    if "重复" in fb or "系列" in fb or "season" in fb or "季" in fb:
        rules.append("- 严禁推荐同一系列的多部作品（如第1季和第3季），每个系列最多选1部")

    if "id" in fb and ("0" in fb or "无效" in fb or "null" in fb):
        rules.append("- 只推荐bangumi_id为正整数的作品，id=0或null的条目严禁选择")

    if "多样" in fb or "单一" in fb or "重复" in fb:
        rules.append("- 必须从至少3个不同年份和至少2种不同风格中选择")

    if "匹配" in fb and ("低" in fb or "不足" in fb or "不符" in fb):
        rules.append("- 每部推荐必须与用户查询高度相关，严禁推荐明显不匹配的作品")

    if "正规" in fb or "官方" in fb or "学生" in fb or "毕设" in fb:
        rules.append("- 只推荐正规官方番剧，学生毕设/答辩/课程作业/同人作品绝对不要")

    if "评分" in fb and ("低" in fb or "不足" in fb or "6" in fb):
        rules.append("- 优先选择评分>=6.0的作品，评分过低的不要推荐")

    if "类型" in fb and ("不符" in fb or "偏离" in fb or "核心" in fb):
        rules.append("- 必须确保每部推荐的核心类型与用户查询一致，副类型不算匹配")

    if not rules:
        rules = [
            "- 增加多样性，避免同系列重复",
            "- 只选正规番剧，确保bangumi_id有效",
            "- 每部推荐必须与用户查询明确相关",
        ]

    return "\n".join(rules)


def _filter_data_by_feedback(bangumi_data, feedback):
    if not feedback or not bangumi_data:
        return bangumi_data
    filtered = list(bangumi_data)
    fb = feedback.lower()

    seen_ids = set()
    deduped = []
    scored_for_dedup = sorted(
        filtered,
        key=lambda x: (x.get("rating_score") or 0) + (min(x.get("collect_count") or 0, 1000) / 100),
        reverse=True,
    )
    for item in scored_for_dedup:
        item_id = item.get("id")
        if item_id and item_id > 0 and item_id not in seen_ids:
            seen_ids.add(item_id)
            deduped.append(item)
        elif not item_id or item_id <= 0:
            continue
    filtered = deduped

    banned_names = set()
    chinese_bookmarks = re.findall(r"《([^》]+)》", feedback)
    for name in chinese_bookmarks:
        banned_names.add(name.strip().lower())
        banned_names.add(name.strip())

    negative_sections = []
    neg_patterns = [
        r"包含[^，。；]*《([^》]+)》",
        r"推荐[^，。；]*《([^》]+)》.*?(?:不符|偏离|不当|错误|不相关|不算|非[恋爱言情喜剧])",
        r"如《([^》]+)》",
        r"《([^》]+)》.*?(?:为副线|核心.*?(?:机战|科幻|战斗|体育|运动|家庭|喜剧|欧美|儿童|冒险|超级英雄|偶像|音乐)|无恋爱情节|属于青春情感|恋爱.*(?:次要|支线)|非.*核心)",
        r"(?:核心|主要).*?(?:偏向|更接近|不属于).*?《([^》]+)》",
        r"《([^》]+)》.*?(?:恋爱元素|恋爱标签).*?(?:次要|极少|不足以|不是主线)",
    ]
    for pat in neg_patterns:
        for m in re.finditer(pat, feedback):
            name = m.group(1).strip()
            if len(name) >= 2:
                banned_names.add(name.lower())
                banned_names.add(name)

    if banned_names:
        filtered = [
            item for item in filtered
            if not _item_matches_names(item, banned_names)
        ]

    if any(w in fb for w in ["学生", "毕设", "答辩"]):
        filtered = [item for item in filtered if not _is_low_quality(item)]

    if "id" in fb and ("0" in fb or "无效" in fb or "null" in fb):
        filtered = [item for item in filtered if item.get("id") and item["id"] > 0]

    if len(filtered) == 0:
        return []

    return filtered


def _item_matches_names(item, names):
    name_cn = (item.get("name_cn") or "").strip().lower()
    name_raw = (item.get("name") or "").strip().lower()
    combined = name_cn + "|" + name_raw
    for name in names:
        if name.lower() in combined:
            return True
        if name.lower() in name_cn or name.lower() in name_raw:
            return True
    return False


def generate_recommendations(state: AgentState) -> dict:
    bangumi_data = state.get("bangumi_data", [])
    tavily_results = state.get("tavily_results", "")
    user_query = state.get("user_query", "")
    preferences = state.get("preferences", {})
    evaluation_feedback = state.get("evaluation_feedback", "")
    reflection_count = state.get("reflection_count", 0)
    bangumi_count = len(bangumi_data)

    if not bangumi_data:
        return {
            "candidate_recommendations": [],
            "execution_path": ["generate_recommendations"],
            "process_log": [
                "🤖 AI推荐引擎: 候选池为空，无法生成推荐",
                "📝 生成推荐: 0部",
            ],
        }

    lightweight_data = []
    for item in bangumi_data:
        lightweight_data.append({
            "id": item.get("id"),
            "name_cn": item.get("name_cn") or item.get("name"),
            "name": item.get("name"),
            "score": item.get("rating_score"),
            "rating_total": item.get("rating_total"),
            "tags": item.get("tags", [])[:8],
            "date": item.get("air_date") or item.get("date"),
            "eps": item.get("eps"),
            "collect_count": item.get("collect_count"),
            "summary": (item.get("summary") or "")[:80],
            "image_url": item.get("image_url") or item.get("images_large") or "",
        })

    bangumi_str = json.dumps(lightweight_data, ensure_ascii=False)

    top_items = sorted(
        bangumi_data,
        key=lambda x: (x.get("rating_score") or 0) * 10 + (min(x.get("collect_count") or 0, 500) / 100),
        reverse=True,
    )[:8]
    top_lines = []
    for t in top_items:
        name = t.get("name_cn") or t.get("name", "?")
        top_lines.append(f"  {name} (评分{t.get('rating_score','N/A')}, 收藏{t.get('collect_count',0)})")
    top_hint = "Top候选快速参考:\n" + "\n".join(top_lines)

    tavily_context = ""
    if tavily_results:
        tavily_context = f"网络口碑与评价信息:\n{tavily_results[:1500]}"

    retry_context = ""
    if evaluation_feedback and reflection_count > 0:
        rules = _extract_rules_from_feedback(evaluation_feedback)
        retry_context = f"""\n⚠️ 这是第{reflection_count}次重试。上一轮评估不通过。

你必须严格遵守以下规则（从审查反馈中提取）:
{rules}
"""
    else:
        retry_context = ""

    target_count = min(5, bangumi_count)

    if bangumi_count < 5:
        default_rules = f"""\n⚠️ 候选池仅有{bangumi_count}部作品，请从中选出不超过{target_count}部符合要求的推荐。
- 如果某部作品的核心类型明显不符合用户查询，跳过它
- 每部推荐至少标注2个具体匹配理由
- 严禁推荐同一系列的多部作品"""
    else:
        default_rules = f"""\n🚨 硬性约束:
- 必须输出EXACTLY 5部推荐，一部都不能少
- 每部推荐的bangumi_id必须是有效的正整数（不能是0或null）
- 严禁推荐同一系列的多部作品（如同时推荐第1季和第3季）
- 每部推荐至少标注2个具体匹配理由
- 必须覆盖至少3个不同年份和2种不同风格
- 严禁输出少于5部"""

    core_type_rule = """\n🎯 核心类型强制匹配规则:
- 你必须在推荐前判断每部作品的核心（第一）类型是否真正匹配用户查询
- 如果用户查询"恋爱番剧"，作品必须以恋爱为核心类型。副类型含恋爱但核心是机战/科幻/战斗/体育的作品（如《机动战士高达SEED》）绝对不要推荐
- 如果用户查询"异世界番剧"，作品必须以异世界/穿越为核心设置
- 不要被作品的标签列表迷惑——标签列表包含所有相关标签，但不代表核心类型
- 如果一部作品的核心类型疑似与用户查询不符，宁可跳过它"""

    llm = get_llm()

    prompt = f"""你是动漫推荐专家。从候选池中为用户选出最符合要求的动漫（候选池共{bangumi_count}部，目标输出{target_count}部）。

用户查询: {user_query}
用户偏好: {json.dumps(preferences, ensure_ascii=False)}

{top_hint}

完整候选池:
{bangumi_str}

{tavily_context}
{retry_context}{default_rules}{core_type_rule}

质量规则:
- 只推荐正规番剧，不要学生毕设/答辩/同人
- 优先评分>=6.0且收藏数高的作品

只输出JSON数组:
[{{"title":"中文名","title_original":"原名","reason":"推荐理由","match_points":["点1","点2"],"score":0,"tags":["标签"],"image_url":"封面URL","bangumi_id":0}}]"""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        recommendations = json.loads(content)
        if not isinstance(recommendations, list):
            recommendations = []
        recommendations = [r for r in recommendations if isinstance(r, dict)]
    except (json.JSONDecodeError, Exception):
        recommendations = []

    auto_filled = False
    min_expected = 1 if bangumi_count < 3 else 3
    if len(recommendations) < min_expected:
        recommendations = _auto_generate_with_llm(bangumi_data, user_query, preferences, count=target_count)
        auto_filled = True

    candidate_names = []
    for item in bangumi_data[:10]:
        name = item.get("name_cn") or item.get("name", "")
        if name:
            candidate_names.append(f"《{name}》")
    names_str = "、".join(candidate_names)
    if bangumi_count > 10:
        names_str += f"... 等{bangumi_count}部"

    return {
        "candidate_recommendations": recommendations,
        "execution_path": ["generate_recommendations"],
        "process_log": [
            f"🤖 AI推荐引擎: 从{bangumi_count}部候选中筛选",
            f"🎬 候选作品: {names_str}" if names_str else f"🎬 候选作品: {bangumi_count}部",
            "⭐ 质量偏好: 评分≥6.0 + 高评分优先",
            f"📝 生成推荐: {len(recommendations)}部{' (自动补全)' if auto_filled else ''}",
        ],
    }


def evaluate_recommendations(state: AgentState) -> dict:
    candidate_recommendations = state.get("candidate_recommendations", [])
    user_query = state.get("user_query", "")
    preferences = state.get("preferences", {})
    filter_params = state.get("filter_params", {})

    if not candidate_recommendations:
        return {
            "pass_evaluation": False,
            "evaluation_feedback": "推荐列表为空，无法通过评估。",
            "execution_path": ["evaluate_recommendations"],
        }

    llm = get_llm()

    prompt = f"""你是一个动漫推荐质量审查员（Critic）。请审查以下推荐结果，判断是否满足质量标准。

用户原始查询: {user_query}
用户偏好: {json.dumps(preferences, ensure_ascii=False)}
筛选参数: {json.dumps(filter_params, ensure_ascii=False)}

待审查的推荐列表:
{json.dumps(candidate_recommendations, ensure_ascii=False, indent=2)}

审查标准（按优先级排列）:

【硬性标准 - 违反则不通过】:
1. 是否存在同一系列的多部作品（如同一作品的不同季、剧场版与TV版同时出现）？如果有，不通过。
2. 每部推荐的核心类型是否与用户查询意图匹配？例如用户要"恋爱喜剧"，核心类型是偶像/音乐的作品不算匹配。
3. 如果用户查询中提到了特定作品（如"和XX相似的"），推荐是否确实与该作品在类型/风格/主题上相似？

【软性标准 - 建议改善但不强制拦截】:
4. 推荐的年份和风格多样性。注意：如果用户查询本身就很宽泛（如"推荐一些恋爱番"），同类热门作品集中推荐是合理的，不应因此判定不通过。
5. 推荐理由是否包含了与用户查询相关的具体匹配点。

【注意】:
- 不要过度纠偏。如果推荐列表基本符合用户意图，即使多样性不够完美也应通过。
- 只有在存在明确的硬性违规（同系列重复、核心类型不匹配）时才判定不通过。
- 不要将"风格单一"作为宽泛查询的不通过理由。

请输出以下JSON格式，不要包含任何其他内容:
{{
    "pass": true或false,
    "feedback": "具体的审查反馈意见。如果未通过，必须明确指出哪部作品有什么硬性违规"
}}"""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        result = json.loads(content)
        passed = result.get("pass", False)
        feedback = result.get("feedback", "")
    except (json.JSONDecodeError, Exception):
        passed = False
        feedback = "审查结果解析失败，默认不通过。"

    return {
        "pass_evaluation": passed,
        "evaluation_feedback": feedback,
        "execution_path": ["evaluate_recommendations"],
        "process_log": [
            f"🔎 质量审查: {'✅ 通过' if passed else '❌ 未通过'} - {feedback[:300]}",
        ],
    }


def refine_search(state: AgentState) -> dict:
    evaluation_feedback = state.get("evaluation_feedback", "")
    current_keywords = state.get("search_keywords", "")
    user_query = state.get("user_query", "")
    preferences = state.get("preferences", {})
    bangumi_data = state.get("bangumi_data", [])
    filter_params = state.get("filter_params", {})

    filtered_data = _filter_data_by_feedback(bangumi_data, evaluation_feedback)

    updated_filter_params = dict(filter_params)
    score_update = _parse_score_from_feedback(evaluation_feedback)
    score_log = ""
    if score_update is not None:
        existing_min = updated_filter_params.get("min_score")
        if existing_min is None or score_update > existing_min:
            updated_filter_params["min_score"] = score_update
            score_log = f"，评分阈值→≥{score_update}"

    llm = get_llm()

    prompt = f"""你是一个动漫搜索策略优化器。当前搜索关键词未能产出满意的推荐结果，请根据反馈调整搜索策略。

用户原始查询: {user_query}
用户偏好: {json.dumps(preferences, ensure_ascii=False)}
当前搜索关键词: {current_keywords}
评估反馈: {evaluation_feedback}

请分析反馈中的问题，生成新的搜索关键词。规则：
- 关键词必须是简短的类型/风格/主题词，每次最多1-2个词。
- 绝对不要使用以下类型的词作为搜索关键词：国家名（如"日本""中国""韩国"）、放送载体（如"TV""OVA""剧场版""电影"）、评分修饰词（如"高分""低分""神作""评分"）、通用词（如"推荐""番剧""动画"）。
- 这些国家/载体信息应通过筛选参数(filter)处理，不是搜索关键词。
- 如果推荐不相关，更换类型角度（如"恋爱"→"纯爱"或"恋爱"→"傲娇"），而不是堆砌更多词。
- 如果推荐列表为空或结果太少，使用更简短宽泛的关键词（例如只用"恋爱"一个词）。
- 不要返回完整的自然语言句子作为搜索词。

请严格只输出以下JSON格式，不要包含任何其他内容:
{{
    "search_keywords": "1-2个核心类型关键词"
}}"""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        result = json.loads(content)
        new_keywords = result.get("search_keywords", current_keywords)
    except (json.JSONDecodeError, Exception):
        new_keywords = current_keywords

    new_keywords = _strip_score_words(new_keywords)

    if len(filtered_data) < 3 and len(bangumi_data) >= 5:
        filtered_data = bangumi_data
        pool_log = f"🧹 数据清洗: {len(bangumi_data)}→{len(_filter_data_by_feedback(bangumi_data, evaluation_feedback))}部（清洗后不足3部，回滚到原始池）"
        need_refetch = False
    elif len(filtered_data) < 3:
        need_refetch = True
        pool_log = f"🧹 数据清洗: {len(bangumi_data)}→{len(filtered_data)}部（不足3部，触发重新拉取）"
    elif len(filtered_data) == 0:
        need_refetch = True
        pool_log = f"🧹 数据清洗: {len(bangumi_data)}→0部（全部不合格，需要扩大搜索范围）"
    else:
        need_refetch = False
        pool_log = f"🧹 数据清洗: {len(bangumi_data)}→{len(filtered_data)}部（根据审查反馈清理）"

    current_reflection = state.get("reflection_count", 0)
    return {
        "search_keywords": new_keywords,
        "reflection_count": current_reflection + 1,
        "bangumi_data": filtered_data,
        "filter_params": updated_filter_params,
        "need_refetch": need_refetch,
        "execution_path": ["refine_search"],
        "process_log": [
            f"🔄 搜索策略优化(第{current_reflection + 1}次): '{current_keywords}' → '{new_keywords}'{score_log}",
            f"💡 优化依据: {evaluation_feedback[:120]}",
            pool_log,
        ],
    }


def format_response(state: AgentState) -> dict:
    candidate_recommendations = state.get("candidate_recommendations", [])
    pass_evaluation = state.get("pass_evaluation", True)
    bangumi_data = state.get("bangumi_data", [])
    user_query = state.get("user_query", "")
    preferences = state.get("preferences", {})
    filter_params = state.get("filter_params", {})
    evaluation_feedback = state.get("evaluation_feedback", "")

    if not pass_evaluation and bangumi_data:
        min_score = filter_params.get("min_score")
        filtered_data = list(bangumi_data)
        if min_score is not None:
            filtered_data = [item for item in filtered_data if (item.get("rating_score") or 0) >= min_score]
        if evaluation_feedback:
            filtered_data = _filter_data_by_feedback(filtered_data, evaluation_feedback)
        if len(filtered_data) < 3 and len(bangumi_data) >= 5:
            filtered_data = bangumi_data
        candidate_recommendations = _auto_generate_with_llm(filtered_data, user_query, preferences, count=5)
        n = len(candidate_recommendations)
        return {
            "final_recommendations": candidate_recommendations,
            "execution_path": ["format_response"],
            "process_log": [
                f"📦 最终输出: {n}部推荐结果 (审查不通过，LLM增强自动兜底+评分过滤)",
                f"📊 排序依据: 评分≥{min_score if min_score else '无限制'}筛选后按评分×收藏热度排序",
            ],
        }

    n = len(candidate_recommendations)
    return {
        "final_recommendations": candidate_recommendations,
        "execution_path": ["format_response"],
        "process_log": [
            f"📦 最终输出: {n}部推荐结果",
            f"📊 排序依据: 综合评分×收藏热度×用户偏好匹配度",
        ],
    }