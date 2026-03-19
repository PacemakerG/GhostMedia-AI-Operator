# Stage A 运行手册（基础稳定）

目标：让 `Trend-grab-agent`、`content-vedio-agent`、`social-auto-upload` 三个模块可独立启动，并完成最小功能验证。

## 1. 先决条件

1. 已安装 Conda、Node.js（用于 social 前端）。
2. 已准备 API Key（LLM、素材平台）与平台 Cookie。
3. 首次执行：

```bash
bash scripts/setup_ghostmedia.sh
```
4. 配置统一参数（推荐）：
```bash
cp .env.example .env
bash scripts/sync_env.sh
```

## 2. 推荐启动顺序

1. `Trend`（抓热点）  
2. `Content`（生成视频）  
3. `Social`（发布上传）

## 3. 模块运行与验证

### 3.1 Trend-grab-agent
- 启动命令：
```bash
bash scripts/run_trend.sh run
```
- 体检命令：
```bash
bash scripts/run_trend.sh doctor
```
- 输入/输出：
  - 输入：`config/config.yaml`、热点源/RSS
  - 输出：`output/` 下的报告与存储数据
- 常见故障：
  - 报 `AI API Key` 缺失：检查 `config.yaml` 或 `Trend-grab-agent/.env`
  - 报配置文件缺失：确认 `config/config.yaml` 在仓库中存在

### 3.2 content-vedio-agent
- 启动 API：
```bash
bash scripts/run_content.sh api
```
- 启动 WebUI：
```bash
bash scripts/run_content.sh webui
```
- 输入/输出：
  - 输入：选题文案、素材 API Key、LLM 配置
  - 输出：`storage/tasks/` 任务产物（视频/字幕等）
- 最小验证：
  - 打开 `http://127.0.0.1:8080/docs`

### 3.3 social-auto-upload
- 启动后端：
```bash
bash scripts/run_social.sh backend
```
- 启动前端：
```bash
bash scripts/run_social.sh frontend
```
- 输入/输出：
  - 输入：`cookiesFile/` 账号 cookie、`videoFile/` 待发布视频
  - 输出：平台发布结果、`db/database.db` 记录
- 最小验证：
  - 打开 `http://127.0.0.1:5409`

## 4. 日志定位建议

1. 先看终端首个报错，不要只看最后一行异常。
2. 优先排查配置与密钥，再排查依赖版本。
3. 若是平台上传失败，先复用对应 `examples/` 脚本验证单平台链路。
