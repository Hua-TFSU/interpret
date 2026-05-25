# Hua-TFSU Real-time Interpreter

面向课堂、会议和直播场景的实时同传字幕平台 MVP，支持浏览器采集麦克风音频，后端实时听写并做英中/中英字幕翻译。

## 功能

- 浏览器麦克风采集，前端重采样到 16 kHz Float32 PCM。
- WebSocket 实时推送音频分片到 FastAPI 后端。
- faster-whisper 执行中英/英中听写。
- OpenAI-compatible Chat Completions 执行双语字幕翻译。
- 前端显示听写、翻译、音频波形、历史字幕和 JSON 导出。
- 前端可通过 `API Key` 按钮输入 OpenAI API key；key 仅保存在浏览器本地，并通过 HTTPS 请求头临时传给后端翻译接口。
- 四个平行工作区：实时字幕、术语库、双语语料库、手写笔记。
- 术语库支持手动添加和 AI 一键抓取；翻译时优先使用术语表。
- 双语语料库保存在浏览器本地，可从字幕流存入语料。
- 手写笔记支持鼠标、触控板和触控笔绘制、保存与下载。
- Docker Compose 一键部署。

## 本地运行

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000`。

轻量连通性测试环境可设置 `HUA_TFSU_ASR_PROVIDER=demo`，无需安装模型即可验证 WebSocket、麦克风采集和字幕推送链路。生产环境使用默认 `faster_whisper`。

## Docker 部署

```bash
cp .env.example .env
docker compose up --build
```

CPU 默认使用 `small/int8`，首次启动会下载 Whisper 模型。GPU 部署时可把 `.env` 改为：

```env
HUA_TFSU_WHISPER_DEVICE=cuda
HUA_TFSU_WHISPER_COMPUTE_TYPE=float16
```

## Render 部署

仓库根目录包含 `render.yaml`，可在 Render Dashboard 里用 Blueprint 或 Docker Web Service 部署。

- Service type: Web Service
- Runtime: Docker
- Health check path: `/health`
- 默认云端 ASR: `HUA_TFSU_ASR_PROVIDER=demo`，用于先验证页面、WebSocket、术语表、语料库和翻译链路。
- 生产 ASR: 把 `HUA_TFSU_ASR_PROVIDER` 改为 `faster_whisper`，并使用更高规格实例；首次启动会下载 Whisper 模型。
- OpenAI Key: 在 Render 环境变量里设置 `HUA_TFSU_OPENAI_API_KEY`，不要写入代码仓库。

## 参考项目

源码已放在 `references/`：

- `collabora/WhisperLive`，约 4043 stars。
- `ufal/whisper_streaming`，约 3623 stars。
- `ufal/SimulStreaming`，约 601 stars。

设计对比见 `docs/design.md`。
