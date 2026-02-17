# Browser Insight Hybrid MCP

本地化浏览器 JS 抓取、Source Map 高保真还原、增量 RAG 索引的 MCP 服务器。

采用 **Python Host + Node.js Worker** 混合架构：Python 负责 MCP 通信、CDP 浏览器控制、向量数据库；Node.js 负责 JS AST 解析和 Source Map 还原。

## 环境要求

- [uv](https://github.com/astral-sh/uv)（Python 包管理器）
- Node.js >= 18
- Chrome / Chromium（可自动启动，无需手动配置）

> Windows 用户：推荐使用 PowerShell 7+ 执行以下命令。uv 和 Node.js 均支持 Windows，安装方式参考各自官网。

## 安装

### 1. 克隆项目

```bash
git clone <repo-url>
cd auto_js_reverse
```

### 2. 安装 Python 依赖

**macOS / Linux:**

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install fastmcp websockets lancedb fastembed pyarrow aiohttp numpy
```

**Windows (PowerShell):**

```powershell
uv venv --python 3.12 .venv
.venv\Scripts\Activate.ps1
uv pip install fastmcp websockets lancedb fastembed pyarrow aiohttp numpy
```

**Windows (CMD):**

```cmd
uv venv --python 3.12 .venv
.venv\Scripts\activate.bat
uv pip install fastmcp websockets lancedb fastembed pyarrow aiohttp numpy
```

### 3. 安装 Node.js 依赖

**macOS / Linux:**

```bash
cd src/browser_insight/node_worker
npm install
cd ../../..
```

**Windows:**

```cmd
cd src\browser_insight\node_worker
npm install
cd ..\..\..
```

### 4. 配置硅基流动 API Key

向量化使用[硅基流动](https://cloud.siliconflow.cn/i/exnclWno/)的 `BAAI/bge-m3` 远程 Embedding 模型，无需本地 GPU。

注册[硅基流动](https://cloud.siliconflow.cn/i/exnclWno)账号后，在 [API Key 页面](https://cloud.siliconflow.cn/account/ak) 获取 Key，然后设置环境变量：

**macOS / Linux:**

```bash
export SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

**Windows (PowerShell):**

```powershell
$env:SILICONFLOW_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
```

**Windows (CMD):**

```cmd
set SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

或写入配置文件 `.mcp_config/config.json`：

```json
{
  "embedding": {
    "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

## Chrome 浏览器

MCP 服务器通过 CDP 协议连接 Chrome。支持两种模式：

### 自动启动（默认）

无需手动操作。MCP 服务器在检测不到 Chrome 远程调试端口时，会自动查找并启动本机 Chrome 浏览器。

自动检测的浏览器（按优先级）：
- Google Chrome
- Chromium
- Brave Browser
- Microsoft Edge

Chrome 会使用独立的用户数据目录 `~/.browser_insight/chrome_profile`，不影响你日常使用的 Chrome 配置。

### 手动启动

如果你希望手动控制 Chrome，可以在配置中关闭自动启动：

```json
{
  "chrome_cdp": {
    "auto_launch": false
  }
}
```

然后手动启动 Chrome：

**macOS:**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

**Linux:**

```bash
google-chrome --remote-debugging-port=9222
```

**Windows:**

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

### 无头模式

不需要显示浏览器窗口时，可以开启无头模式：

```json
{
  "chrome_cdp": {
    "headless": true
  }
}
```

启动后在 Chrome 中打开你要分析的目标页面。

## IDE / MCP 客户端配置

所有 IDE 均通过 JSON 配置文件接入 MCP 服务器，使用 `uv run` 启动以确保依赖环境正确。

> 以下示例中 `/absolute/path/to/auto_js_reverse` 请替换为你的实际项目绝对路径。
> - macOS / Linux：通过 `cd auto_js_reverse && pwd` 获取
> - Windows：通过 `cd auto_js_reverse && cd` (CMD) 或 `cd auto_js_reverse; (Get-Location).Path` (PowerShell) 获取
> - Windows 路径示例：`C:\Users\YourName\code\auto_js_reverse`，在 JSON 中需要双反斜杠 `C:\\Users\\YourName\\code\\auto_js_reverse` 或使用正斜杠 `C:/Users/YourName/code/auto_js_reverse`

### Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/auto_js_reverse",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/auto_js_reverse/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

或者通过 Cursor 设置界面：`Settings → MCP Servers → Add`，粘贴上述 JSON 中 `mcpServers` 的内容。

### Windsurf

在项目根目录创建 `.windsurf/mcp.json`：

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/auto_js_reverse",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/auto_js_reverse/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Claude Code

#### 方式一：通过 `.mcp.json` 配置（推荐）

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/auto_js_reverse",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/auto_js_reverse/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

#### 方式二：通过 `claude mcp add` 命令

```bash
claude mcp add browser-insight \
  -e PYTHONPATH=/absolute/path/to/auto_js_reverse/src \
  -e SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx \
  -- uv run --directory /absolute/path/to/auto_js_reverse --python 3.12 python -m browser_insight.main
```

#### 验证连接

添加后重启 Claude Code，输入：

```
/mcp
```

应能看到 `browser-insight` 服务器状态为已连接，并列出以下工具：

- `capture_current_page` - 抓取当前页面 JS 资源
- `search_local_codebase` - RAG 语义检索代码

### VS Code (Copilot)

在项目根目录创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/auto_js_reverse",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/auto_js_reverse/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### OpenCode

在项目根目录创建 `.opencode.json`（或 `~/.config/opencode/opencode.json` 全局生效）：

```json
{
  "mcp": {
    "browser-insight": {
      "type": "local",
      "command": [
        "/absolute/path/to/auto_js_reverse/.venv/bin/python",
        "-m",
        "browser_insight.main"
      ],
      "environment": {
        "PYTHONPATH": "/absolute/path/to/auto_js_reverse/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      },
      "enabled": true
    }
  }
}
```

> 注意：OpenCode 1.2+ 使用 `mcp` 字段（不是 `mcpServers`），`command` 必须是字符串数组，环境变量使用 `environment` 对象。

启动 OpenCode 后，MCP 工具会自动加载，可直接在对话中使用 `capture_current_page` 和 `search_local_codebase`。

### 其他 MCP 客户端

任何支持 MCP Stdio 传输协议的客户端都可以接入。核心启动命令：

**macOS / Linux:**

```bash
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx \
PYTHONPATH=/absolute/path/to/auto_js_reverse/src \
uv run --directory /absolute/path/to/auto_js_reverse --python 3.12 python -m browser_insight.main
```

**Windows (PowerShell):**

```powershell
$env:SILICONFLOW_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
$env:PYTHONPATH = "C:\absolute\path\to\auto_js_reverse\src"
uv run --directory "C:\absolute\path\to\auto_js_reverse" --python 3.12 python -m browser_insight.main
```

**Windows (CMD):**

```cmd
set SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
set PYTHONPATH=C:\absolute\path\to\auto_js_reverse\src
uv run --directory "C:\absolute\path\to\auto_js_reverse" --python 3.12 python -m browser_insight.main
```

## MCP 工具说明

### `capture_current_page`

触发一次完整的全量抓取流程：

1. 通过 CDP 连接 Chrome，获取当前页面所有 JS 资源
2. SHA-256 哈希去重，跳过已索引文件
3. 下载 JS 文件和对应的 Source Map
4. Node.js Worker 进行 Source Map 还原 + AST 语义切分
5. FastEmbed 向量化后写入 LanceDB

参数：
- `force_refresh` (bool, 默认 false) - 忽略缓存，强制重新解析

### `search_local_codebase`

对已索引的代码库进行 RAG 语义检索。

参数：
- `query` (string, 必填) - 自然语言问题
- `domain_filter` (string, 可选) - 限定搜索域名
- `limit` (int, 默认 10) - 返回结果数

### `insight://archived-sites`

Resource 类型，列出所有已归档的域名和统计信息。

## 配置文件

配置文件位于 `.mcp_config/config.json`，可调整：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `chrome_cdp.port` | Chrome 远程调试端口 | 9222 |
| `chrome_cdp.auto_launch` | 未检测到 Chrome 时自动启动 | true |
| `chrome_cdp.headless` | 无头模式（不显示浏览器窗口） | false |
| `chrome_cdp.user_data_dir` | Chrome 用户数据目录 | storage/chrome_profile |
| `storage.base_dir` | JS 文件归档目录 | storage/archives |
| `storage.db_dir` | LanceDB 数据库目录 | storage/db |
| `storage.model_dir` | Embedding 模型缓存目录 | storage/models |
| `pipeline.max_concurrent_downloads` | 并发下载数 | 5 |
| `pipeline.max_file_size_bytes` | 单文件大小上限（超过则降级为行切分） | 5MB |
| `embedding.model_name` | Embedding 模型 | BAAI/bge-small-en-v1.5 |
| `embedding.batch_size` | 向量化批大小 | 32 |
| `node_worker.max_old_space_size_mb` | Node.js 内存限制 | 256 |

## 存储结构

所有运行时数据统一存储在项目的 `storage/` 目录下：

```
storage/
├── archives/                    # JS 文件归档（按日期/域名/原始路径）
│   └── 2026-02-16/
│       └── www.example.com/
│           ├── index.html
│           ├── metadata.json
│           └── static/js/
│               ├── app.abc123.js
│               └── app.abc123.js.map
├── db/                          # LanceDB 向量数据库
│   ├── file_index.lance/
│   └── code_chunks.lance/
├── models/                      # Embedding 模型缓存 (ONNX)
│   └── BAAI--bge-small-en-v1.5/
└── chrome_profile/              # Chrome 用户数据（自动启动时使用）
```

## 常见问题

**Q: 提示 "无法连接到 Chrome DevTools"**

默认情况下 MCP 会自动启动 Chrome，无需手动操作。如果自动启动失败，请检查：
1. 本机是否安装了 Chrome/Chromium/Brave/Edge 浏览器
2. 端口 9222 是否被其他程序占用
   - macOS / Linux：`lsof -i :9222`
   - Windows：`netstat -ano | findstr :9222`
3. 如果关闭了 `auto_launch`，需手动以 `--remote-debugging-port=9222` 参数启动 Chrome

**Q: 模型下载失败或超时**

确认已设置 `HF_ENDPOINT=https://hf-mirror.com` 环境变量。首次下载约 130MB，请耐心等待。

**Q: Node.js 依赖未安装**

进入 `src/browser_insight/node_worker/` 目录执行 `npm install`。

**Q: Source Map 未还原**

很多生产环境网站不提供 `.map` 文件，此时系统会自动降级为解析混淆代码。搜索结果中会标注来源类型。

**Q: Windows 下 `uv` 命令找不到**

确认已将 uv 添加到系统 PATH。推荐通过官方安装脚本安装：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

安装后重启终端即可使用。

**Q: Windows 下 PowerShell 执行策略报错**

如果提示 "无法加载文件 .ps1，因为在此系统上禁止运行脚本"，以管理员身份运行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
