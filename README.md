## OpenClaw 小说写作助手

**OpenClaw** 是一个本地运行的小说写作工具，支持短篇/长篇连载，每日续写，前后内容连贯。

### 功能特性

- **连载续写**：按章节生成，支持短篇、长篇
- **前后连贯**：自动维护前情摘要，每章自动生成摘要供续写使用
- **JSON 存储**：小说与章节以 JSON 文件保存，便于备份与迁移
- **导出 Markdown**：支持导出整本小说为 Markdown 文件

### 目录结构

```text
openclaw/
  __init__.py
  config.py          # ARK 模型配置
  novel_store.py     # 小说 JSON 存储
  novel_prompts.py   # 小说提示词模板
  novel_generator.py # 续写与摘要生成
  cli.py             # 命令行入口
  desktop_app.py     # 桌面应用
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

```bash
# 方式一
python run_desktop.py

# 方式二
python -m openclaw

# 方式三
python -m openclaw run
```

### 配置

在项目根目录创建 `.env` 文件（可选，也可在界面中填写）：

```bash
ARK_API_KEY=你的_ARK_key
ARK_MODEL=你的模型ID
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 使用流程

1. 点击「新建」创建小说，填写标题和简介
2. 在「小说配置」中完善简介、人物、类型（短篇/长篇）
3. 在「模型配置」中填写豆包 Key 和模型 ID
4. 点击「生成下一章」开始续写
5. 可选填写「本章梗概」引导生成方向
6. 生成完成后自动生成本章摘要，供后续章节连贯使用
7. 可随时切换章节编辑，或导出整本为 Markdown

### 数据存储

小说数据保存在 `~/.openclaw/novels/` 目录，每个小说一个 JSON 文件。
