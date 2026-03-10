# auto_js_reverse 测试说明

## 测试分层

项目测试分为三层：

- `unit`: 纯逻辑测试，不依赖真实浏览器、真实网络或外部 API
- `integration`: 集成测试，可能依赖本地 Chrome、Node Worker 或本地配置
- `e2e`: 端到端测试，依赖真实网页与完整链路

## 推荐执行方式

### 只跑单元测试

```bash
python scripts/check_test_env.py --level unit
python -m pytest -m unit
```

### 跑集成测试

```bash
python scripts/check_test_env.py --level integration
python -m pytest -m integration
```

### 跑端到端测试

```bash
python scripts/check_test_env.py --level e2e
python -m pytest -m e2e
```

### 一次跑完整测试分层

```bash
python scripts/check_test_env.py --level all
python scripts/run_tests.py --level all
```

## 推荐脚本入口

如果你希望把环境检查和测试执行串起来，优先使用：

```bash
python scripts/run_tests.py --level unit
python scripts/run_tests.py --level integration
python scripts/run_tests.py --level e2e
python scripts/run_tests.py --level all
```

传递额外 pytest 参数示例：

```bash
python scripts/run_tests.py --level unit tests/test_pipeline_resilience.py
python scripts/run_tests.py --level integration tests/test_new_tools.py
```

## 当前建议

- 日常开发优先跑 `unit`
- 修改浏览器连接、索引、抓取流程时，再补 `integration`
- 修改完整逆向工作流时，再跑 `e2e`
- 在跑 `integration/e2e` 之前先执行环境自检脚本，减少无效排查

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
