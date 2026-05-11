# OpenClaw 代码库文档

> 供 AI 快速理解项目结构与业务逻辑。最后更新：2026-04-24

---

## 一、项目概览

**OpenClaw**（产品名「文栈」）是一款**微信公众号 AI 写作助手**，由三个相互配合的子系统构成：

| 子系统 | 技术 | 作用 |
|--------|------|------|
| `openclaw/` | Python 核心库 + Typer CLI | 文章生成逻辑、配置管理、旧版 PySide6 桌面端 |
| `wechat_backend/` | FastAPI | HTTP 服务：生成接口、微信草稿/封面上传 |
| `openclaw-tauri/` | Tauri 2 + React 18 + Vite | **主桌面客户端**（新版，重点） |

项目**不是** monorepo，根目录无 `package.json`，Python 和 Node 两套依赖互相独立。

---

## 二、目录结构

```
openClaw/
├── openclaw/               # Python 核心
│   ├── config.py           # OpenClawConfig：读 ARK_* 环境变量
│   ├── generator.py        # ArticleGenerator：调用豆包/ARK API 生成文章
│   ├── prompt_templates.py # 提示词模板
│   ├── cli.py              # Typer CLI 入口
│   ├── desktop_app.py      # 旧版 PySide6 桌面 UI（已被 Tauri 替代）
│   └── collapsible_box.py  # PySide6 折叠组件
│
├── wechat_backend/         # FastAPI 后端
│   ├── app.py              # 路由注册（4 个端点，见下）
│   └── config.py           # 微信账号配置
│
├── openclaw-tauri/         # 主桌面客户端（重点）
│   ├── src/                # React 前端
│   ├── src-tauri/          # Rust/Tauri 壳
│   ├── package.json
│   ├── vite.config.ts
│   └── index.html
│
├── requirements.txt        # Python 依赖
├── run_desktop.py          # 启动旧版 PySide6
├── .env                    # 本地环境变量（含 ARK key，勿提交）
├── PRD_OpenClaw.md         # 产品需求文档
├── DEPLOYMENT.md           # 打包与部署说明
└── README.md
```

---

## 三、openclaw-tauri 详解（重点）

### 3.1 前端目录结构

```
openclaw-tauri/src/
├── main.tsx                  # React 挂载点，导入全局 CSS
├── App.tsx                   # 主状态机（核心）
├── styles.css                # 布局与皮肤
│
├── lib/
│   ├── types.ts              # 所有 TypeScript 类型/接口定义
│   ├── app-ui.ts             # UI 枚举选项、默认值、工具函数
│   ├── openclaw-api.ts       # 所有 HTTP 调用封装
│   └── tauri.ts              # Tauri IPC 封装（get_runtime_info）
│
└── components/
    ├── Sidebar.tsx            # 左侧栏：品牌、服务状态、账号切换、导航
    ├── TopTemplateTabs.tsx    # 提示词槽位 Tab（工作区顶部）
    └── pages/
        ├── WorkspacePage.tsx  # 主工作台：参数填写 + Markdown 编辑器
        ├── PromptPage.tsx     # 提示词模板管理
        ├── AccountPage.tsx    # 账号配置展示
        ├── ModelPage.tsx      # API Key / 模型 ID / 联网开关
        └── PlaceholderPage.tsx # 应用设置（占位）
```

### 3.2 App.tsx — 核心状态机

`App.tsx` 是整个应用的状态中心，所有业务逻辑都集中在 `InnerApp` 组件中。

**关键常量**：
```ts
// 开发时走 Vite 代理 /api，生产时直连线上服务
const BACKEND_BASE_URL = import.meta.env.DEV ? "/api" : "http://49.235.172.63:8000";
```

**localStorage 持久化键名**（前缀 `openclaw.*`）：

| 键名 | 存储内容 |
|------|----------|
| `openclaw.wechatAccounts` | 微信公众号账号列表 `WechatAccount[]` |
| `openclaw.activeAccountId` | 当前选中账号 id |
| `openclaw.promptSlots` | 提示词槽位列表 `PromptSlot[]` |
| `openclaw.activePromptId` | 当前选中提示词槽位 id |
| `openclaw.articleDraft` | 创作参数 `GeneratePayload` |
| `openclaw.draftMeta` | 草稿元数据 `DraftMeta`（标题/作者/摘要） |
| `openclaw.resultMarkdown` | 生成结果 Markdown 字符串 |

**主要状态**：

```ts
activeView: SidebarView          // 当前页面："workspace"|"account"|"model"|"prompt"|"settings"
accounts: WechatAccount[]        // 公众号账号列表
activeAccountId: string          // 当前账号 id
promptSlots: PromptSlot[]        // 4 个预设提示词槽位
activePromptId: string           // 当前提示词
articleDraft: GeneratePayload    // 生成参数（含 topic、style、length 等）
draftMeta: DraftMeta             // 发草稿元数据（标题、作者、摘要）
resultMarkdown: string           // 生成结果
serviceStatus: string            // "连接中" | "服务正常" | "服务异常" | "连接失败"
isGenerating / isSendingDraft / isUploadingCover  // 各异步操作 loading
```

**关键业务流程**：

1. **生成文章** `handleGenerateArticle`：
   - 校验 topic（原创模式）/ sourceArticle（改写模式）
   - 调 `generateArticle(BACKEND_BASE_URL, articleDraft)`
   - 返回后提取标题、生成摘要，写入 `resultMarkdown` 和 `draftMeta`

2. **发送草稿** `handleSendDraft`：
   - 校验账号、内容、AppID/Secret、thumbMediaId
   - 调 `sendWechatDraft(BACKEND_BASE_URL, {...})`

3. **上传封面** `handleCoverUpload`：
   - 校验文件类型（PNG/JPG）和大小（≤1MB）
   - 调 `uploadWechatThumb` 后将返回的 `thumbMediaId` 写回账号

4. **账号管理**：Modal 弹窗管理创建/编辑，删除时至少保留 1 个账号

5. **自动保存**：所有状态变化时通过 `useEffect` 写入 localStorage

### 3.3 lib/types.ts — 类型定义

**核心接口**：

```ts
interface GeneratePayload {
  topic: string;             // 文章主题
  audience: string;          // 目标读者（"大学生"等）
  style: string;             // 风格（"专业理性"等）
  length: "short"|"medium"|"long";
  mode: "standard"|"story"|"case_study"|"listicle"|"analysis";
  systemPrompt: string;      // 系统提示词
  creationMode: "synthesized"|"rewrite";
  sourceArticle?: string;    // 改写模式下的参考文章（≤5000字）
  rewriteGoal: "new_article"|"new_angle"|"more_conversational"|"more_actionable";
  referenceFocus: "mixed"|"structure"|"tone"|"opening";
  referenceLevel: "low"|"medium"|"high";
  expressionMode: "standard"|"conversational"|"de_ai"|"opinionated";
  apiKey?: string;           // 前端直连豆包时填写
  apiModel?: string;         // 默认 "doubao-seed-2-0-pro-260215"
  apiBaseUrl?: string;       // 默认 "https://ark.cn-beijing.volces.com/api/v3"
  enableWebSearch?: boolean; // 默认 true
}

interface WechatAccount {
  id: string;           // "account-xxxxxxxx"
  name: string;         // 公众号名称
  appId: string;        // 微信 AppID
  appSecret: string;    // 微信 AppSecret
  thumbMediaId: string; // 封面永久素材 ID
}

interface DraftPayload {
  title: string;
  contentMd: string;    // Markdown 内容，后端转 HTML
  digest?: string;
  author?: string;
  wechatAppId?: string;
  wechatAppSecret?: string;
  wechatThumbMediaId?: string;
  wechatBaseUrl?: string;
}
```

### 3.4 lib/openclaw-api.ts — API 调用层

**两条生成路径（关键分支）**：

```
generateArticle(baseUrl, payload)
    │
    ├─ payload.apiKey && payload.apiModel 都存在？
    │       ↓ YES
    │   generateArticleDirectly()  ← 前端直连豆包
    │   POST /doubao/responses（开发）
    │   POST https://ark.cn-beijing.volces.com/api/v3/responses（生产）
    │   使用豆包 Responses API（非 Chat Completions）
    │
    └─ NO → POST {baseUrl}/article/generate  ← 走 Python 后端
```

**字段名转换**（前端 camelCase ↔ 后端 snake_case）：

| 前端 | 后端 |
|------|------|
| `systemPrompt` | `system_prompt` |
| `creationMode` | `creation_mode` | (synthesized\|rewrite) |
| `sourceArticle` | `source_article` |
| `rewriteGoal` | `rewrite_goal` |
| `referenceFocus` | `reference_focus` |
| `referenceLevel` | `reference_level` |
| `expressionMode` | `expression_mode` |
| `apiKey` | `api_key` |
| `apiModel` | `model` |
| `apiBaseUrl` | `api_base_url` |
| `enableWebSearch` | `enable_web_search` |

**直连豆包时的 Prompt 构建**：
- System prompt → `input[0].content[0]`（input_text）
- 由 `buildDirectUserPrompt` 构建的 user prompt → `input[0].content[1]`（input_text）
- `enableWebSearch` 为真时加 `tools: [{ type: "web_search" }]`

**所有 API 函数**：

| 函数 | 调用路径 | 说明 |
|------|----------|------|
| `backendHealthcheck(baseUrl)` | `GET {baseUrl}/health` | 服务状态检查 |
| `generateArticle(baseUrl, payload)` | 见上方分支 | 生成文章 |
| `sendWechatDraft(baseUrl, payload)` | `POST {baseUrl}/wechat/draft` | 发草稿到公众号 |
| `uploadWechatThumb(baseUrl, file, account)` | `POST {baseUrl}/wechat/upload_thumb` | 上传封面图（multipart） |

### 3.5 lib/app-ui.ts — UI 选项与默认值

**默认提示词槽位**（4 个，可自定义）：
1. `系统提示词` - 通用内容编辑
2. `新媒体运营` - 干货可执行内容
3. `心理医生` - 专业温和心理内容
4. `树洞学姐` - 亲和真诚细腻表达

**工具函数**：
- `extractTitleFromMarkdown(md, fallback)` - 提取 `# 标题`，最多 64 字
- `summarizeMarkdown(md)` - 去掉 Markdown 符号后取前 120 字作摘要
- `maskValue(value)` - 脱敏显示（保留前8后5位）
- `parseStoredValue(key, fallback)` - 安全读取 localStorage

### 3.6 Vite 配置（开发代理）

```ts
// vite.config.ts
proxy: {
  "/api": {
    target: "http://49.235.172.63:8000",
    rewrite: (path) => path.replace(/^\/api/, ""),
  },
  "/doubao": {
    target: "https://ark.cn-beijing.volces.com/api/v3",
    rewrite: (path) => path.replace(/^\/doubao/, ""),
  }
}
// 开发服务器：127.0.0.1:1420
```

### 3.7 src-tauri（Rust 壳）

Rust 侧**极简**，仅提供一个命令：

```rust
// src-tauri/src/lib.rs
#[tauri::command]
fn get_runtime_info() -> RuntimeInfo {
    RuntimeInfo {
        platform: std::env::consts::OS.to_string(),   // "windows"/"linux"/"macos"
        arch: std::env::consts::ARCH.to_string(),
        tauri_version: env!("CARGO_PKG_VERSION").to_string(),
    }
}
```

| 配置项 | 值 |
|--------|-----|
| productName | 文栈 |
| identifier | com.openclaw.desktop |
| 窗口尺寸 | 1120×760，可缩放 |
| devUrl | http://127.0.0.1:1420 |
| beforeDevCommand | npm run dev |
| frontendDist | ../dist |
| icon | icons/icon.ico |

前端调用：
```ts
// lib/tauri.ts
import { invoke } from "@tauri-apps/api/core";
// 在浏览器环境降级为 mock 数据
```

---

## 四、wechat_backend（Python FastAPI）

### 4 个 HTTP 端点

| 方法 | 路径 | 作用 |
|------|------|------|
| `GET` | `/health` | 返回 `{"status":"ok"}` |
| `POST` | `/article/generate` | 接收 snake_case 字段，调用 `ArticleGenerator` 生成 Markdown |
| `POST` | `/wechat/upload_thumb` | multipart 上传图片，通过微信 API 存为永久素材，返回 `thumb_media_id` |
| `POST` | `/wechat/draft` | 接收 Markdown，转 HTML 后通过微信 API 创建草稿，返回 `media_id` |

### `/article/generate` 请求体（snake_case）

与前端 `buildGeneratePayload()` 输出一致，见 3.4 节字段映射表。

---

## 五、Python 核心（openclaw/）

| 文件 | 说明 |
|------|------|
| `config.py` | `OpenClawConfig`：读 `ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL`、`ARK_ENABLE_WEB_SEARCH` |
| `generator.py` | `ArticleGenerator`：OpenAI 兼容客户端，调用豆包/ARK 生成文章 |
| `prompt_templates.py` | 系统提示词模板 |
| `cli.py` | Typer CLI，可命令行生成文章 |
| `desktop_app.py` | 旧版 PySide6 桌面 UI（已被 Tauri 替代，仅维护） |

---

## 六、数据流总览

```
用户操作
  │
  ▼
React UI（App.tsx 状态管理）
  │
  ├─ localStorage ◄── 自动保存所有状态
  │
  ├─ [生成文章，有 apiKey]──────────────────► 豆包 /responses API（直连）
  │                                            使用豆包 Responses API（非 Chat）
  │
  ├─ [生成文章，无 apiKey]─────────────────► FastAPI POST /article/generate
  │                                                │
  │                                                └─► Python ArticleGenerator
  │                                                       │
  │                                                       └─► 豆包/ARK API
  │
  ├─ [发草稿]──────────────────────────────► FastAPI POST /wechat/draft
  │                                                │
  │                                                └─► 微信公众号 API
  │
  ├─ [上传封面]────────────────────────────► FastAPI POST /wechat/upload_thumb
  │                                                │
  │                                                └─► 微信公众号 API（永久素材）
  │
  └─ [Tauri IPC] get_runtime_info ─────────► Rust：返回 OS/架构/版本
```

---

## 七、已知问题与注意点

1. **生产 URL 硬编码**：`App.tsx` 中 `BACKEND_BASE_URL` 生产值写死为 `http://49.235.172.63:8000`，与 README 中提到的 `VITE_API_BASE_URL` 环境变量**不通用**（`openclaw-api.ts` 的 `defaultBackendBaseUrl` 读了该变量，但主流程用的是 `App.tsx` 的常量）。如需修改服务地址，**只改 `App.tsx` 第 36 行**。

2. **豆包 Responses API 格式**：直连豆包走的是 `/responses` 端点，使用 `input[]` 格式（非 `messages[]`），返回 `output[].content[]` 中的 `output_text` 类型字段，与标准 Chat Completions 不同。

3. **改写模式参考文章长度限制**：前端截取前 5000 字，后端无此限制。校验：改写模式需 ≥300 字才允许生成。

4. **封面图限制**：仅支持 PNG/JPG，大小 ≤1MB（前端校验）。

5. **账号 AppSecret 安全**：存在 localStorage 中，明文。脱敏显示在 UI 中用 `maskValue()`，但本地存储未加密。

6. **Rust 侧极简**：目前 Tauri 的 Rust 代码仅提供 `get_runtime_info` 命令，不参与任何业务逻辑。所有请求直接从前端发出，不经过 Rust 代理。

---

## 八、开发启动

```bash
# 启动 Python 后端
uvicorn wechat_backend.app:app --reload --host 0.0.0.0 --port 8000

# 启动 Tauri 桌面客户端（另开终端）
cd openclaw-tauri
npm run tauri dev
# 等价于：Vite dev server（1420端口）+ Rust 构建

# 仅启动前端（浏览器预览，无 Tauri 功能）
cd openclaw-tauri
npm run dev
```

---

## 九、依赖速查

**前端（openclaw-tauri/package.json）**：
- `@tauri-apps/api ^2` - Tauri IPC
- `antd ^6.3.6` - UI 组件库（主色 `#6366f1`）
- `@ant-design/icons ^6.1.1`
- `react ^18.3.1`
- `typescript`、`vite ^5`

**Python（requirements.txt）**：
- `fastapi`、`uvicorn` - Web 服务
- `openai` - 兼容 ARK/豆包 API
- `python-dotenv` - 环境变量
- `PySide6` - 旧版桌面 UI
- `typer` - CLI

**Rust（src-tauri/Cargo.toml）**：
- `tauri 2`
- `serde` / `serde_json`
