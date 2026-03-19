from __future__ import annotations

from typing import Any


STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "maoshenstyle": {
        "key": "maoshenstyle",
        "name": "猫神风格",
        "summary": "基于公开可访问样本归纳的强判断评论风格：先表态、再拆矛盾、语言短促、允许讽刺，标题像判词而不是摘要。",
        "voice_traits": [
            "第一句先落判断，不先讲背景",
            "句子尽量短，像在当面下结论",
            "允许嘲讽、反问、点名荒诞感，但不能失真",
            "核心不是介绍新闻，而是指出谁在装、谁在输、谁最尴尬",
        ],
        "title_rules": [
            "标题像判词、吐槽、揭穿，而不是“某某事件最新进展”",
            "优先使用价值判断和冲突结论，例如“真正难看的不是X，是Y”",
            "能写出输赢关系，就不要只写事件名",
        ],
        "opening_rules": [
            "第一句必须有态度，可以直接下结论",
            "第二句接矛盾点或反差点，不要铺背景",
            "如果能一针见血，就不要委婉过渡",
        ],
        "platform_rules": {
            "weibo": "像一条带刺的短评，适合引战但不越线，结尾最好留一个能让评论区站队的问题。",
            "bilibili": "保持犀利，但要把逻辑讲透，像在做一段有立场的时评视频文案。",
            "douyin": "像镜头前的直给口播，前3秒就要挑明最刺痛的点。",
            "xiaohongshu": "保留判断感，但用“我最烦这种”“这事最离谱的是”这类更生活化表达增强代入。",
        },
        "forbidden": [
            "不要写得四平八稳",
            "不要用大量套话稀释观点",
            "不要把风格理解成纯骂街，必须有判断依据",
        ],
        "source_notes": [
            "风格特征来自公开可访问样本与镜像页面的归纳，不是逐条复刻原文。",
            "参考来源包括 24vids 频道页、Twstalker 镜像页及公开转载文章。",
        ],
    },
}


def get_style_profile(name: str) -> dict[str, Any]:
    key = (name or "maoshenstyle").strip().lower()
    return STYLE_PROFILES.get(key, STYLE_PROFILES["maoshenstyle"])


def format_style_profile(profile: dict[str, Any]) -> str:
    platform_rules = profile.get("platform_rules", {}) or {}
    lines = [
        f"当前写作风格：{profile.get('name', '默认风格')}",
        f"风格摘要：{profile.get('summary', '')}",
        "表达特征：",
    ]
    lines.extend([f"- {item}" for item in profile.get("voice_traits", [])])
    lines.append("标题规则：")
    lines.extend([f"- {item}" for item in profile.get("title_rules", [])])
    lines.append("开头规则：")
    lines.extend([f"- {item}" for item in profile.get("opening_rules", [])])
    lines.append("平台差异：")
    for platform, rule in platform_rules.items():
        lines.append(f"- {platform}: {rule}")
    lines.append("禁止事项：")
    lines.extend([f"- {item}" for item in profile.get("forbidden", [])])
    return "\n".join(lines)
