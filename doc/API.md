# Browser Insight MCP API 文档

## MCP Tools

### `capture_current_page`

| 属性 | 说明 |
|------|------|
| 功能 | 触发一次完整的全量抓取、归档、分析流程 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `storage_path` | `str` | 是 | 文件存储的绝对路径，所有抓取的 JS 文件将归档到此目录下（按日期/域名/原始路径组织） |
| `target_url` | `str` | 否 | 目标网页 URL，会自动查找已打开的匹配标签页，找不到则新建 |
| `force_refresh` | `bool` | 否 (默认 `false`) | 是否忽略哈希缓存，强制重新解析所有文件 |

**返回:** 简报字符串，包含新增文件数、Source Map 还原数、索引代码块数、实际存储路径。

---

### `search_local_codebase`

| 属性 | 说明 |
|------|------|
| 功能 | RAG 语义检索本地已索引的浏览器 JS 代码库 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `query` | `str` | 是 | 自然语言搜索问题，例如 "用户登录逻辑"、"API 请求签名" |
| `domain_filter` | `str` | 否 | 限制搜索的域名，例如 `example.com` |
| `limit` | `int` | 否 (默认 `10`) | 返回结果数量上限 |

**返回:** Markdown 格式的代码块列表，标注来源为 Source Map 还原或混淆代码。

---

### `list_captured_files`

| 属性 | 说明 |
|------|------|
| 功能 | 列出本地已抓取归档的所有 JS 文件 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `domain_filter` | `str` | 否 | 限制列出的域名，不填则列出所有 |

**返回:** 文件列表，包含 URL、本地路径、文件大小、是否有 Source Map。

---

### `read_js_file`

| 属性 | 说明 |
|------|------|
| 功能 | 读取已抓取的 JS 文件源码，支持指定行范围 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `file_path` | `str` | 否 | JS 文件的本地绝对路径（与 url 二选一） |
| `url` | `str` | 否 | JS 文件的原始 URL（与 file_path 二选一） |
| `start_line` | `int` | 否 (默认 `1`) | 起始行号 |
| `end_line` | `int` | 否 | 结束行号，不填则读到文件末尾 |

**返回:** 带行号的源码内容。

---

### `execute_js`

| 属性 | 说明 |
|------|------|
| 功能 | 在当前浏览器页面上下文中执行 JavaScript 表达式 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `expression` | `str` | 是 | 要执行的 JS 表达式，支持 await 异步 |
| `target_url` | `str` | 否 | 目标页面 URL，不填则使用当前页面 |

**返回:** 表达式执行结果，自动 JSON 序列化。

---

### `capture_network_requests`

| 属性 | 说明 |
|------|------|
| 功能 | 监听浏览器网络请求，捕获 XHR/Fetch/脚本请求 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `target_url` | `str` | 否 | 目标页面 URL |
| `duration` | `float` | 否 (默认 `10.0`) | 监听时长（秒） |
| `trigger_action` | `str` | 否 | 监听开始后自动执行的 JS 代码，用于触发网络请求。不填则自动刷新页面 |
| `filter_type` | `str` | 否 | 过滤请求类型：`XHR`、`Fetch`、`Script` |

**返回:** 请求列表，包含 URL、方法、请求头、POST 数据、响应状态。自动高亮 Authorization/Cookie/签名等关键请求头。

---

### `hook_function`

| 属性 | 说明 |
|------|------|
| 功能 | Hook 页面中指定的 JS 函数，记录调用参数、返回值和调用栈 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `function_path` | `str` | 是 | 函数路径，例如 `window.encrypt`、`CryptoJS.MD5` |
| `target_url` | `str` | 否 | 目标页面 URL |
| `trigger_action` | `str` | 否 | Hook 注入后自动执行的 JS 代码，用于触发目标函数调用 |
| `max_calls` | `int` | 否 (默认 `10`) | 最多记录调用次数 |
| `duration` | `float` | 否 (默认 `15.0`) | 监听时长（秒） |

**返回:** 调用记录列表，包含每次调用的参数、返回值和调用栈。监听结束后自动恢复原函数。

---

### `analyze_encryption`

| 属性 | 说明 |
|------|------|
| 功能 | 扫描已索引代码库，自动识别常见加密/签名模式 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `domain_filter` | `str` | 否 | 限制扫描的域名 |

**检测模式:** MD5、SHA、AES、DES/3DES、RSA、Base64、HMAC、CryptoJS、JSEncrypt、sign/signature、encrypt/decrypt、密钥定义。

**返回:** 按加密类型分组的代码片段列表，附带文件位置和下一步操作建议。

---

## MCP Resources

### `insight://archived-sites`

| 属性 | 说明 |
|------|------|
| 功能 | 列出本地已归档的所有域名和抓取记录 |
| 类型 | Resource |

**返回:** 域名列表，包含文件数和最近抓取时间。

---

## AI 逆向工作流

推荐的 JS 逆向分析流程：

1. **`capture_current_page`** — 抓取目标页面所有 JS 资源并建立索引
2. **`list_captured_files`** — 查看抓取到的文件列表
3. **`analyze_encryption`** — 自动扫描加密模式，快速定位关键代码
4. **`search_local_codebase`** — 语义搜索特定功能（如 "登录请求签名"）
5. **`read_js_file`** — 读取完整的加密函数源码
6. **`capture_network_requests`** — 监听 API 请求，观察加密参数
7. **`hook_function`** — Hook 加密函数，观察实际输入输出
8. **`execute_js`** — 在页面中执行代码验证逆向结果
