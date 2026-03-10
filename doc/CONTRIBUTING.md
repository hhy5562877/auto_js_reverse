# auto_js_reverse 贡献指南

## 目标

本文档用于统一 `auto_js_reverse` 的协作方式，确保贡献内容可维护、可测试、可追踪。

## 基本原则

- 小步提交，不要在一次提交中混入无关改动
- 优先修根因，不做表面绕过
- 代码改动必须同步更新文档
- 面向模块边界设计，避免“巨型函数”和“上帝类”

## 提交流程

1. 先阅读 `README.md`、`doc/API.md`、`CHANGELOG`
2. 理清涉及模块与影响范围
3. 先补测试或先补失败复现
4. 再进行代码修改
5. 同步更新文档与 `CHANGELOG`
6. 本地验证通过后提交

## 文档同步要求

出现以下情况时必须更新文档：

- 修改、新增、废弃 MCP Tool 或 Resource：更新 `doc/API.md`
- 新增流程规范、协作规范：更新 `doc/CONTRIBUTING.md`
- 阶段目标变化：更新 `doc/MILESTONES.md` 与 `doc/ROADMAP.md`
- 任意代码或文件操作：更新 `CHANGELOG`

## 提交规范

提交信息使用 Conventional Commits：

```bash
feat(scope): description
fix(scope): description
docs(scope): description
refactor(scope): description
test(scope): description
chore(scope): description
```

示例：

```bash
fix(pipeline): avoid startup failure without embedding key
feat(skill): add auto_js_reverse analysis skill
docs(roadmap): add project milestones and delivery phases
```

## 代码要求

### 后端

- 外部调用必须有异常处理
- 返回值要保持明确、稳定、可读
- 业务编排、浏览器连接、索引访问、向量能力尽量分层

### 测试

- 纯逻辑优先写成不依赖浏览器和外部 API 的测试
- 真实页面、真实网络、真实 Key 的测试应视为集成或 E2E
- 不要让基础测试依赖 fenbi、baidu、Chrome 实例才能运行

## 推荐分层

- `main.py`: MCP tool / resource 暴露层
- `pipeline.py`: 工作流编排层
- `browser_connector.py`: 浏览器控制层
- `node_bridge.py`: Node Worker 调用层
- `index_manager.py`: 索引访问层
- `embedding_service.py`: 向量服务层

## 提交前检查清单

- 是否修复了根因
- 是否补齐了必要文档
- 是否更新了 `CHANGELOG`
- 是否进行了最小可行验证
- 是否避免引入无关文件
