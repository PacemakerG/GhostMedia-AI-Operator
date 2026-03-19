#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT_DIR / "orchestrator" / "output"
DEFAULT_CONTENT_API = "http://127.0.0.1:8080/api/v1/videos"
ENV_FILE = ROOT_DIR / ".env"

FACELESS_PRESET = {
    "template_name": "facelessnews_v1",
    "description": "无脸热点快评模板：3秒钩子开场 + 下一句补新闻信息 + B-roll + 大字幕 + 结尾提问。",
    "platform": "douyin",
    "video_aspect": "9:16",
    "video_source": "pexels",
    "video_clip_duration": 4,
    "video_count": 1,
    "voice_name": "zh-CN-XiaoxiaoNeural-Female",
    "voice_rate": 1.12,
    "voice_volume": 1.0,
    "voice_style": "",
    "voice_style_degree": 1.0,
    "voice_role": "",
    "subtitle_enabled": True,
    "subtitle_position": "center",
    "font_name": "STHeitiMedium.ttc",
    "font_size": 62,
    "text_fore_color": "#FFFFFF",
    "text_background_color": True,
    "stroke_color": "#000000",
    "stroke_width": 1.8,
    "bgm_type": "random",
    "bgm_volume": 0.12,
    "n_threads": 2,
}

AZURE_XIAOXIAO_PRESET = {
    "voice_name": "zh-CN-XiaoxiaoMultilingualNeural-V2-Female",
    "voice_rate": 1.08,
    "voice_volume": 1.0,
    "voice_style": "cheerful",
    "voice_style_degree": 1.35,
    "voice_role": "",
}

BORING_OPENING_PATTERNS = [
    r"^(据报道|据悉|消息显示|新闻显示|今天有一条|今天有个|今天一条|近日|最近|刚刚|目前|有一条关于)",
    r"^.{0,6}(新闻|报道称|通报称)",
]


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        env[key.strip()] = value
    return env


def resolve_voice_preset() -> dict[str, Any]:
    env = parse_env_file(ENV_FILE)
    has_azure = bool(
        env.get("CONTENT_AZURE_SPEECH_KEY", "").strip() or env.get("GM_AZURE_SPEECH_KEY", "").strip()
    ) and bool(
        env.get("CONTENT_AZURE_SPEECH_REGION", "").strip()
        or env.get("GM_AZURE_SPEECH_REGION", "").strip()
    )
    preset = dict(FACELESS_PRESET)
    if has_azure:
        preset.update(AZURE_XIAOXIAO_PRESET)
    return preset


def latest_output_dir() -> Path:
    candidates = [
        path
        for path in OUTPUT_ROOT.iterdir()
        if path.is_dir() and (path / "generated.json").exists()
    ]
    if not candidates:
        raise FileNotFoundError("未找到可用的 orchestrator 输出目录")
    candidates.sort(key=lambda p: p.name, reverse=True)
    return candidates[0]


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in clean_text(text).split("\n") if part.strip()]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", clean_text(text))
    return [part.strip() for part in parts if part.strip()]


def short_text(text: str, limit: int) -> str:
    text = clean_text(text).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pick_question(text: str) -> str:
    for sentence in reversed(split_sentences(text)):
        if "？" in sentence or "?" in sentence:
            return sentence
    sentences = split_sentences(text)
    return sentences[-1] if sentences else ""


def sanitize_news_opening(text: str) -> str:
    cleaned = clean_text(text)
    for pattern in BORING_OPENING_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned).strip(" ，。,:：")
    return cleaned


def build_hook_line(news: dict[str, Any], platform_version: dict[str, Any]) -> str:
    raw_hook = sanitize_news_opening(str(platform_version.get("hook", "")))
    title = clean_text(str(news.get("title", ""))).strip("。")
    debate = clean_text(str(news.get("debate_point", ""))).strip("。")
    core_angle = clean_text(str(news.get("core_angle", ""))).strip("。")

    if raw_hook and len(raw_hook) >= 8:
        return short_text(raw_hook, 34)
    if core_angle:
        return short_text(f"这事最扎人的地方，不是热闹，是{core_angle}", 34)
    if debate:
        return short_text(f"这事吵起来，不只是因为新闻本身，而是因为{debate}", 34)
    if title:
        return short_text(f"这事一出来，很多人第一反应都是：{title}", 34)
    return "这事一出，评论区很难不吵起来。"


def build_intro_line(news: dict[str, Any], platform_version: dict[str, Any], hook_line: str) -> str:
    title = clean_text(str(news.get("title", ""))).strip("。")
    if title and title not in hook_line:
        return short_text(f"事情是这样，{title}。", 42)

    script_paragraphs = split_paragraphs(str(platform_version.get("script", "")))
    for paragraph in script_paragraphs:
        sentence = sanitize_news_opening(paragraph).strip()
        if not sentence:
            continue
        if sentence == hook_line:
            continue
        return short_text(sentence, 42)

    if title:
        return short_text(f"事情是这样，{title}。", 42)
    return "先把事情本身讲清楚。"


def build_body_paragraphs(platform_version: dict[str, Any], hook_line: str, intro_line: str) -> list[str]:
    paragraphs = split_paragraphs(str(platform_version.get("script", "")))
    filtered: list[str] = []
    seen = {clean_text(hook_line), clean_text(intro_line)}
    for paragraph in paragraphs:
        normalized = clean_text(sanitize_news_opening(paragraph))
        if not normalized or normalized in seen:
            continue
        filtered.append(normalized)
    return filtered


def build_search_terms(news: dict[str, Any], platform_version: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    category = str(news.get("category", "")).strip()
    title = str(news.get("title", "")).strip()
    if category and category not in {"其他热点", "other"}:
        terms.append(category)
    if title:
        terms.append(title)
    for tag in platform_version.get("hashtags", []) or []:
        clean_tag = str(tag).strip().lstrip("#")
        if clean_tag:
            terms.append(clean_tag)

    for field_name in ["core_angle", "debate_point"]:
        raw = str(news.get(field_name, "")).strip()
        if not raw:
            continue
        clauses = re.split(r"[，,。；：:]", raw)
        for clause in clauses:
            clause = clause.strip(" “”—-？?！!、")
            if 4 <= len(clause) <= 18:
                terms.append(clause)

    seen: set[str] = set()
    unique_terms: list[str] = []
    for term in terms:
        if len(term) > 24:
            continue
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms[:6]


def build_segments(news: dict[str, Any], platform_version: dict[str, Any]) -> list[dict[str, Any]]:
    hook_line = build_hook_line(news, platform_version)
    intro_line = build_intro_line(news, platform_version, hook_line)
    paragraphs = build_body_paragraphs(platform_version, hook_line, intro_line)
    voice_script = build_voice_script(news, platform_version)
    ending_question = pick_question(voice_script)
    debate = str(news.get("debate_point", "")).strip()
    core_angle = str(news.get("core_angle", "")).strip()
    title = str(platform_version.get("title", news.get("title", ""))).strip()
    source_title = str(news.get("title", "")).strip()
    search_terms = build_search_terms(news, platform_version)

    segments: list[dict[str, Any]] = [
        {
            "start_sec": 0,
            "end_sec": 3,
            "visual": "黑底大字 + 高频关键词闪现",
            "onscreen_text": short_text(title, 22),
            "narration": short_text(hook_line, 40),
        },
        {
            "start_sec": 3,
            "end_sec": 8,
            "visual": "热点原始标题卡 + 来源平台字卡",
            "onscreen_text": short_text(source_title, 28),
            "narration": short_text(intro_line, 80),
        },
        {
            "start_sec": 8,
            "end_sec": 16,
            "visual": f"B-roll 搜索词：{', '.join(search_terms[:3])}",
            "onscreen_text": short_text(core_angle or "真正重点不是表面新闻，而是背后的输赢关系", 28),
            "narration": short_text(paragraphs[0] if paragraphs else (core_angle or intro_line), 120),
        },
        {
            "start_sec": 16,
            "end_sec": 26,
            "visual": "评论截图感字幕条 + 关键词放大",
            "onscreen_text": short_text(debate or "这事真正能打起来的点，在于立场和代价", 28),
            "narration": short_text(paragraphs[1] if len(paragraphs) > 1 else debate or core_angle, 120),
        },
        {
            "start_sec": 26,
            "end_sec": 35,
            "visual": "结尾提问卡 + 引导评论区站队",
            "onscreen_text": short_text(ending_question or "你站哪边？", 24),
            "narration": short_text(ending_question or debate or "你怎么看？", 50),
        },
    ]
    return segments


def build_voice_script(news: dict[str, Any], platform_version: dict[str, Any]) -> str:
    hook_line = build_hook_line(news, platform_version)
    intro_line = build_intro_line(news, platform_version, hook_line)
    body_paragraphs = build_body_paragraphs(platform_version, hook_line, intro_line)
    parts = [part for part in [hook_line, intro_line, *body_paragraphs] if part]
    return "\n\n".join(parts)


def build_faceless_brief(
    news: dict[str, Any],
    platform: str,
    news_index: int,
    source_run_dir: Path,
) -> dict[str, Any]:
    versions = news.get("platform_versions", {}) or {}
    platform_version = versions.get(platform, {}) or {}
    if not platform_version:
        raise RuntimeError(f"热点 {news_index} 缺少平台版本: {platform}")

    voice_script = build_voice_script(news, platform_version)
    ending_question = pick_question(voice_script)
    cover_title = str(platform_version.get("title", news.get("title", ""))).strip()
    search_terms = build_search_terms(news, platform_version)
    segments = build_segments(news, platform_version)

    return {
        "news_index": news_index,
        "source_run_dir": str(source_run_dir),
        "template_name": FACELESS_PRESET["template_name"],
        "platform": platform,
        "topic_title": str(news.get("title", "")),
        "category": str(news.get("category", "")),
        "selection_reason": str(news.get("selection_reason", "")),
        "core_angle": str(news.get("core_angle", "")),
        "debate_point": str(news.get("debate_point", "")),
        "cover_title": cover_title,
        "hook": build_hook_line(news, platform_version),
        "voice_script": voice_script,
        "ending_question": ending_question,
        "caption": str(platform_version.get("caption") or platform_version.get("content") or ""),
        "hashtags": platform_version.get("hashtags", []) or [],
        "visual_search_terms": search_terms,
        "segments": segments,
        "render_preset": FACELESS_PRESET,
    }


def build_task_request(brief: dict[str, Any], video_source: str) -> dict[str, Any]:
    voice_preset = resolve_voice_preset()
    request = {
        "video_subject": brief["cover_title"],
        "video_script": brief["voice_script"],
        "video_terms": brief["visual_search_terms"],
        "video_aspect": FACELESS_PRESET["video_aspect"],
        "video_clip_duration": FACELESS_PRESET["video_clip_duration"],
        "video_count": FACELESS_PRESET["video_count"],
        "video_source": video_source,
        "voice_name": voice_preset["voice_name"],
        "voice_rate": voice_preset["voice_rate"],
        "voice_volume": voice_preset["voice_volume"],
        "voice_style": voice_preset["voice_style"],
        "voice_style_degree": voice_preset["voice_style_degree"],
        "voice_role": voice_preset["voice_role"],
        "bgm_type": FACELESS_PRESET["bgm_type"],
        "bgm_volume": FACELESS_PRESET["bgm_volume"],
        "subtitle_enabled": FACELESS_PRESET["subtitle_enabled"],
        "subtitle_position": FACELESS_PRESET["subtitle_position"],
        "font_name": FACELESS_PRESET["font_name"],
        "font_size": FACELESS_PRESET["font_size"],
        "text_fore_color": FACELESS_PRESET["text_fore_color"],
        "text_background_color": FACELESS_PRESET["text_background_color"],
        "stroke_color": FACELESS_PRESET["stroke_color"],
        "stroke_width": FACELESS_PRESET["stroke_width"],
        "n_threads": FACELESS_PRESET["n_threads"],
    }
    return request


def write_render_script(out_dir: Path, task_request_path: Path, api_url: str) -> None:
    script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        f'API_URL="${{CONTENT_API_URL:-{api_url}}}"\n'
        'curl -sS -X POST "$API_URL" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        f'  --data "@{task_request_path.name}"\n'
    )
    path = out_dir / "render_content_api.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def submit_task(api_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate_faceless_news(
    source_dir: Path,
    platform: str,
    video_source: str,
    submit: bool,
    api_url: str,
) -> Path:
    generated = json.loads((source_dir / "generated.json").read_text(encoding="utf-8"))
    selected_news = generated.get("master_pack", {}).get("selected_news", []) or []
    if not selected_news:
        raise RuntimeError("generated.json 中没有 selected_news")

    out_dir = source_dir / "faceless_news"
    out_dir.mkdir(parents=True, exist_ok=True)

    overview_lines = [
        "# FacelessNews 产物",
        "",
        f"- 来源目录：{source_dir}",
        f"- 生成时间：{datetime.now().isoformat()}",
        f"- 模板：{FACELESS_PRESET['template_name']}",
        f"- 平台版本来源：{platform}",
        f"- 视频素材源：{video_source}",
        "",
        "## 产物说明",
        "- `brief.json`：短视频脚本、分镜和包装信息",
        "- `task_request.json`：可直接提交给 content-vedio-agent 的请求体",
        "- `render_content_api.sh`：一键提交当前任务到视频服务",
        "",
        "## 热点列表",
    ]

    for index, news in enumerate(selected_news, start=1):
        news_dir = out_dir / f"news_{index}"
        news_dir.mkdir(parents=True, exist_ok=True)

        brief = build_faceless_brief(news, platform=platform, news_index=index, source_run_dir=source_dir)
        task_request = build_task_request(brief, video_source=video_source)

        (news_dir / "brief.json").write_text(
            json.dumps(brief, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (news_dir / "task_request.json").write_text(
            json.dumps(task_request, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (news_dir / "script.txt").write_text(brief["voice_script"], encoding="utf-8")
        (news_dir / "caption.txt").write_text(
            f"{brief['cover_title']}\n{brief['caption']}\n"
            + " ".join(f"#{tag}" for tag in brief["hashtags"]),
            encoding="utf-8",
        )
        write_render_script(news_dir, news_dir / "task_request.json", api_url)

        submit_result: dict[str, Any] | None = None
        if submit:
            submit_result = submit_task(api_url, task_request)
            (news_dir / "submit_result.json").write_text(
                json.dumps(submit_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        overview_lines.extend(
            [
                f"- 热点{index}：{brief['topic_title']}",
                f"  封面标题：{brief['cover_title']}",
                f"  关键词：{', '.join(brief['visual_search_terms'])}",
            ]
        )
        if submit_result:
            overview_lines.append(f"  已提交任务：{json.dumps(submit_result, ensure_ascii=False)}")

    (out_dir / "README.md").write_text("\n".join(overview_lines), encoding="utf-8")
    return out_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从热点文案生成 FacelessNews 视频素材包")
    parser.add_argument(
        "--source-dir",
        default="",
        help="指定 orchestrator 输出目录；不填则自动读取最新一轮",
    )
    parser.add_argument(
        "--platform",
        default="douyin",
        help="使用哪一套平台文案作为 faceless 视频底稿，默认 douyin",
    )
    parser.add_argument(
        "--video-source",
        default=FACELESS_PRESET["video_source"],
        help="传给 content-vedio-agent 的视频素材源，默认 pexels",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="生成后直接提交给 content-vedio-agent API",
    )
    parser.add_argument(
        "--content-api-url",
        default=DEFAULT_CONTENT_API,
        help=f"视频服务接口地址，默认 {DEFAULT_CONTENT_API}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve() if args.source_dir else latest_output_dir()
    if not (source_dir / "generated.json").exists():
        raise FileNotFoundError(f"目录中缺少 generated.json: {source_dir}")

    out_dir = generate_faceless_news(
        source_dir=source_dir,
        platform=args.platform,
        video_source=args.video_source,
        submit=args.submit,
        api_url=args.content_api_url,
    )
    print(f"FacelessNews 输出目录: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
