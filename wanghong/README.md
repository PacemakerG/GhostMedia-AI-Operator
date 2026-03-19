# X 平台内容抓取器

从 X 平台抓取指定用户的内容、图片和视频，并使用 AI 改写文案。

## 快速开始

```bash
pip install -r requirements.txt
python src/main.py --username Maoshen9527 --limit 20
```

## 功能特性

- ✅ 抓取指定用户的推文内容
- ✅ 下载图片和视频到本地
- ✅ 使用 AI 智能改写文案
- ✅ 保留原帖时间戳和互动数据
- ✅ 支持增量更新（避免重复下载）

## 项目结构

```
wanghong/
├── src/
│   ├── crawler/        # X 平台爬虫
│   ├── downloader/     # 媒体下载器
│   ├── rewriter/       # AI 文案改写
│   └── main.py         # 主入口
├── config/             # 配置文件
├── data/               # 数据存储
└── logs/               # 日志
```

## 配置说明

编辑 `config/config.yaml`:

```yaml
x_credentials:
  username: "your_username"
  password: "your_password"
  
ai_config:
  model: "gpt-4"
  api_key: "your_api_key"
  
download:
  save_images: true
  save_videos: true
  quality: "original"
```

## 使用示例

```bash
# 抓取猫神的最近 20 条推文
python src/main.py --username Maoshen9527 --limit 20

# 只抓取图片，不包含视频
python src/main.py --username Maoshen9527 --limit 50 --no-video

# 使用 AI 改写文案
python src/main.py --username Maoshen9527 --rewrite --style "幽默风趣"
```

## 注意事项

1. 爬取 X 平台需要有效的登录凭证
2. 遵守 X 平台的 robots.txt 和使用条款
3. 建议添加适当的延迟以避免触发反爬机制
4. 仅用于个人学习和研究目的

## License

MIT License - 仅供学习研究使用
