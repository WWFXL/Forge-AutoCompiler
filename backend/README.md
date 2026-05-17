# Forge-AutoCompiler Backend

Forge-AutoCompiler 的 Python 后端：LangGraph agent 运行时 + FastAPI 网关 + 编译核心。

> 这只是简短入口指引。完整指南：
> - **[../README_zh.md](../README_zh.md)** — 项目总览（中文）
> - **[CLAUDE.md](CLAUDE.md)** — 后端架构与开发指南（给 AI 编程助手用）
> - **[../CONTRIBUTING.md](../CONTRIBUTING.md)** — 贡献流程

## 命令

```bash
make install    # uv sync
make dev        # 启动 LangGraph 服务（端口 2024）
make gateway    # 启动 Gateway API（端口 8001）
make test       # PYTHONPATH=. uv run pytest tests/ -v
make lint       # ruff check + ruff format --check
make format     # ruff check --fix + ruff format

# 跑单测
PYTHONPATH=. uv run pytest tests/test_compile_runtime.py -v
```

## 入口

| 模块 | 作用 |
|---|---|
| `packages/harness/deerflow/agents/__init__.py:make_lead_agent` | LangGraph 入口（注册在 `langgraph.json`） |
| `app/gateway/app.py:app` | FastAPI 实例 |
| `packages/harness/deerflow/compile/` | 编译核心 |
| `packages/harness/deerflow/subagents/builtins/compiler_agent.py` | compiler 子代理契约 |
| `packages/harness/deerflow/client.py` | `DeerFlowClient` 进程内嵌入式客户端 |

## 直连端口（不走 nginx）

- LangGraph：http://localhost:2024
- Gateway：http://localhost:8001

## 必读约束

- **Harness/App 边界**：`packages/harness/deerflow/` 不允许 import `app.*`。CI 由 `tests/test_harness_boundary.py` 强制。
- **`HOST_PROJECT_ROOT`**：手动跑后端时必须 export；编译容器创建依赖它。
- **行宽 240**，双引号，4 空格缩进，全量类型注解（见 `ruff.toml`）。

更多见 [CLAUDE.md](CLAUDE.md)。
