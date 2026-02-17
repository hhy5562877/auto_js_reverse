# Browser Insight Hybrid MCP

本地化浏览器 JS 抓取、Source Map 高保真还原、增量 RAG 索引的 MCP 服务器。

采用 **Python Host + Node.js Worker** 混合架构：Python 负责 MCP 通信、CDP 浏览器控制、向量数据库；Node.js 负责 JS AST 解析和 Source Map 还原。

- 仓库地址：https://github.com/hhy5562877/auto_js_reverse
- 作者：[嚯嚯歪](https://github.com/hhy5562877)（hhy5562877@163.com）

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| [Git](https://git-scm.com/) | 任意 | 克隆项目 |
| [uv](https://github.com/astral-sh/uv) | >= 0.4 | Python 包管理器，替代 pip/venv |
| [Node.js](https://nodejs.org/) | >= 18 | JS AST 解析和 Source Map 还原 |
| Chrome / Chromium | 任意 | 可自动启动，无需手动配置 |

## 前置工具安装

如果你已经安装了上述工具，可以跳过本节。

### macOS

推荐使用 [Homebrew](https://brew.sh/) 安装：

```bash
# 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Git（macOS 通常自带，可跳过）
xcode-select --install

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Node.js
brew install node

# 验证安装
uv --version
node --version
npm --version
```

### Linux (Ubuntu / Debian)

```bash
# 更新包管理器
sudo apt update

# 安装 Git
sudo apt install -y git

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Node.js（通过 NodeSource，获取 v18+）
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 安装 Chrome（如果没有，用于 CDP 连接）
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable

# 验证安装
uv --version
node --version
google-chrome --version
```

### Linux (CentOS / RHEL / Fedora)

```bash
# 安装 Git
sudo dnf install -y git

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Node.js
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf install -y nodejs

# 安装 Chrome
sudo dnf install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm

# 验证安装
uv --version
node --version
google-chrome --version
```

### Windows

推荐使用 PowerShell 7+。以管理员身份打开 PowerShell：

```powershell
# 安装 uv
irm https://astral.sh/uv/install.ps1 | iex

# 安装 Node.js（通过官网下载安装包，或使用 winget）
winget install OpenJS.NodeJS.LTS

# 安装 Git（如果没有）
winget install Git.Git

# 重启终端后验证安装
uv --version
node --version
npm --version
git --version
```

如果没有 `winget`，可以手动下载安装：
- uv：https://github.com/astral-sh/uv/releases （下载 `uv-x86_64-pc-windows-msvc.zip`）
- Node.js：https://nodejs.org/ （下载 LTS 版本 `.msi` 安装包）
- Git：https://git-scm.com/download/win

> 安装完成后请确保 `uv`、`node`、`npm`、`git` 命令在终端中可用。如果提示找不到命令，请检查是否已添加到系统 PATH 环境变量，或重启终端。

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/hhy5562877/auto_js_reverse.git
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

MCP 服务器通过 CDP（Chrome DevTools Protocol）协议连接 Chrome。支持两种模式：

### 自动启动（默认，推荐）

无需手动操作。MCP 服务器在检测不到 Chrome 远程调试端口时，会自动查找并启动本机 Chrome 浏览器。

自动检测的浏览器（按优先级）：

| 平台 | 检测路径 |
|------|---------|
| macOS | `/Applications/Google Chrome.app`、`Chromium.app`、`Brave Browser.app`、`Microsoft Edge.app` |
| Linux | `google-chrome`、`chromium`、`brave-browser`、`microsoft-edge`（通过 PATH 查找） |
| Windows | `C:\Program Files\Google\Chrome\Application\chrome.exe`、`Brave`、`Edge` 等默认安装路径 |

Chrome 会使用独立的用户数据目录（`storage/chrome_profile`），不影响你日常使用的 Chrome 配置。

### 手动启动

如果你希望手动控制 Chrome（例如使用已登录的 Chrome 实例），可以在 `.mcp_config/config.json` 中关闭自动启动：

```json
{
  "chrome_cdp": {
    "auto_launch": false
  }
}
```

然后手动启动 Chrome（必须关闭所有已打开的 Chrome 窗口后再执行）：

**macOS:**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

**Linux:**

```bash
# 有桌面环境
google-chrome --remote-debugging-port=9222

# 无桌面环境（服务器 / Docker）
google-chrome --remote-debugging-port=9222 --headless=new --no-sandbox --disable-gpu
```

**Windows (CMD):**

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Windows (PowerShell):**

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

> 如果 Chrome 安装在非默认路径，请替换为实际路径。可以在 Chrome 地址栏输入 `chrome://version` 查看可执行文件路径。

### 无头模式

不需要显示浏览器窗口时（如服务器环境），可以在 `.mcp_config/config.json` 中开启无头模式：

```json
{
  "chrome_cdp": {
    "headless": true
  }
}
```

### 验证 Chrome CDP 连接

启动 Chrome 后，在浏览器中访问以下地址确认 CDP 端口正常：

```
http://localhost:9222/json
```

如果返回 JSON 数组，说明 CDP 连接正常。

## IDE / MCP 客户端配置

所有 IDE 均通过 JSON 配置文件接入 MCP 服务器，使用 `uv run` 启动以确保依赖环境正确。

> 以下示例中的路径请替换为你的实际项目绝对路径：
> - macOS：如 `/Users/yourname/code/auto_js_reverse`（通过 `cd auto_js_reverse && pwd` 获取）
> - Linux：如 `/home/yourname/code/auto_js_reverse`（通过 `cd auto_js_reverse && pwd` 获取）
> - Windows：如 `这里填写项目路径`（通过 `cd auto_js_reverse && cd` 获取，JSON 中使用正斜杠 `/` 或双反斜杠 `\\`）
>
> 以下示例中所有出现 `这里填写项目路径` 的地方，都需要替换为你的实际路径。

### Cursor

在项目根目录创建 `.cursor/mcp.json`：

**macOS / Linux:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

**Windows:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

或者通过 Cursor 设置界面：`Settings → MCP Servers → Add`，粘贴上述 JSON 中 `mcpServers` 的内容。

### Windsurf

在项目根目录创建 `.windsurf/mcp.json`：

**macOS / Linux:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

**Windows:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Claude Code

#### 方式一：通过 `.mcp.json` 配置（推荐）

在项目根目录创建 `.mcp.json`：

**macOS / Linux:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

**Windows:**

```json
{
  "mcpServers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

#### 方式二：通过 `claude mcp add` 命令

**macOS / Linux:**

```bash
claude mcp add browser-insight \
  -e PYTHONPATH=这里填写项目路径/src \
  -e SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx \
  -- uv run --directory 这里填写项目路径 --python 3.12 python -m browser_insight.main
```

**Windows (PowerShell):**

```powershell
claude mcp add browser-insight `
  -e PYTHONPATH=这里填写项目路径/src `
  -e SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx `
  -- uv run --directory 这里填写项目路径 --python 3.12 python -m browser_insight.main
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

**macOS / Linux:**

```json
{
  "servers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

**Windows:**

```json
{
  "servers": {
    "browser-insight": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "这里填写项目路径",
        "--python", "3.12",
        "python", "-m", "browser_insight.main"
      ],
      "env": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### OpenCode

在项目根目录创建 `.opencode.json`（或 `~/.config/opencode/opencode.json` 全局生效）：

**macOS / Linux:**

```json
{
  "mcp": {
    "browser-insight": {
      "type": "local",
      "command": [
        "这里填写项目路径/.venv/bin/python",
        "-m",
        "browser_insight.main"
      ],
      "environment": {
        "PYTHONPATH": "这里填写项目路径/src",
        "SILICONFLOW_API_KEY": "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
      },
      "enabled": true
    }
  }
}
```

**Windows:**

```json
{
  "mcp": {
    "browser-insight": {
      "type": "local",
      "command": [
        "这里填写项目路径/.venv/Scripts/python.exe",
        "-m",
        "browser_insight.main"
      ],
      "environment": {
        "PYTHONPATH": "这里填写项目路径/src",
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
PYTHONPATH=这里填写项目路径/src \
uv run --directory 这里填写项目路径 --python 3.12 python -m browser_insight.main
```

**Windows (PowerShell):**

```powershell
$env:SILICONFLOW_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
$env:PYTHONPATH = "这里填写项目路径\src"
uv run --directory "这里填写项目路径" --python 3.12 python -m browser_insight.main
```

**Windows (CMD):**

```cmd
set SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
set PYTHONPATH=这里填写项目路径\src
uv run --directory "这里填写项目路径" --python 3.12 python -m browser_insight.main
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

### 连接问题

**Q: 提示 "无法连接到 Chrome DevTools"**

默认情况下 MCP 会自动启动 Chrome，无需手动操作。如果自动启动失败，请按平台排查：

**所有平台通用检查：**
1. 确认本机已安装 Chrome / Chromium / Brave / Edge 浏览器
2. 确认没有其他程序占用 9222 端口
3. 在浏览器中访问 `http://localhost:9222/json`，如果返回 JSON 说明 CDP 正常
4. 如果关闭了 `auto_launch`，需手动以 `--remote-debugging-port=9222` 参数启动 Chrome

**macOS:**
```bash
# 检查端口占用
lsof -i :9222

# 如果端口被占用，杀掉占用进程
kill -9 $(lsof -t -i :9222)
```

**Linux:**
```bash
# 检查端口占用
ss -tlnp | grep 9222
# 或
lsof -i :9222

# 如果端口被占用
kill -9 $(lsof -t -i :9222)
```

**Windows (PowerShell):**
```powershell
# 检查端口占用
netstat -ano | findstr :9222

# 找到占用端口的 PID 后杀掉进程（将 <PID> 替换为实际进程 ID）
taskkill /PID <PID> /F
```

**Q: CDP 连接超时**

可能原因：
1. Chrome 已打开但所有标签页的 WebSocket 被其他 DevTools 客户端占用 — 关闭其他 DevTools 连接
2. Chrome 标签页处于崩溃状态 — 关闭异常标签页或重启 Chrome
3. 网络代理干扰 — 确认 `localhost` 不走代理

### 安装问题

**Q: Windows 下 `uv run` 报错 `ModuleNotFoundError: No module named 'setuptools.backends'`**

这是旧版本的 `pyproject.toml` 配置问题，已在最新版本修复。请更新到最新代码：

```bash
git pull origin main
```

**Q: `uv` 命令找不到**

**macOS / Linux:**
```bash
# 重新安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 确认 ~/.cargo/bin 在 PATH 中（uv 默认安装到此目录）
echo $PATH | grep cargo

# 如果不在，添加到 shell 配置（bash 用 ~/.bashrc，zsh 用 ~/.zshrc）
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell):**
```powershell
# 重新安装 uv
irm https://astral.sh/uv/install.ps1 | iex

# 重启终端后验证
uv --version
```

**Q: `npm install` 失败**

**macOS / Linux:**
```bash
# 确认 Node.js 版本 >= 18
node --version

# 清除 npm 缓存后重试
npm cache clean --force
cd src/browser_insight/node_worker
rm -rf node_modules package-lock.json
npm install
```

**Windows (PowerShell):**
```powershell
node --version
npm cache clean --force
cd src\browser_insight\node_worker
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
```

**Q: Windows 下 PowerShell 执行策略报错**

如果提示 "无法加载文件 .ps1，因为在此系统上禁止运行脚本"，以管理员身份运行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 运行问题

**Q: 硅基流动 API 调用失败**

向量化使用硅基流动远程 API，不需要下载模型。如果 API 调用失败：

1. 确认 `SILICONFLOW_API_KEY` 已正确设置
2. 确认网络可以访问 `https://api.siliconflow.cn`
3. 如果在国内网络环境下，确认没有被防火墙拦截

**macOS / Linux 验证：**
```bash
curl -s https://api.siliconflow.cn/v1/models | head -c 200
```

**Windows (PowerShell) 验证：**
```powershell
(Invoke-WebRequest -Uri "https://api.siliconflow.cn/v1/models").Content.Substring(0, 200)
```

**Q: Node.js 依赖未安装**

进入 `src/browser_insight/node_worker/` 目录执行 `npm install`：

**macOS / Linux:**
```bash
cd src/browser_insight/node_worker && npm install
```

**Windows:**
```cmd
cd src\browser_insight\node_worker && npm install
```

**Q: Source Map 未还原**

很多生产环境网站不提供 `.map` 文件，此时系统会自动降级为解析混淆代码。搜索结果中会标注来源类型。

### Linux 特有问题

**Q: 无桌面环境（服务器 / Docker）下 Chrome 启动失败**

在 `.mcp_config/config.json` 中开启无头模式：

```json
{
  "chrome_cdp": {
    "headless": true
  }
}
```

或手动启动：
```bash
google-chrome --headless=new --no-sandbox --disable-gpu --remote-debugging-port=9222
```

如果提示缺少依赖库：
```bash
# Ubuntu / Debian
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libasound2

# CentOS / RHEL / Fedora
sudo dnf install -y nss atk at-spi2-atk libdrm libXcomposite libXdamage libXrandr mesa-libgbm pango alsa-lib
```

**Q: Docker 中运行**

Dockerfile 示例：
```dockerfile
FROM node:18-slim

RUN apt-get update && apt-get install -y \
    python3 curl wget gnupg \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libasound2 \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN cd src/browser_insight/node_worker && npm install

ENV PATH="/root/.cargo/bin:$PATH"
ENV PYTHONPATH=/app/src
RUN uv venv --python 3.12 .venv && uv pip install -r pyproject.toml
```

配置中需要开启无头模式：
```json
{
  "chrome_cdp": {
    "headless": true
  }
}
```

### macOS 特有问题

**Q: macOS Gatekeeper 拦截 Chrome 启动**

如果自动启动 Chrome 时被 macOS 安全策略拦截，手动打开一次 Chrome 并允许运行，之后自动启动就不会再被拦截。

**Q: macOS 上 `lancedb` 安装失败（x86_64 架构）**

`lancedb` 在 macOS x86_64（Intel Mac）上可能没有预编译 wheel。解决方案：

```bash
# 如果是 Apple Silicon Mac，确认使用 arm64 版本的 Python
uv venv --python 3.12 .venv
uv pip install lancedb

# 如果是 Intel Mac，尝试从源码编译（需要 Rust 工具链）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
uv pip install lancedb
```

### Windows 特有问题

**Q: Windows 下路径过长导致 npm install 失败**

Windows 默认路径长度限制为 260 字符。如果项目路径较深，可能导致 `node_modules` 中的文件路径超限。

解决方案：
1. 将项目放在较短的路径下，如 `C:\code\auto_js_reverse`
2. 或启用 Windows 长路径支持（需要管理员权限）：

```powershell
# 以管理员身份运行 PowerShell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

重启电脑后生效。

**Q: Windows 防火墙拦截 Chrome CDP 端口**

如果 Chrome 已启动但 `http://localhost:9222/json` 无法访问，可能是防火墙拦截了本地端口。

```powershell
# 以管理员身份运行，添加防火墙入站规则
New-NetFirewallRule -DisplayName "Chrome CDP" -Direction Inbound -LocalPort 9222 -Protocol TCP -Action Allow
```

**Q: Windows 下 Chrome 自动启动后闪退**

可能是用户数据目录冲突。确认没有其他 Chrome 实例在使用相同的用户数据目录：

```powershell
# 关闭所有 Chrome 进程
taskkill /IM chrome.exe /F

# 删除 MCP 使用的 Chrome 用户数据目录后重试
Remove-Item -Recurse -Force storage\chrome_profile
```
