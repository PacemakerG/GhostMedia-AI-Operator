# 配置模板说明（Stage A）

本仓库采用“根目录 `.env` 统一控制 + 模块配置自动同步”的方式。你只需维护一个 `.env`，再执行同步脚本。

## 0. 统一入口

1. 复制模板：
```bash
cp .env.example .env
```
2. 填写 `.env` 中的 `GM_*`、`CONTENT_*`、`SOCIAL_*` 参数。
3. 执行同步：
```bash
bash scripts/sync_env.sh
```

## 1. 模板与目标文件

1. `content-vedio-agent/config.example.toml` -> `content-vedio-agent/config.toml`
2. `social-auto-upload/conf.example.py` -> `social-auto-upload/conf.py`
3. `Trend-grab-agent/docker/.env` -> `Trend-grab-agent/.env`（本地环境变量覆盖）

## 2. 必填项（最小可运行）

### Trend-grab-agent
- 文件：`Trend-grab-agent/config/config.yaml`
- 至少确认：
  - `app.timezone`（建议 `Asia/Shanghai`）
  - `ai.model`、`ai.api_key`（或使用环境变量 `AI_API_KEY`）
  - 至少一个通知渠道（可选，但生产建议配置）

### content-vedio-agent
- 文件：`content-vedio-agent/config.toml`
- 至少确认：
  - `llm_provider` 与对应 API Key（如 `openai_api_key`）
  - `pexels_api_keys` 或 `pixabay_api_keys`（素材来源）

### social-auto-upload
- 文件：`social-auto-upload/conf.py`
- 至少确认：
  - `LOCAL_CHROME_PATH`（本机 Chrome 路径）
  - 已创建 `cookiesFile/`、`videoFile/`
  - 已初始化 `db/database.db`

## 3. 快速初始化命令

```bash
bash scripts/setup_ghostmedia.sh
```

脚本会自动创建缺失模板副本与基础目录，并按 `.env` 更新模块配置。

## 4. 安全约束

1. 所有密钥仅写入本地配置，不提交到 Git。
2. 优先使用环境变量注入密钥（尤其是生产环境）。
3. 若怀疑密钥泄露，先撤销旧密钥再继续运行。
