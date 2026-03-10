# auto_js_reverse 测试说明

## 测试分层

项目测试分为三层：

- `unit`: 纯逻辑测试，不依赖真实浏览器、真实网络或外部 API
- `integration`: 集成测试，可能依赖本地 Chrome、Node Worker 或本地配置
- `e2e`: 端到端测试，依赖真实网页与完整链路

## 推荐执行方式

### 只跑单元测试

```bash
python -m pytest -m unit
```

### 跑集成测试

```bash
python -m pytest -m integration
```

### 跑端到端测试

```bash
python -m pytest -m e2e
```

## 当前建议

- 日常开发优先跑 `unit`
- 修改浏览器连接、索引、抓取流程时，再补 `integration`
- 修改完整逆向工作流时，再跑 `e2e`

## 环境要求

### unit

- Python 依赖可用
- 不要求真实 Chrome
- 不要求 Embedding Key

### integration

- 本机可启动 Chrome / Chromium
- Node Worker 依赖已安装
- 部分测试可能需要 `.mcp_config/config.json`

### e2e

- 目标网站可访问
- Chrome 可连接 CDP
- Embedding Key 可用
- 网络稳定
