#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI
from style_profiles import format_style_profile, get_style_profile


ROOT_DIR = Path(__file__).resolve().parents[2]
TREND_NEWS_DIR = ROOT_DIR / "Trend-grab-agent" / "output" / "news"
OUTPUT_ROOT = ROOT_DIR / "orchestrator" / "output"

CATEGORY_AGENTS = [
    {
        "key": "ent_female",
        "name": "娱乐圈女明星新闻",
    },
    {
        "key": "ent_male",
        "name": "娱乐圈男明星新闻",
    },
    {
        "key": "intl_politics",
        "name": "国际政治",
    },
    {
        "key": "domestic_politics",
        "name": "国内政治",
    },
    {
        "key": "esports",
        "name": "电竞比赛",
    },
    {
        "key": "traditional_sports",
        "name": "传统体育比赛",
    },
    {
        "key": "other",
        "name": "其他热点",
    },
]

VIRAL_FRAMEWORK = [
    "开头必须有钩子，不准温吞开场",
    "必须给出清晰观点，而不是中性复述",
    "优先写冲突、反差、利害关系、站队点",
    "标题要有信息增量，不能像公文摘要",
    "短文案要像平台原生文案，不要像行业报告",
    "在合规前提下，允许锋利，不允许空泛",
]


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        data[key] = value
    return data


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd or ROOT_DIR), check=True)


def run_trend_once() -> None:
    run_cmd(["bash", "scripts/run_trend.sh", "run"], cwd=ROOT_DIR)


def latest_news_db() -> Path:
    if not TREND_NEWS_DIR.exists():
        raise FileNotFoundError(f"未找到目录: {TREND_NEWS_DIR}")
    db_files = sorted(TREND_NEWS_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not db_files:
        raise FileNotFoundError("未找到热点数据库文件")
    return db_files[0]


def fetch_hotspots(db_path: Path, top_k_per_platform: int, focus_platforms: list[str]) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        latest_crawl_time = conn.execute("SELECT MAX(crawl_time) AS t FROM rank_history").fetchone()["t"]
        if not latest_crawl_time:
            raise RuntimeError("数据库中没有 rank_history 数据")

        sql = """
        SELECT
          p.id AS platform_id,
          p.name AS platform_name,
          n.title AS title,
          r.rank AS rank,
          n.url AS url,
          n.mobile_url AS mobile_url
        FROM rank_history r
        JOIN news_items n ON r.news_item_id = n.id
        JOIN platforms p ON n.platform_id = p.id
        WHERE r.crawl_time = ?
        ORDER BY p.id ASC, r.rank ASC
        """
        rows = conn.execute(sql, (latest_crawl_time,)).fetchall()
    finally:
        conn.close()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = row["platform_id"]
        if focus_platforms and pid not in focus_platforms:
            continue
        if pid not in grouped:
            grouped[pid] = {
                "platform_id": pid,
                "platform_name": row["platform_name"],
                "items": [],
            }
        if len(grouped[pid]["items"]) >= top_k_per_platform:
            continue
        grouped[pid]["items"].append(
            {
                "rank": row["rank"],
                "title": row["title"],
                "url": row["mobile_url"] or row["url"] or "",
            }
        )

    platforms = list(grouped.values())
    total_items = sum(len(p["items"]) for p in platforms)
    return {
        "source_db": str(db_path),
        "crawl_time": latest_crawl_time,
        "platform_count": len(platforms),
        "item_count": total_items,
        "platforms": platforms,
    }


def flatten_hotspots(hotspots: dict[str, Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    idx = 1
    for platform in hotspots.get("platforms", []):
        for item in platform.get("items", []):
            flat.append(
                {
                    "item_id": f"item_{idx}",
                    "platform_id": platform["platform_id"],
                    "platform_name": platform["platform_name"],
                    "rank": item["rank"],
                    "title": item["title"],
                    "url": item["url"],
                }
            )
            idx += 1
    return flat


def extract_json_block(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def build_client(env: dict[str, str]) -> tuple[OpenAI, str, str]:
    api_key = env.get("GM_LLM_API_KEY", "").strip()
    model = env.get("GM_LLM_MODEL", "").strip()
    base_url = env.get("GM_LLM_API_BASE", "").strip()
    if not api_key or not model or not base_url:
        raise RuntimeError("缺少 GM_LLM_API_KEY / GM_LLM_MODEL / GM_LLM_API_BASE")

    normalized_base_url = base_url.rstrip("/")
    if not normalized_base_url.endswith("/v1"):
        normalized_base_url = normalized_base_url + "/v1"
    return OpenAI(api_key=api_key, base_url=normalized_base_url), model, normalized_base_url


def _usage_to_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def call_chat(
    client: OpenAI,
    model: str,
    agent_name: str,
    messages: list[dict[str, str]],
    tracker: dict[str, Any],
    max_tokens: int = 3500,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    usage = _usage_to_dict(getattr(resp, "usage", None))
    tracker["calls"].append(
        {
            "agent": agent_name,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "ts": datetime.now().isoformat(),
        }
    )
    return resp.choices[0].message.content or ""


def llm_json(
    client: OpenAI,
    model: str,
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    tracker: dict[str, Any],
    max_tokens: int = 3500,
) -> dict[str, Any]:
    text = call_chat(
        client=client,
        model=model,
        agent_name=agent_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tracker=tracker,
        max_tokens=max_tokens,
    )
    return extract_json_block(text)


def classify_hotspots(
    client: OpenAI,
    model: str,
    flat_items: list[dict[str, Any]],
    tracker: dict[str, Any],
) -> dict[str, Any]:
    categories = [c["name"] for c in CATEGORY_AGENTS]
    system_prompt = (
        "你是热点分类Agent。任务是把每条热点分到最合适的一个类别。"
        "必须严格输出JSON，不要输出其它文本。"
    )
    user_prompt = (
        "请按类别对以下热点逐条分类。\n"
        "分类范围：\n"
        f"{categories}\n\n"
        "规则：\n"
        "1) 每条热点只能归入一个类别；\n"
        "2) 不确定时归入“其他热点”；\n"
        "3) 输出简短理由。\n\n"
        "输出JSON Schema:\n"
        "{\n"
        '  "results": [\n'
        "    {\n"
        '      "item_id": "item_1",\n'
        '      "category": "电竞比赛",\n'
        '      "reason": "一句话理由",\n'
        '      "confidence": 0.86\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"热点条目:\n{json.dumps(flat_items, ensure_ascii=False)}"
    )
    raw = llm_json(
        client=client,
        model=model,
        agent_name="classifier_agent",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tracker=tracker,
        max_tokens=4000,
    )
    return raw


def build_category_buckets(
    flat_items: list[dict[str, Any]], classified: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_id = {item["item_id"]: item for item in flat_items}
    valid_names = {c["name"] for c in CATEGORY_AGENTS}

    buckets: dict[str, Any] = {
        c["name"]: {
            "key": c["key"],
            "name": c["name"],
            "items": [],
        }
        for c in CATEGORY_AGENTS
    }
    assignments: list[dict[str, Any]] = []

    for row in classified.get("results", []):
        item_id = str(row.get("item_id", "")).strip()
        if item_id not in by_id:
            continue
        category = str(row.get("category", "其他热点")).strip()
        if category not in valid_names:
            category = "其他热点"

        item = by_id[item_id]
        wrapped = {
            "item_id": item["item_id"],
            "platform_id": item["platform_id"],
            "platform_name": item["platform_name"],
            "rank": item["rank"],
            "title": item["title"],
            "url": item["url"],
            "reason": str(row.get("reason", "")).strip(),
            "confidence": float(row.get("confidence", 0) or 0),
        }
        buckets[category]["items"].append(wrapped)
        assignments.append(
            {
                "item_id": item_id,
                "category": category,
                "reason": wrapped["reason"],
                "confidence": wrapped["confidence"],
            }
        )

    assigned_ids = {a["item_id"] for a in assignments}
    for item in flat_items:
        if item["item_id"] in assigned_ids:
            continue
        wrapped = {
            "item_id": item["item_id"],
            "platform_id": item["platform_id"],
            "platform_name": item["platform_name"],
            "rank": item["rank"],
            "title": item["title"],
            "url": item["url"],
            "reason": "分类模型未返回，自动归入其他",
            "confidence": 0.0,
        }
        buckets["其他热点"]["items"].append(wrapped)
        assignments.append(
            {
                "item_id": item["item_id"],
                "category": "其他热点",
                "reason": wrapped["reason"],
                "confidence": 0.0,
            }
        )

    for name in buckets:
        buckets[name]["items"].sort(key=lambda x: (x["platform_id"], x["rank"]))
    assignments.sort(key=lambda x: x["item_id"])
    return buckets, assignments


def generate_master_pack(
    client: OpenAI,
    model: str,
    flat_items: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    tracker: dict[str, Any],
    style_profile: dict[str, Any],
) -> dict[str, Any]:
    category_by_id = {item["item_id"]: item["category"] for item in assignments}
    classified_items = []
    for item in flat_items:
        classified_items.append(
            {
                **item,
                "category": category_by_id.get(item["item_id"], "其他热点"),
            }
        )

    system_prompt = (
        "你是总控运营策略Agent，也是一个非常懂平台传播机制的内容总编。"
        "你的任务不是写全网综述，而是从热点里挑出最值得打的3条。"
        "然后针对微博、B站、抖音、小红书分别写出完全不同的版本。"
        "必须遵守这些规则："
        + "；".join(VIRAL_FRAMEWORK)
        + "；微博要短促尖锐；B站要有观点和展开；抖音要有口播感和节奏；小红书要有情绪和代入感。"
        + "；写作时还必须严格遵守给定的风格画像。"
        + "。必须返回严格JSON。"
    )
    user_prompt = (
        f"风格画像：\n{format_style_profile(style_profile)}\n\n"
        "请输出：\n"
        "1) 一份300-500字研报，只解释为什么这3条值得打\n"
        "2) 从输入热点里选出3条最适合传播的新闻\n"
        "3) 对每条新闻分别输出微博、B站、抖音、小红书版本\n"
        "4) 每个平台都要按平台语言风格重写，不能只是同一段换标题\n\n"
        "输出JSON Schema:\n"
        "{\n"
        '  "research_report_md": "markdown文本",\n'
        '  "global_observation": ["观察1","观察2","观察3"],\n'
        '  "selected_news": [\n'
        "    {\n"
        '      "item_id": "item_1",\n'
        '      "title": "原热点标题",\n'
        '      "platform_name": "微博",\n'
        '      "category": "国际政治",\n'
        '      "selection_reason": "为什么值得打",\n'
        '      "core_angle": "推荐切入角度",\n'
        '      "debate_point": "争议点/站队点",\n'
        '      "platform_versions": {\n'
        '        "weibo": {\n'
        '          "title": "微博标题",\n'
        '          "content": "微博正文，80-180字",\n'
        '          "hashtags": ["标签1","标签2"]\n'
        "        },\n"
        '        "bilibili": {\n'
        '          "title": "B站标题",\n'
        '          "intro": "B站导语，80-150字",\n'
        '          "content": "B站长一点的稿子，300-600字",\n'
        '          "hashtags": ["标签1","标签2"]\n'
        "        },\n"
        '        "douyin": {\n'
        '          "title": "抖音标题",\n'
        '          "hook": "15秒开场钩子",\n'
        '          "script": "抖音口播稿，180-320字",\n'
        '          "caption": "抖音文案，50-100字",\n'
        '          "hashtags": ["标签1","标签2"]\n'
        "        },\n"
        '        "xiaohongshu": {\n'
        '          "title": "小红书标题",\n'
        '          "content": "小红书正文，250-500字",\n'
        '          "hashtags": ["标签1","标签2"]\n'
        "        }\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "选择原则：\n"
        "1) 优先冲突强、情绪强、立场强的新闻\n"
        "2) 3条尽量不要完全同质，可覆盖不同类型话题\n"
        "3) 禁止泛泛而谈，必须让每个平台版本看起来像原生内容\n"
        "4) 风格画像优先级高于默认写法，尤其体现在标题、开头、判断句和节奏上\n\n"
        f"热点列表:\n{json.dumps(classified_items, ensure_ascii=False)}"
    )
    data = llm_json(
        client=client,
        model=model,
        agent_name="strategy_agent",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tracker=tracker,
        max_tokens=7000,
    )
    return data


def build_publish_text(title: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{t.strip().lstrip('#')}" for t in hashtags if t.strip())
    return f"{title}\n{tags}\n"


def summarize_token_usage(tracker: dict[str, Any]) -> dict[str, Any]:
    total_prompt = sum(x["prompt_tokens"] for x in tracker["calls"])
    total_completion = sum(x["completion_tokens"] for x in tracker["calls"])
    total = sum(x["total_tokens"] for x in tracker["calls"])

    by_agent: dict[str, dict[str, int]] = {}
    for call in tracker["calls"]:
        agent = call["agent"]
        if agent not in by_agent:
            by_agent[agent] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        by_agent[agent]["prompt_tokens"] += call["prompt_tokens"]
        by_agent[agent]["completion_tokens"] += call["completion_tokens"]
        by_agent[agent]["total_tokens"] += call["total_tokens"]

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total,
        "by_agent": by_agent,
        "calls": tracker["calls"],
    }


def write_outputs(
    hotspots: dict[str, Any],
    category_buckets: dict[str, Any],
    assignments: list[dict[str, Any]],
    master_pack: dict[str, Any],
    token_usage: dict[str, Any],
    model: str,
    base_url: str,
    style_profile: dict[str, Any],
) -> Path:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / now
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "hotspots.json").write_text(
        json.dumps(hotspots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "category_classification.json").write_text(
        json.dumps(
            {
                "assignments": assignments,
                "buckets": category_buckets,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "generated.json").write_text(
        json.dumps(
            {
                "master_pack": master_pack,
                "_llm_model": model,
                "_llm_base_url": base_url,
                "_style_profile": style_profile,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "token_usage.json").write_text(
        json.dumps(token_usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (out_dir / "research_report.md").write_text(
        str(master_pack.get("research_report_md", "")), encoding="utf-8"
    )
    selected_news = master_pack.get("selected_news", []) or []
    observation = master_pack.get("global_observation", []) or []
    combined_md = ["# 三条热点平台改写包", "", "## 总体判断"]
    combined_md.extend([f"- {x}" for x in observation])
    news_dir = out_dir / "news_packs"
    news_dir.mkdir(parents=True, exist_ok=True)
    first_caption_title = "今日热点速览"
    first_caption_tags: list[str] = []

    for index, news in enumerate(selected_news, start=1):
        news_title = str(news.get("title", ""))
        platform_name = str(news.get("platform_name", ""))
        category = str(news.get("category", ""))
        reason = str(news.get("selection_reason", ""))
        core_angle = str(news.get("core_angle", ""))
        debate_point = str(news.get("debate_point", ""))
        versions = news.get("platform_versions", {}) or {}

        safe_name = f"news_{index}"
        if index == 1:
            bili = versions.get("bilibili", {}) or {}
            first_caption_title = str(bili.get("title", "")) or news_title or first_caption_title
            first_caption_tags = bili.get("hashtags", []) or []

        lines = [
            f"# 热点 {index}",
            "",
            f"## 原始热点",
            news_title,
            "",
            f"## 来源平台",
            platform_name,
            "",
            f"## 分类",
            category,
            "",
            f"## 入选理由",
            reason,
            "",
            f"## 推荐切入角度",
            core_angle,
            "",
            f"## 争议点",
            debate_point,
        ]

        for platform_key, platform_label in [
            ("weibo", "微博"),
            ("bilibili", "B站"),
            ("douyin", "抖音"),
            ("xiaohongshu", "小红书"),
        ]:
            data = versions.get(platform_key, {}) or {}
            lines.extend(
                [
                    "",
                    f"## {platform_label}",
                    f"### 标题",
                    str(data.get("title", "")),
                ]
            )
            if platform_key == "douyin":
                lines.extend(
                    [
                        "",
                        "### 开场钩子",
                        str(data.get("hook", "")),
                        "",
                        "### 口播稿",
                        str(data.get("script", "")),
                        "",
                        "### 配文",
                        str(data.get("caption", "")),
                    ]
                )
            elif platform_key == "bilibili":
                lines.extend(
                    [
                        "",
                        "### 导语",
                        str(data.get("intro", "")),
                        "",
                        "### 正文",
                        str(data.get("content", "")),
                    ]
                )
            else:
                lines.extend(
                    [
                        "",
                        "### 正文",
                        str(data.get("content", "")),
                    ]
                )
            lines.extend(["", "### 标签"])
            lines.extend([f"- #{x}" for x in (data.get("hashtags", []) or [])])

        file_path = news_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")

        combined_md.extend(
            [
                "",
                f"## 热点 {index}",
                f"- 原始标题：{news_title}",
                f"- 来源平台：{platform_name}",
                f"- 分类：{category}",
                f"- 入选理由：{reason}",
                f"- 切入角度：{core_angle}",
                f"- 争议点：{debate_point}",
            ]
        )

    (out_dir / "article.md").write_text("\n".join(combined_md), encoding="utf-8")

    publish_md = ["# 发布素材包", "", "## 本轮选题"]
    for index, news in enumerate(selected_news, start=1):
        publish_md.extend(
            [
                f"- 热点{index}：{news.get('title', '')}",
                f"  入选理由：{news.get('selection_reason', '')}",
                f"  切入角度：{news.get('core_angle', '')}",
                f"  争议点：{news.get('debate_point', '')}",
            ]
        )
    (out_dir / "publish_pack.md").write_text("\n".join(publish_md), encoding="utf-8")

    (out_dir / "social_caption.txt").write_text(
        build_publish_text(first_caption_title, first_caption_tags),
        encoding="utf-8",
    )

    history_file = OUTPUT_ROOT / "token_usage_history.jsonl"
    summary_row = {
        "run_ts": now,
        "output_dir": str(out_dir),
        "total_tokens": token_usage["total_tokens"],
        "prompt_tokens": token_usage["total_prompt_tokens"],
        "completion_tokens": token_usage["total_completion_tokens"],
        "model": model,
    }
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary_row, ensure_ascii=False) + "\n")

    return out_dir


def do_publish(
    out_dir: Path,
    publish_platform: str,
    account_name: str,
    video_file: Path,
    bilibili_account_file: str = "",
) -> None:
    if not video_file.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_file}")

    caption = (out_dir / "social_caption.txt").read_text(encoding="utf-8")
    sidecar = video_file.with_suffix(".txt")
    sidecar.write_text(caption, encoding="utf-8")

    if publish_platform == "bilibili":
        cmd = [
            "bash",
            "scripts/run_bilibili_browser_publish.sh",
            "--video-file",
            str(video_file),
        ]
        if bilibili_account_file:
            cmd.extend(["--account-file", bilibili_account_file])
        run_cmd(cmd, cwd=ROOT_DIR)
        return

    cmd = [
        "bash",
        "scripts/run_social.sh",
        "cli",
        publish_platform,
        account_name,
        "upload",
        str(video_file),
    ]
    run_cmd(cmd, cwd=ROOT_DIR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GhostMedia 热点多Agent链路：抓取->分类->选3条热点->4平台改写->发布"
    )
    parser.add_argument("--skip-trend", action="store_true", help="跳过热点抓取，直接使用最新数据库")
    parser.add_argument("--top-k-per-platform", type=int, default=8, help="每个平台提取的热点条数")
    parser.add_argument(
        "--style-profile",
        default="maoshenstyle",
        help="内容风格画像，如 maoshenstyle",
    )
    parser.add_argument(
        "--focus-platforms",
        default="",
        help="仅分析指定平台ID，逗号分隔，如 weibo,douyin,zhihu",
    )
    parser.add_argument("--publish", action="store_true", help="启用一键发布（需要提供平台、账号、视频）")
    parser.add_argument("--publish-platform", default="", help="发布平台，如 douyin/tencent/tiktok/kuaishou/bilibili")
    parser.add_argument("--account-name", default="", help="账号名，对应 social cookie 文件名")
    parser.add_argument("--video-file", default="", help="待发布视频路径（.mp4）")
    parser.add_argument(
        "--bilibili-account-file",
        default="",
        help="B站账号cookie文件路径（不填则默认 social-auto-upload/cookies/bilibili_uploader/account.json）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = parse_env_file(ROOT_DIR / ".env")
    focus_platforms = [x.strip() for x in args.focus_platforms.split(",") if x.strip()]
    style_profile = get_style_profile(args.style_profile)

    if not args.skip_trend:
        print("[1/6] 开始抓取热点...")
        run_trend_once()
    else:
        print("[1/6] 跳过抓取，使用最新热点数据库...")

    print("[2/6] 提取热点数据...")
    db_path = latest_news_db()
    hotspots = fetch_hotspots(db_path, args.top_k_per_platform, focus_platforms)
    flat_items = flatten_hotspots(hotspots)
    if not flat_items:
        raise RuntimeError("未提取到热点数据，请检查平台配置")

    client, model, normalized_base_url = build_client(env)
    token_tracker: dict[str, Any] = {"calls": []}

    print("[3/6] 分类Agent：热点分类...")
    classified = classify_hotspots(client, model, flat_items, token_tracker)
    category_buckets, assignments = build_category_buckets(flat_items, classified)

    print("[4/6] 策略Agent：选3条热点并做平台改写...")
    master_pack = generate_master_pack(
        client,
        model,
        flat_items,
        assignments,
        token_tracker,
        style_profile,
    )

    print("[5/6] 写入三条热点的平台内容包...")

    token_usage = summarize_token_usage(token_tracker)
    out_dir = write_outputs(
        hotspots=hotspots,
        category_buckets=category_buckets,
        assignments=assignments,
        master_pack=master_pack,
        token_usage=token_usage,
        model=model,
        base_url=normalized_base_url,
        style_profile=style_profile,
    )
    print(f"输出目录: {out_dir}")
    print(
        "Token统计: "
        f"prompt={token_usage['total_prompt_tokens']}, "
        f"completion={token_usage['total_completion_tokens']}, "
        f"total={token_usage['total_tokens']}"
    )

    if args.publish:
        print("[6/6] 执行一键发布...")
        if not args.publish_platform or not args.video_file:
            raise RuntimeError("--publish 至少需要 --publish-platform 和 --video-file")
        if args.publish_platform != "bilibili" and not args.account_name:
            raise RuntimeError("非 bilibili 发布需提供 --account-name")
        do_publish(
            out_dir=out_dir,
            publish_platform=args.publish_platform,
            account_name=args.account_name,
            video_file=Path(args.video_file).expanduser().resolve(),
            bilibili_account_file=args.bilibili_account_file,
        )
        print("发布完成。")
    else:
        print("[6/6] 跳过发布（未启用 --publish）。")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"执行失败: {exc}")
        raise SystemExit(1)
