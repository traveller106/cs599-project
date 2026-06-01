import os
import time
import json
from pathlib import Path
import requests
from urllib.parse import quote
from dotenv import load_dotenv
from tavily import TavilyClient

_ENV_PATH = Path(__file__).resolve().parent / ".env"

BANGUMI_SEARCH_URL = "https://api.bgm.tv/search/subject/{keyword}?type=2&responseGroup=large"
BANGUMI_DETAIL_URL = "https://api.bgm.tv/subject/{subject_id}?responseGroup=large"
BANGUMI_BROWSE_URL = "https://api.bgm.tv/v0/subjects"
USER_AGENT = "AnimeRecommender/1.0 (contact@example.com)"


def load_config():
    load_dotenv(_ENV_PATH)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not deepseek_key:
        raise ValueError("DEEPSEEK_API_KEY is not set in environment variables")
    if not tavily_key:
        raise ValueError("TAVILY_API_KEY is not set in environment variables")
    return {"DEEPSEEK_API_KEY": deepseek_key, "TAVILY_API_KEY": tavily_key}


def _classify_item_type(item):
    name_raw = item.get("name", "") or ""
    name_cn = item.get("name_cn", "") or ""
    combined = (name_cn + name_raw).lower()
    eps = item.get("eps", 0) or 0

    if "ova" in combined or "oad" in combined:
        return "ova"
    if "剧场版" in combined or "movie" in combined or "映画" in combined:
        return "剧场版"
    if "web" in combined and eps <= 6:
        return "web"
    if eps == 1:
        return "剧场版"
    if eps >= 2:
        return "tv"
    return "tv"


def _extract_item(item):
    tags = []
    if "tags" in item:
        tags = [t["name"] for t in item["tags"]]

    collection = item.get("collection", {})
    collect_count = 0
    if isinstance(collection, dict):
        collect_count = sum(v for k, v in collection.items() if isinstance(v, (int, float)))

    item_type = _classify_item_type(item)

    rating = item.get("rating", {})
    rating_score = rating.get("score") if isinstance(rating, dict) else None
    rating_total = rating.get("total", 0) if isinstance(rating, dict) else 0

    summary = item.get("summary", "") or ""
    if len(summary) > 500:
        summary = summary[:500] + "..."

    result = {
        "id": item.get("id"),
        "name": item.get("name"),
        "name_cn": item.get("name_cn"),
        "images_large": item.get("images", {}).get("large") if item.get("images") else None,
        "image_url": item.get("images", {}).get("large") if item.get("images") else None,
        "summary": summary,
        "rating_score": rating_score,
        "rating_total": rating_total,
        "tags": tags,
        "date": item.get("date", ""),
        "air_date": item.get("air_date", ""),
        "eps": item.get("eps", 0),
        "item_type": item_type,
        "collect_count": collect_count,
    }
    return result


def _extract_v0_item(item):
    tags = []
    if "tags" in item:
        for t in item["tags"]:
            if isinstance(t, dict):
                tags.append(t.get("name", ""))
            elif isinstance(t, str):
                tags.append(t)

    collection = item.get("collection", {})
    collect_count = 0
    if isinstance(collection, dict):
        collect_count = sum(v for k, v in collection.items() if isinstance(v, (int, float)))

    rating = item.get("rating", {})
    rating_score = rating.get("score") if isinstance(rating, dict) else None
    rating_total = rating.get("total", 0) if isinstance(rating, dict) else 0

    summary = item.get("summary", "") or ""
    if len(summary) > 500:
        summary = summary[:500] + "..."

    date_str = item.get("date", "") or ""
    air_date = item.get("air_date", "") or date_str

    eps = item.get("eps", 0) or 0
    if eps == 0:
        total_eps = item.get("total_episodes", 0) or 0
        if total_eps:
            eps = total_eps

    result = {
        "id": item.get("id"),
        "name": item.get("name"),
        "name_cn": item.get("name_cn"),
        "images_large": _extract_v0_image(item.get("images")),
        "image_url": _extract_v0_image(item.get("images")),
        "summary": summary,
        "rating_score": rating_score,
        "rating_total": rating_total,
        "tags": tags,
        "date": date_str,
        "air_date": air_date,
        "eps": eps,
        "item_type": _classify_item_type({"name": item.get("name", ""), "name_cn": item.get("name_cn", ""), "eps": eps}),
        "collect_count": collect_count,
    }
    return result


def _extract_v0_image(images):
    if not images or not isinstance(images, dict):
        return None
    for key in ("large", "common", "medium", "small", "grid"):
        url = images.get(key)
        if url:
            return url
    return None


def _do_search(keyword):
    url = BANGUMI_SEARCH_URL.format(keyword=quote(keyword))
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "list" in data:
                return [_extract_item(item) for item in data["list"]]
            if isinstance(data, dict) and "error" in data:
                return []
            return []
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(1)
    return []


def search_bangumi(keyword):
    if not keyword or not keyword.strip():
        return []
    results = _do_search(keyword)
    if results:
        return results
    words = keyword.split()
    if len(words) > 1:
        for i in range(len(words) - 1, 0, -1):
            shorter = " ".join(words[:i])
            results = _do_search(shorter)
            if results:
                return results
    return results


def search_bangumi_multi(keyword):
    if not keyword or not keyword.strip():
        return []
    words = keyword.split()
    if len(words) <= 1:
        return search_bangumi(keyword)

    seen_ids = set()
    all_results = []
    item_keyword_hits = {}

    for w in words:
        if not w.strip():
            continue
        batch = _do_search(w)
        for item in batch:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                all_results.append(item)
                item_keyword_hits[item_id] = 1
            elif item_id and item_id in item_keyword_hits:
                item_keyword_hits[item_id] += 1

    if not all_results:
        return search_bangumi(keyword)

    combined = search_bangumi(keyword)
    for item in combined:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            all_results.append(item)
            item_keyword_hits[item_id] = 1

    multi_keyword_items = [
        item for item in all_results
        if item_keyword_hits.get(item.get("id"), 1) >= 2
    ]

    if len(multi_keyword_items) >= 5:
        remaining = [item for item in all_results if item_keyword_hits.get(item.get("id"), 1) < 2]
        multi_keyword_items.extend(remaining)
        return multi_keyword_items

    return all_results


def browse_bangumi_by_tags(tags, min_score=None, year_range=None, sort="rank", limit=50):
    url = "https://api.bgm.tv/v0/search/subjects"
    payload = {
        "keyword": "",
        "sort": sort,
        "filter": {
            "type": [2],
        },
    }
    if tags:
        tag_list = [t.strip() for t in tags if t.strip()]
        if tag_list:
            payload["filter"]["tag"] = tag_list
    rating_filters = []
    if min_score is not None:
        rating_filters.append(f">={min_score}")
    if rating_filters:
        payload["filter"]["rating"] = rating_filters
    if year_range and len(year_range) == 2:
        payload["filter"]["airdate"] = [f">={year_range[0]}-01-01", f"<={year_range[1]}-12-31"]

    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    all_items = []
    max_pages = min(10, max(3, limit // 10 + 2))
    for page in range(max_pages):
        payload["limit"] = 25
        payload["offset"] = page * 25
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    all_items.extend(items)
                    if len(items) < 25:
                        page = 9999
                    break
            except (requests.exceptions.RequestException, json.JSONDecodeError):
                if attempt < 2:
                    time.sleep(1)
                    continue
                break
        if page == 9999:
            break

    seen_ids = set()
    result = []
    for item in all_items:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            result.append(_extract_v0_item(item))

    return result


def get_bangumi_detail(subject_id):
    url = BANGUMI_DETAIL_URL.format(subject_id=subject_id)
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 429:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(1)
                continue
            return None


def search_tavily_tool(query, api_key):
    client = TavilyClient(api_key=api_key)
    try:
        response = client.search(query, max_results=3, search_depth="advanced")
        return json.dumps(response, ensure_ascii=False)
    except Exception:
        return ""


def _build_tavily_queries(search_keywords, preferences, filter_params):
    queries = []
    tags = filter_params.get("tags", []) or []
    fav_genres = preferences.get("fav_genres", [])

    base = search_keywords.strip()
    if not base:
        return queries

    queries.append(f"{base} 动漫 推荐 最佳")

    if tags:
        tag_str = " ".join(tags[:3])
        queries.append(f"{base} {tag_str} 动漫 评价 口碑")

    queries.append(f"{base} anime review recommendation rating")

    if fav_genres:
        genre_str = " ".join(fav_genres[:2])
        queries.append(f"{base} {genre_str} 番剧 观众评价 豆瓣 bangumi")

    queries.append(f"{base} anime 人气排名 热门推荐 2024 2025")

    return queries


def tavily_multi_search(search_keywords, preferences, filter_params, api_key):
    queries = _build_tavily_queries(search_keywords, preferences, filter_params)
    if not queries:
        return ""

    all_results = []
    seen_urls = set()
    for query in queries[:4]:
        raw = search_tavily_tool(query, api_key)
        if not raw:
            continue
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            items = data.get("results", []) if isinstance(data, dict) else []
            for item in items:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title": item.get("title", ""),
                        "content": item.get("content", "")[:400],
                        "url": url,
                        "score": item.get("score", 0),
                    })
        except (json.JSONDecodeError, TypeError):
            pass

    total = len(all_results)
    return json.dumps({
        "total_results": total,
        "results": all_results[:8],
    }, ensure_ascii=False)


def summarize_tavily_results(tavily_json, search_keywords, preferences, filter_params):
    if not tavily_json:
        return ""
    try:
        data = json.loads(tavily_json) if isinstance(tavily_json, str) else tavily_json
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(data, dict) or not data.get("results"):
        return ""

    keywords_lower = search_keywords.lower().split()
    tags_lower = [t.lower() for t in (filter_params.get("tags", []) or [])]
    fav_genres_lower = [g.lower() for g in (preferences.get("fav_genres", []) or [])]

    scored = []
    for item in data["results"]:
        title = (item.get("title", "") or "").lower()
        content = (item.get("content", "") or "").lower()
        combined = title + " " + content

        relevance = 0
        for kw in keywords_lower:
            if kw in combined:
                relevance += 3
        for tag in tags_lower:
            if tag in combined:
                relevance += 2
        for genre in fav_genres_lower:
            if genre in combined:
                relevance += 2

        has_rating_keywords = any(w in combined for w in ["评分", "rating", "score", "口碑", "推荐", "评价", "review"])
        if has_rating_keywords:
            relevance += 1

        scored.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "url": item.get("url", ""),
            "relevance": relevance,
        })

    scored.sort(key=lambda x: x["relevance"], reverse=True)

    top = scored[:5]
    lines = []
    for i, s in enumerate(top, 1):
        lines.append(f"[{i}] {s['title']}")
        lines.append(f"    摘要: {s['content'][:200]}")
        lines.append(f"    相关性: {s['relevance']}分")
        lines.append("")

    summary = "\n".join(lines)
    return f"网络搜索结果汇总 (共{data.get('total_results', len(scored))}条，精选{len(top)}条):\n\n{summary}"


def filter_bangumi_data(data, filter_params):
    if not filter_params:
        return data
    filtered = []
    for item in data:
        if "type" in filter_params and filter_params["type"]:
            allowed = [t.lower() for t in filter_params["type"]]
            item_type = (item.get("item_type", "") or "").lower()
            if item_type not in allowed:
                continue
        if "year_range" in filter_params and filter_params["year_range"]:
            try:
                start_year, end_year = filter_params["year_range"]
                year_str = item.get("air_date") or item.get("date") or ""
                if not year_str:
                    continue
                item_year = int(str(year_str).split("-")[0])
                if item_year < start_year or item_year > end_year:
                    continue
            except (ValueError, TypeError):
                pass
        if "min_score" in filter_params and filter_params["min_score"] is not None:
            item_score = item.get("rating_score")
            if item_score is None or item_score < filter_params["min_score"]:
                continue
        if "tags" in filter_params and filter_params["tags"]:
            required_tags = [t.lower() for t in filter_params["tags"]]
            search_text = (
                (item.get("name_cn", "") or "") + " "
                + (item.get("name", "") or "") + " "
                + (item.get("summary", "") or "")
            ).lower()
            if not any(rt in search_text for rt in required_tags):
                continue
        filtered.append(item)
    return filtered