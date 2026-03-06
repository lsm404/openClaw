## OpenClaw 自动写公众号工具

**OpenClaw** 是一个本地运行的小工具，帮助你快速生成公众号文章草稿（标题 / 大纲 / 正文），然后你可以在公众号后台进行人工润色和发布。

### 功能特性

- **一键生成整篇文章**：根据主题、目标读者、风格自动生成「标题 + 大纲 + 正文」。
- **多种写作风格**：支持科普风、职场风、故事风等预设风格，也支持自定义提示词。
- **结构化输出**：自动生成分节小标题，方便直接粘贴到微信公众号编辑器。
- **草稿而非终稿**：定位是「高质量初稿生成器」，方便你二次编辑，而不是完全自动发布。

### 目录结构

```text
openclaw/
  __init__.py
  config.py          # 配置 & ARK/OpenAI 兼容调用
  prompt_templates.py# 提示词模板
  generator.py       # 核心生成逻辑
  cli.py             # 命令行入口
  desktop_app.py     # 桌面应用入口
wechat_backend/
  app.py             # 微信公众号草稿后端（FastAPI）
  config.py          # 公众号配置
requirements.txt
README.md
```

### 安装依赖

```bash
cd /Users/edy/Documents/ower/auto
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 运行桌面应用

在项目根目录、已激活虚拟环境的前提下：

```bash
# macOS / Linux
python -m openclaw.desktop_app

# 或
python run_desktop.py
```

```bash
# Windows
python -m openclaw.desktop_app

# 或
python run_desktop.py
```

> 若未创建 `run_desktop.py`，可直接用 `python -m openclaw.desktop_app` 启动。

### 配置 ARK Key（火山引擎）

在项目根目录创建 `.env` 文件：

```bash
ARK_API_KEY=你的_ARK_key
ARK_MODEL=你的模型ID_例如_doubao-seed-1.6-flash-250828
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 可选：发送到公众号草稿相关
WECHAT_APPID=你的公众号appid
WECHAT_APPSECRET=你的公众号appsecret
WECHAT_THUMB_MEDIA_ID=一张封面图的thumb_media_id
WECHAT_BASE_URL=https://api.weixin.qq.com

# 可选：桌面应用调用后端的地址
BACKEND_BASE_URL=http://127.0.0.1:8000
```

> **注意**：`.env` 只保存在本地，不要提交到任何远端仓库。

### 启动公众号草稿后端

```bash
cd /Users/edy/Documents/ower/auto
source .venv/bin/activate
uvicorn wechat_backend.app:app --reload
```

后端默认监听在 `http://127.0.0.1:8000`，桌面应用会通过 `BACKEND_BASE_URL` 调用 `/wechat/draft` 接口，把当前生成的 Markdown 文章推到公众号草稿箱。

### 命令行用法

生成一篇文章草稿（标题 + 大纲 + 正文）：

```bash
python -m openclaw \
  --topic "AI 如何帮助普通人写公众号" \
  --audience "职场白领" \
  --style "科普+轻松聊天" \
  --length medium \
  --output article.md
```

主要参数说明：

- `--topic`：文章主题（必填）。
- `--audience`：目标读者画像，例如「程序员」「职场新人」等。
- `--style`：写作风格描述，例如「严肃科普」「故事化」「鸡汤文」等。
- `--length`：文章长度，`short` / `medium` / `long`。
- `--output`：输出 markdown 文件名，默认为 `openclaw_article.md`。

### 开发计划（可后续扩展）

- 支持多篇文章批量生成（给出多个 topic 列表）。
- 支持从提示词模板库中选择「选题框架」。
- 支持把生成结果拆分为多条朋友圈 / 视频号脚本。

