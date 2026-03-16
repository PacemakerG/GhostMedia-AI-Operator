# 仓库协作指南

## 项目结构与模块组织
本仓库是一个 AI 自媒体运营流程的集成工作区，采用“上游项目隔离 + 中央编排”的方式推进。

- `apps/social-auto-upload/`：已纳入版本管理的自动发布执行器（Python 后端 + Vue 前端）。
- `Riona-AI-Agent/`：TypeScript 自动化 Agent（核心代码在 `src/`，测试在 `src/test/`）。
- `Trend-grab-agent/`：热点抓取与分析模块（`trendradar/`、`mcp_server/`、`config/`）。
- `content-vedio-agent/`：内容生成与视频合成模块（`app/`、`webui/`、`test/`）。
- `README.md`：项目目标、阶段说明和后续模块规划。

新增集成代码建议放在顶层目录（如 `agents/`、`orchestration/`），避免直接改动上游源码结构。

## 构建、测试与开发命令
请在对应子项目目录执行命令。

- Riona（TS）：
  - `npm ci`
  - `npm run typecheck && npm run lint && npm test`
  - `npm start`
- TrendGrab（Python）：
  - `pip install -r requirements.txt`
  - `python -m trendradar`（命令行运行）
  - `python -m mcp_server.server`（MCP 服务）
- Content Video（Python）：
  - `pip install -r requirements.txt`
  - `bash webui.sh`
  - `python -m unittest discover -s test`
- Social Auto Upload：
  - `pip install -r requirements.txt`
  - `python sau_backend.py`
  - `cd sau_frontend && npm install && npm run dev`

## 代码风格与命名规范
- TypeScript 遵循 ESLint + Prettier（`Riona-AI-Agent` 内执行 `npm run lint`、`npm run format`）。
- Python 遵循 PEP 8，4 空格缩进；函数和模块用 `snake_case`，类名用 `PascalCase`。
- 平台适配逻辑放在各项目既有 `uploader/adapter` 目录，不跨模块混放。
- 测试命名：Python 使用 `test_*.py`，TS 使用 Jest 风格测试文件。

## 测试要求
- 只改哪个模块，就至少跑哪个模块的原生测试与静态检查。
- PR 最低标准：
  - 受影响模块测试通过；
  - 关键链路（抓取 -> 生成 -> 发布）至少完成一次冒烟验证。
- 修复缺陷时，若模块已有测试框架，优先补回归测试。

## 提交与合并请求规范
- 提交信息使用 Conventional Commits（当前历史示例：`chore: ...`、`docs: ...`）。
- 按模块限定提交范围，例如：`feat(trendradar): add topic scoring cache`。
- PR 说明需包含：变更目的、影响模块、执行命令与结果、配置变更（如 `.env`/密钥/cookie/代理）、必要截图或日志。

## 安全与配置提示
- 严禁提交密钥、Cookie、账号会话信息。
- 本地产物（`*.db`、日志、生成视频、cookie 目录）不得入库。
- 跨项目复用代码前先核对上游许可证与商业使用条款。
