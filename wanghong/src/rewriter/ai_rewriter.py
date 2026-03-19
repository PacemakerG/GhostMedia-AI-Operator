# AI 文案改写器
# 使用 AI 对 X 平台抓取的内容进行改写和优化

import logging
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class RewriteResult:
    """改写结果"""

    original_text: str
    rewritten_text: str
    style: str
    hashtags: List[str]
    emoji_suggestions: List[str]
    engagement_score: float  # 预估互动分数 0-100
    warnings: List[str]  # 风险提示（如违规词）


class AIContentRewriter:
    """AI 内容改写器"""

    # 预设改写风格
    STYLES = {
        "humorous": {
            "name": "幽默风趣",
            "description": "轻松搞笑、玩梗、接地气",
            "prompt_suffix": "用幽默风趣的语气改写，可以玩一些网络梗，让人看了会心一笑。",
        },
        "professional": {
            "name": "专业严谨",
            "description": "专业术语、逻辑清晰、权威感",
            "prompt_suffix": "用专业严谨的语气改写，使用恰当的术语，逻辑清晰，给人专业可靠的感觉。",
        },
        "emotional": {
            "name": "情感共鸣",
            "description": "走心、有温度、引发共鸣",
            "prompt_suffix": "用情感化的语气改写，真诚走心，能引发读者情感共鸣，有温度有感染力。",
        },
        "concise": {
            "name": "简洁直白",
            "description": "短句、直接、不绕弯",
            "prompt_suffix": "用简洁直白的语气改写，短句直接，不绕弯子，让人一眼就能看懂。",
        },
        "storytelling": {
            "name": "故事叙述",
            "description": "有情节、有画面感",
            "prompt_suffix": "用讲故事的方式改写，有情节推进，有画面感，让读者仿佛身临其境。",
        },
    }

    def __init__(self, config: Dict, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # AI 配置
        self.ai_config = config.get("ai_config", {})
        self.model = self.ai_config.get("model", "gpt-4")
        self.api_key = self.ai_config.get("api_key")
        self.api_base = self.ai_config.get("api_base")

        # 内容限制
        self.max_length = config.get("max_length", 500)
        self.min_length = config.get("min_length", 50)

        # 敏感词过滤
        self.sensitive_words = config.get("sensitive_words", [])

        self.logger.info(f"AI改写器初始化完成，模型: {self.model}")

    async def rewrite(
        self, content: str, style: str = "humorous", context: Optional[Dict] = None
    ) -> RewriteResult:
        """改写单条内容

        Args:
            content: 原始内容
            style: 改写风格（humorous/professional/emotional/concise/storytelling）
            context: 上下文信息（如原帖互动数据、话题标签等）

        Returns:
            RewriteResult: 改写结果
        """
        self.logger.info(f"开始改写内容，风格: {style}")

        # 检查内容长度
        if len(content) < self.min_length:
            return self._create_error_result(content, "内容过短")

        if len(content) > self.max_length * 2:
            content = content[: self.max_length * 2] + "..."

        # 获取风格配置
        style_config = self.STYLES.get(style, self.STYLES["humorous"])

        # 构建提示词
        prompt = self._build_prompt(content, style_config, context)

        try:
            # 调用 AI 进行改写
            rewritten = await self._call_ai(prompt)

            # 后处理
            rewritten = self._post_process(rewritten)

            # 提取标签和表情建议
            hashtags = self._extract_hashtags(rewritten, context)
            emojis = self._suggest_emojis(rewritten, style)

            # 预估互动分数
            engagement_score = self._calculate_engagement_score(
                rewritten, style, context
            )

            # 检查敏感词
            warnings = self._check_sensitive_words(rewritten)

            result = RewriteResult(
                original_text=content,
                rewritten_text=rewritten,
                style=style_config["name"],
                hashtags=hashtags,
                emoji_suggestions=emojis,
                engagement_score=engagement_score,
                warnings=warnings,
            )

            self.logger.info(f"改写完成，预估互动分: {engagement_score}")
            return result

        except Exception as e:
            self.logger.error(f"改写失败: {e}")
            return self._create_error_result(content, str(e))

    async def rewrite_batch(
        self,
        contents: List[str],
        style: str = "humorous",
        context_list: Optional[List[Dict]] = None,
    ) -> List[RewriteResult]:
        """批量改写"""
        self.logger.info(f"开始批量改写 {len(contents)} 条内容")

        tasks = []
        for i, content in enumerate(contents):
            context = (
                context_list[i] if context_list and i < len(context_list) else None
            )
            tasks.append(self.rewrite(content, style, context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"第 {i + 1} 条改写异常: {result}")
                processed_results.append(
                    self._create_error_result(contents[i], str(result))
                )
            else:
                processed_results.append(result)

        return processed_results

    def _build_prompt(
        self, content: str, style_config: Dict, context: Optional[Dict]
    ) -> str:
        """构建提示词"""
        base_prompt = f"""请改写以下内容，要求：

原内容：
{content}

改写要求：
1. {style_config["prompt_suffix"]}
2. 保持原意不变
3. 字数控制在 {self.min_length} - {self.max_length} 字之间
4. 语言自然流畅，符合中文社交媒体风格
5. 可以适当添加emoji增强表达，但不要过度使用
"""

        # 添加上下文信息
        if context:
            base_prompt += "\n上下文信息：\n"
            if "likes" in context:
                base_prompt += f"- 原帖点赞数: {context['likes']}\n"
            if "retweets" in context:
                base_prompt += f"- 原帖转发数: {context['retweets']}\n"
            if "hashtags" in context:
                base_prompt += f"- 相关话题: {', '.join(context['hashtags'])}\n"

        base_prompt += "\n请直接输出改写后的内容，不要添加任何解释。"

        return base_prompt

    async def _call_ai(self, prompt: str) -> str:
        """调用 AI 模型"""
        # 这里使用 LiteLLM 或其他统一接口
        # 实际实现时需要根据配置调用不同的模型

        # 模拟调用
        await asyncio.sleep(0.5)

        # 实际实现示例（使用 LiteLLM）：
        # from litellm import acompletion
        # response = await acompletion(
        #     model=self.model,
        #     messages=[{"role": "user", "content": prompt}],
        #     api_key=self.api_key,
        #     api_base=self.api_base
        # )
        # return response.choices[0].message.content

        return f"【AI改写示例】这是改写后的内容..."

    def _post_process(self, text: str) -> str:
        """后处理改写结果"""
        # 去除多余空格
        text = " ".join(text.split())

        # 去除多余换行
        text = text.replace("\n\n\n", "\n\n")

        # 限制长度
        if len(text) > self.max_length:
            text = text[: self.max_length] + "..."

        return text.strip()

    def _extract_hashtags(self, text: str, context: Optional[Dict]) -> List[str]:
        """提取话题标签"""
        hashtags = []

        # 从原文中提取
        import re

        found = re.findall(r"#(\w+)", text)
        hashtags.extend([f"#{tag}" for tag in found])

        # 从上下文中获取
        if context and "hashtags" in context:
            for tag in context["hashtags"]:
                if tag not in hashtags:
                    hashtags.append(tag)

        # 去重并限制数量
        hashtags = list(dict.fromkeys(hashtags))[:5]

        return hashtags

    def _suggest_emojis(self, text: str, style: str) -> List[str]:
        """建议使用的 emoji"""
        emoji_map = {
            "humorous": ["😂", "🤣", "😄", "🎉", "🔥"],
            "professional": ["💼", "📊", "✅", "📈", "💡"],
            "emotional": ["❤️", "😭", "🥺", "✨", "🌟"],
            "concise": ["👉", "👍", "✨", "💯", "🚀"],
            "storytelling": ["📖", "🎬", "🌅", "🎭", "✨"],
        }

        return emoji_map.get(style, ["✨", "👍", "💯"])

    def _calculate_engagement_score(
        self, text: str, style: str, context: Optional[Dict]
    ) -> float:
        """预估互动分数"""
        score = 50.0  # 基础分

        # 长度适中加分
        if 50 <= len(text) <= 200:
            score += 15

        # 包含 emoji 加分
        if any(ord(char) > 10000 for char in text):
            score += 10

        # 包含问句加分（引发互动）
        if "?" in text or "？" in text:
            score += 10

        # 风格加成
        style_bonus = {
            "humorous": 15,
            "emotional": 12,
            "storytelling": 10,
            "concise": 8,
            "professional": 5,
        }
        score += style_bonus.get(style, 0)

        # 原帖互动数据参考
        if context:
            likes = context.get("likes", 0)
            if likes > 1000:
                score += 10
            elif likes > 100:
                score += 5

        return min(100.0, max(0.0, score))

    def _check_sensitive_words(self, text: str) -> List[str]:
        """检查敏感词"""
        warnings = []

        for word in self.sensitive_words:
            if word in text:
                warnings.append(f"包含敏感词: '{word}'")

        return warnings

    def _create_error_result(self, original: str, error: str) -> RewriteResult:
        """创建错误结果"""
        return RewriteResult(
            original_text=original,
            rewritten_text=original,  # 返回原文
            style="错误",
            hashtags=[],
            emoji_suggestions=[],
            engagement_score=0.0,
            warnings=[f"改写失败: {error}"],
        )
