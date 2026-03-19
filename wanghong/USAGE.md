# X 平台内容抓取项目

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
# OPENAI_API_KEY=your_key_here
```

编辑 `config/config.yaml`，填入你的 X 平台登录凭证：

```yaml
x_credentials:
  username: "your_x_username"
  password: "your_x_password"
```

### 3. 运行程序

```bash
# 抓取猫神的 20 条推文，使用幽默风格改写
python src/main.py --username Maoshen9527 --limit 20 --style humorous

# 输出示例：
# ✅ 抓取完成: 20 条推文
# ✅ 媒体下载: 15 个文件
# ✅ 文案改写: 20 条内容
# 📄 结果保存: data/processed/Maoshen9527_20240316_123456.json
```

## 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--username` | `-u` | X 用户名（不含@） | 必填 |
| `--limit` | `-l` | 抓取推文数量 | 20 |
| `--style` | `-s` | 改写风格 | humorous |
| `--no-download` | - | 跳过下载媒体 | False |
| `--config` | `-c` | 配置文件路径 | config/config.yaml |

## 改写风格说明

- **humorous** (幽默风趣): 轻松搞笑、玩梗、接地气
- **professional** (专业严谨): 专业术语、逻辑清晰
- **emotional** (情感共鸣): 走心、有温度、引发共鸣
- **concise** (简洁直白): 短句、直接、不绕弯
- **storytelling** (故事叙述): 有情节、有画面感

## 数据输出格式

处理后的数据保存在 `data/processed/` 目录，JSON 格式：

```json
{
  "username": "Maoshen9527",
  "timestamp": "2024-03-16T12:34:56",
  "config": {
    "limit": 20,
    "style": "humorous"
  },
  "stats": {
    "tweets_fetched": 20,
    "media_downloaded": 15,
    "content_rewritten": 20,
    "errors": 0
  },
  "data": [
    {
      "original": {
        "tweet_id": "1234567890",
        "username": "Maoshen9527",
        "content": "原文内容...",
        "created_at": "2024-03-15T10:30:00",
        "stats": {
          "likes": 1234,
          "retweets": 567,
          "replies": 89,
          "views": 12345
        },
        "hashtags": ["#猫咪", "#搞笑"],
        "media_count": 2
      },
      "rewritten": {
        "content": "改写后的内容...",
        "style": "幽默风趣",
        "hashtags": ["#猫咪", "#搞笑", "#萌宠"],
        "emoji_suggestions": ["😂", "🐱", "👍"],
        "engagement_score": 85.5,
        "warnings": []
      }
    }
  ]
}
```

## 注意事项

1. **合法合规**: 仅用于个人学习研究，遵守 X 平台使用条款
2. **API 限制**: X 平台有 API 调用限制，请控制抓取频率
3. **隐私保护**: 不要将敏感信息提交到 Git 仓库
4. **AI 改写**: 改写后的内容建议人工审核后再使用

## 故障排除

### 问题1: 无法登录 X 平台

**解决方案**:
- 检查用户名密码是否正确
- 尝试使用 cookies 登录（从浏览器复制）
- 检查是否需要 2FA 验证

### 问题2: API 调用失败

**解决方案**:
- 检查 API Key 是否有效
- 查看 API 调用配额是否用完
- 增加请求间隔时间

### 问题3: 媒体下载失败

**解决方案**:
- 检查网络连接
- 检查磁盘空间
- 检查文件权限

## 更新日志

### v1.0.0 (2024-03-16)
- ✅ 实现 X 平台推文抓取
- ✅ 实现图片/视频下载
- ✅ 实现 AI 文案改写
- ✅ 支持多种改写风格
- ✅ 输出结构化 JSON 数据

## 贡献

欢迎提交 Issue 和 PR！

## 许可证

MIT License - 仅供学习研究使用
