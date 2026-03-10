# auto_js_reverse Skill

## 目标

该 skill 用于配合 `auto_js_reverse` 项目执行浏览器 JavaScript 逆向分析，而不是仓库本地开发流程。

核心目标：

- 抓取当前网页的 JS 资源并归档
- 基于 Source Map、AST 和向量检索定位关键逻辑
- 结合网络监听、函数 Hook、页面执行完成逆向闭环
- 输出可复现的分析过程与结论

## 适用场景

当用户要做以下事情时，启用本 skill：

- 分析某个网页的登录、签名、加密、混淆逻辑
- 定位前端 API 的请求参数生成方式
- 查找页面中的加密函数、关键请求、调用链
- 验证某段 JS 在真实页面上下文中的执行结果

## 使用前检查

在开始分析前先确认：

1. Chrome 或 Chromium 可用
2. 项目的 MCP 服务可正常启动
3. 已配置可用的 Embedding Key
4. 目标页面可以在浏览器中打开

如果用户没有明确提供目标 URL，先要求或推断一个明确页面入口。

## 推荐工作流

### 1. 抓取页面资源

先使用 `capture_current_page`：

- 指定 `storage_path`
- 尽量提供 `target_url`
- 在需要重新分析时开启 `force_refresh`

目标：

- 归档页面 HTML
- 下载脚本资源
- 尝试关联 Source Map
- 建立本地索引

### 2. 查看已归档文件

使用 `list_captured_files`：

- 先看域名下有哪些 JS 文件
- 优先关注体积较大、命名可疑、带 `encrypt`、`sign`、`vendor`、`app` 等关键词的文件

### 3. 快速筛查加密逻辑

先跑 `analyze_encryption`，再补 `search_local_codebase`：

- 用 `analyze_encryption` 初筛常见加密模式
- 用 `search_local_codebase` 搜索如“登录签名”“token 生成”“AES key”“请求加密”等问题

### 4. 阅读关键源码

使用 `read_js_file`：

- 优先读取命中的关键函数附近行号
- 大文件按区间读取，不要一次性读取整文件
- 需要时回溯调用方和上游参数来源

### 5. 捕获真实请求

使用 `capture_network_requests`：

- 对登录、提交、搜索、列表加载等动作进行监听
- 优先关注 `XHR`、`Fetch`
- 重点记录 URL、Header、POST Body、签名参数、时间戳、token

### 6. Hook 关键函数

当怀疑某个函数参与签名、加密或序列化时，使用 `hook_function`：

- 目标示例：`window.encrypt`、`CryptoJS.MD5`、`window.signData`
- 配合 `trigger_action` 主动触发业务动作
- 重点关注入参、返回值、调用栈

### 7. 在页面里验证结论

最后使用 `execute_js`：

- 在真实页面上下文中调用可疑函数
- 对照 Hook 和网络请求结果验证你的逆向假设
- 输出可复现表达式，而不是只给结论

## 分析输出要求

每次分析尽量输出以下内容：

1. 目标页面与分析对象
2. 抓取到的关键文件
3. 命中的函数或代码片段
4. 关键网络请求与参数
5. 推断出的签名或加密链路
6. 还需要验证的疑点

## 常用搜索词

适合直接用于 `search_local_codebase`：

- `登录请求签名`
- `token 生成逻辑`
- `加密函数`
- `请求头 authorization`
- `AES key`
- `md5 sign`
- `timestamp nonce`
- `CryptoJS`
- `JSEncrypt`
- `Base64 encode`

## 逆向时的判断原则

- 先看真实请求，再找生成逻辑，不要反过来盲猜
- 先找业务入口函数，再下钻到通用加密库
- 先验证输入输出，再写还原代码
- 如果 Source Map 不可用，优先结合 Hook 与网络行为缩小范围

## 失败时的回退策略

如果没有搜到结果，按以下顺序回退：

1. 重新 `capture_current_page`，开启 `force_refresh`
2. 改用更具体的 `search_local_codebase` 查询词
3. 用 `capture_network_requests` 先拿到真实请求
4. 根据请求参数名反查代码
5. 对可疑函数执行 `hook_function`

## 注意事项

- `read_js_file` 只读取已归档文件，不能替代随意本地读文件
- `hook_function` 更适合观察运行时真实输入输出
- `execute_js` 适合做结论验证，不适合作为第一步盲试
- 若接口或工具发生变化，必须同步更新 `doc/API.md`
- 任何修改都要同步记录到 `CHANGELOG`
