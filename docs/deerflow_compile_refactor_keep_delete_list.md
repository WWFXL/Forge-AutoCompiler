# DeerFlow 自动化编译系统改造：保留 / 删除清单

## 文档目的
本文档从“将 DeerFlow 收敛为自动化编译系统”的目标出发，把当前仓库中的目录和关键文件分成三类：
- **必须保留**：删了会直接影响当前编译主链路或基础运行；
- **可选保留**：短期建议保留观察，后续可视改造方向决定；
- **优先删除候选**：和自动化编译目标弱相关，适合后续逐步裁剪。

> 说明：
> - 本清单是面向“自动化编译系统”而不是“通用 Agent 平台”。
> - “可删”不代表现在立刻就删，而是建议在建立最小可运行闭环后，分批裁剪。
> - 删除前最好先做一轮依赖核对和最小链路回归测试。

---

## 一、分类标准

### A. 必须保留
满足以下任一条件：
- 当前编译链路直接依赖；
- 系统启动/配置/运行必需；
- 编译任务的线程隔离、容器执行、日志产物必需；
- 未来短期内明确还要继续扩展。

### B. 可选保留
满足以下特征：
- 不是编译主链路的硬依赖；
- 但当前可能仍被部分功能间接依赖；
- 或未来对编译系统仍有增强价值。

### C. 优先删除候选
满足以下特征：
- 与自动化编译目标关联很弱；
- 更偏原生 DeerFlow 的通用平台能力；
- 删除后可明显降低系统复杂度。

---

## 二、顶层目录与文件清单

| 路径 | 分类 | 处理建议 | 说明 |
|---|---|---|---|
| `backend/` | 必须保留 | 保留 | 核心后端，编译能力、Agent 运行时、网关 API 都在这里 |
| `docker/` | 必须保留 | 保留 | 反向代理与容器化部署主入口 |
| `docs/` | 可选保留 | 部分保留 | 编译相关文档保留，历史/修复类文档可整理 |
| `frontend/` | 可选保留 | 先保留后瘦身 | 若仍需 Web 操作台则保留，但可大幅裁剪页面和组件 |
| `logs/` | 可选保留 | 运行保留，不纳入核心源码 | 运行日志目录，不是核心业务代码 |
| `scripts/` | 必须保留 | 保留主体 | 启动、配置、检查脚本对当前项目很关键 |
| `skills/` | 可选保留 | 保留框架，精简内容 | 技能机制可留，但通用 public skills 大多可删 |
| `temp/` | 可选保留 | 运行保留 | 临时目录，通常不作为核心源码关注 |
| `main.py` | 优先删除候选 | 可忽略/删除 | 当前仅示例打印，无实际业务作用 |
| `pyproject.toml` | 优先删除候选 | 可忽略/后删 | 根目录版本几乎空壳，核心依赖不在这里 |
| `config.example.yaml` | 必须保留 | 保留 | 配置模板，后续需要随着系统收敛一起瘦身 |
| `config.yaml` | 必须保留 | 保留 | 当前运行配置核心文件 |
| `Makefile` | 必须保留 | 保留 | 启动、安装、清理主入口 |
| `README.md` | 可选保留 | 可保留 | 方便理解原始项目定位 |
| `README_zh.md` | 可选保留 | 可保留 | 同上 |
| `Install.md` | 可选保留 | 可保留/后改 | 如果你的部署方式改变，后面要重写 |
| `extensions_config.example.json` | 可选保留 | 视扩展能力决定 | 若不再保留扩展/skills 体系，可后续裁掉 |
| `deer-flow.code-workspace` | 优先删除候选 | 可忽略 | IDE 工作区文件，不影响业务运行 |
| `LICENSE` / `SECURITY.md` / `CONTRIBUTING.md` | 可选保留 | 视项目开源策略决定 | 对运行无影响，但对仓库治理有用 |

---

## 三、`backend/` 目录保留/删除清单

## 3.1 `backend/` 顶层文件

| 路径 | 分类 | 处理建议 | 说明 |
|---|---|---|---|
| `backend/pyproject.toml` | 必须保留 | 保留 | 后端应用依赖定义 |
| `backend/packages/harness/pyproject.toml` | 必须保留 | 保留 | deerflow 核心运行时依赖定义 |
| `backend/langgraph.json` | 必须保留 | 保留 | 注册 `lead_agent` 图入口 |
| `backend/Dockerfile` | 必须保留 | 保留 | 后端镜像构建核心 |
| `backend/uv.lock` | 必须保留 | 保留 | Python 依赖锁文件 |
| `backend/Makefile` | 可选保留 | 可保留 | backend 子模块命令入口 |
| `backend/ruff.toml` | 可选保留 | 建议保留 | lint 配置，方便后续改造期间维护质量 |
| `backend/debug.py` | 优先删除候选 | 视实际用途删除 | 若仅调试临时文件，可后续移除 |
| `backend/README.md` | 可选保留 | 保留参考 | 对理解后端架构有帮助 |
| `backend/docs/` | 可选保留 | 编译相关保留，其余整理 | 子模块文档可筛选整理 |
| `backend/tests/` | 可选保留 | 建议保留 | 后续裁剪时需要测试兜底 |

---

## 3.2 `backend/app/`

### 必须保留

| 路径 | 说明 |
|---|---|
| `backend/app/gateway/` | HTTP API 主入口，前后端与运行时的桥梁 |
| `backend/app/gateway/app.py` | FastAPI 应用装配入口 |
| `backend/app/gateway/routers/threads.py` | 线程状态、清理、历史，对编译任务隔离很重要 |
| `backend/app/gateway/routers/uploads.py` | 若需要上传 patch / 配置 /脚本，必须保留 |
| `backend/app/gateway/routers/artifacts.py` | 编译产物访问核心接口 |
| `backend/app/gateway/routers/runs.py` | 任务执行入口之一 |
| `backend/app/gateway/routers/thread_runs.py` | 线程级运行入口 |

### 可选保留

| 路径 | 说明 |
|---|---|
| `backend/app/gateway/routers/models.py` | 若前端仍需动态读取模型配置则保留 |
| `backend/app/gateway/routers/memory.py` | 若保留记忆系统则保留 |
| `backend/app/gateway/routers/skills.py` | 若你继续走“编译 skill 化”路线可保留 |
| `backend/app/gateway/routers/agents.py` | 若仍支持多 agent / 自定义 agent 可保留 |
| `backend/app/gateway/services.py` / `config.py` / `deps.py` / `path_utils.py` | 大概率仍会被网关主体依赖，短期不要删 |

### 优先删除候选

| 路径 | 说明 |
|---|---|
| `backend/app/channels/` | IM 渠道接入，和编译平台弱相关 |
| `backend/app/gateway/routers/channels.py` | 配套渠道管理接口 |
| `backend/app/gateway/routers/mcp.py` | MCP 配置管理，非编译主链路必需 |
| `backend/app/gateway/routers/assistants_compat.py` | 平台兼容接口，通常可后裁 |
| `backend/app/gateway/routers/suggestions.py` | 问题建议能力，不是编译主链路必需 |

---

## 3.3 `backend/packages/harness/deerflow/`
这是最重要的裁剪区，建议非常谨慎。

### 必须保留

| 路径 | 说明 |
|---|---|
| `backend/packages/harness/deerflow/agents/` | Lead Agent 构建与运行核心 |
| `backend/packages/harness/deerflow/compile/` | 当前自动化编译改造核心 |
| `backend/packages/harness/deerflow/config/` | 配置解析核心 |
| `backend/packages/harness/deerflow/runtime/` | 运行时支撑逻辑 |
| `backend/packages/harness/deerflow/sandbox/` | 文件、路径、线程隔离等能力依赖较深 |
| `backend/packages/harness/deerflow/subagents/` | 你当前的 Compiler Subagent 架构依赖它 |
| `backend/packages/harness/deerflow/tools/` | Agent 可调用工具体系的基础 |
| `backend/packages/harness/deerflow/uploads/` | 上传目录与文件管理能力 |
| `backend/packages/harness/deerflow/utils/` | 底层公共工具，通常被多模块依赖 |

### 可选保留

| 路径 | 说明 |
|---|---|
| `backend/packages/harness/deerflow/models/` | 模型适配层，大概率仍需保留，但后面可以瘦身支持的模型类型 |
| `backend/packages/harness/deerflow/skills/` | 如果继续做“编译技能注入”，则保留框架 |
| `backend/packages/harness/deerflow/tracing/` | 若还要保留 LangSmith / Langfuse 追踪就保留 |
| `backend/packages/harness/deerflow/guardrails/` | 若有安全约束需求，可保留 |
| `backend/packages/harness/deerflow/reflection/` | 若需要 Agent 自检/反思能力则保留，否则后续可删 |
| `backend/packages/harness/deerflow/community/` | 若还用社区版 AIO sandbox 等扩展，则暂时保留 |
| `backend/packages/harness/deerflow/client.py` | 如果需要嵌入式 Python 调用方式，可保留 |

### 优先删除候选

| 路径 | 说明 |
|---|---|
| `backend/packages/harness/deerflow/mcp/` | MCP 能力通常不是编译平台必需 |
| `backend/packages/harness/deerflow/compile_workflow_task_summary.md` | 若只是阶段性说明文档，可整理迁移到 docs 后删除 |

---

## 四、`compile/` 目录：必须保留核心清单

这是你当前最应该重点保护的区域。

| 路径 | 分类 | 说明 |
|---|---|---|
| `backend/packages/harness/deerflow/compile/compile_tools.py` | 必须保留 | 编译工具封装，高层入口 |
| `backend/packages/harness/deerflow/compile/docker_runtime.py` | 必须保留 | 编译容器创建、执行、清理 |
| `backend/packages/harness/deerflow/compile/manager.py` | 必须保留 | compile session 生命周期与日志/产物记录 |
| `backend/packages/harness/deerflow/compile/operations.py` | 必须保留 | prepare / clone / inspect / finalize 等流程动作 |
| `backend/packages/harness/deerflow/compile/paths.py` | 必须保留 | compile 路径组织 |
| `backend/packages/harness/deerflow/compile/schemas.py` | 必须保留 | 编译数据结构定义 |
| `backend/packages/harness/deerflow/compile/__init__.py` | 必须保留 | 模块导出 |

> 结论：`compile/` 整体都应视为 **必须保留**，至少在你完成新的编译架构替换前不要动。

---

## 五、`frontend/` 保留/删除清单

## 5.1 建议保留的最小部分

| 路径 | 分类 | 说明 |
|---|---|---|
| `frontend/package.json` | 必须保留 | 前端依赖入口 |
| `frontend/src/app/workspace/` | 可选保留 | 如果继续保留工作台式交互页面，很有价值 |
| `frontend/src/components/workspace/` | 可选保留 | 聊天、消息、产物、输入框等核心 UI |
| `frontend/src/core/threads/` | 可选保留 | 线程管理逻辑 |
| `frontend/src/core/uploads/` | 可选保留 | 上传能力 |
| `frontend/src/core/artifacts/` | 可选保留 | 编译产物展示 |
| `frontend/src/core/models/` | 可选保留 | 模型列表读取 |
| `frontend/src/core/messages/` | 可选保留 | 消息流逻辑 |
| `frontend/src/hooks/` / `lib/` / `styles/` | 可选保留 | 基础依赖 |

## 5.2 优先删除候选

| 路径 | 说明 |
|---|---|
| `frontend/src/components/landing/` | 官网/落地页展示，不是编译平台核心 |
| `frontend/src/app/page.tsx` | 如果不再需要首页展示，可后续重做或删除 |
| `frontend/src/app/[lang]/docs/` | 文档站页面，非主链路必需 |
| `frontend/src/content/` | 文档内容，若不做站内文档可删 |
| `frontend/src/components/ai-elements/` | 通用 AI 展示组件较多，可按需裁剪 |
| `frontend/src/app/workspace/agents/` | 多 agent 展示页，如果只保留编译 agent 可裁 |
| 一些通用设置页 | 若后续做极简编译控制台，可删减大量设置 UI |

> 建议：前端不要一上来全删。先保留工作台主链路，确认编译流程跑通后，再分区裁剪。

---

## 六、`docker/` 保留/删除清单

### 必须保留

| 路径 | 说明 |
|---|---|
| `docker/docker-compose.yaml` | 生产环境编排核心 |
| `docker/docker-compose-dev.yaml` | 开发环境编排核心 |
| `docker/nginx/` | 前端 / 网关 / LangGraph 统一反向代理 |

### 优先删除候选

| 路径 | 说明 |
|---|---|
| `docker/provisioner/` | 若不使用 Kubernetes sandbox/provisioner，可优先裁掉 |

---

## 七、`scripts/` 保留/删除清单

### 必须保留

| 路径 | 说明 |
|---|---|
| `scripts/serve.sh` | 本地统一启动主脚本 |
| `scripts/docker.sh` | Docker 开发环境主脚本 |
| `scripts/configure.py` | 初始化配置文件 |
| `scripts/config-upgrade.sh` | 配置升级 |
| `scripts/check.py` / `scripts/check.sh` | 环境检查 |
| `scripts/cleanup-containers.sh` | 清理容器 |
| `scripts/wait-for-port.sh` | 启动流程端口等待 |

### 可选保留

| 路径 | 说明 |
|---|---|
| `scripts/deploy.sh` | 如果你仍走原有部署方式则保留 |
| `scripts/tool-error-degradation-detection.sh` | 若仍需要工具错误检测可保留 |

### 优先删除候选

| 路径 | 说明 |
|---|---|
| `scripts/load_memory_sample.py` | 示例类脚本，不是主链路必需 |
| `scripts/export_claude_code_oauth.py` | 特定平台辅助脚本，通常与编译系统无关 |
| `scripts/run-with-git-bash.cmd` | 若不考虑 Windows 特殊工作流，可后删 |

---

## 八、`skills/` 保留/删除清单

## 8.1 技能框架

| 路径 | 分类 | 说明 |
|---|---|---|
| `backend/packages/harness/deerflow/skills/` | 可选保留 | 如果你后续做编译技能化，建议保留框架 |
| `backend/app/gateway/routers/skills.py` | 可选保留 | 若仍允许技能管理/安装，可保留 |
| `skills/` | 可选保留 | 作为技能内容仓库可保留 |

## 8.2 当前 public skills 内容
当前这些几乎都偏通用能力，而不是编译专项：
- `academic-paper-review`
- `bootstrap`
- `chart-visualization`
- `claude-to-deerflow`
- `code-documentation`
- `consulting-analysis`
- `data-analysis`
- `deep-research`
- `find-skills`
- `frontend-design`
- `github-deep-research`
- `image-generation`
- `newsletter-generation`
- `podcast-generation`
- `ppt-generation`
- `skill-creator`
- `surprise-me`
- `vercel-deploy-claimable`
- `video-generation`
- `web-design-guidelines`

### 处理建议
- **技能框架保留**；
- **`skills/public/` 下的大多数现有内容都属于优先删除候选**；
- 后续替换为编译专属 skills，例如：
  - `repo-build-detection`
  - `cmake-build`
  - `autotools-build`
  - `make-build`
  - `build-troubleshooting`
  - `artifact-collection`

---

## 九、`docs/` 保留/删除清单

### 必须保留

| 路径 | 说明 |
|---|---|
| `docs/current_compile_project_implementation.md` | 当前项目源码说明与编译改造说明核心文档 |
| `docs/run_compile_workflow_workflow_mechanism.md` | 编译工作流机制说明，强相关 |

### 可选保留

| 路径 | 说明 |
|---|---|
| `backend/docs/README.md` | 便于理解后端总体文档结构 |
| 其它与当前编译改造直接相关的说明文档 | 可继续沉淀保留 |

### 优先删除候选

| 路径 | 说明 |
|---|---|
| `docs/CODE_CHANGE_SUMMARY_BY_FILE.md` | 更偏阶段性改动记录 |
| `docs/SKILL_NAME_CONFLICT_FIX.md` | 特定问题修复说明，和编译平台关系弱 |
| `docs/plans/` | 若只是历史计划记录，可整理归档后删除 |
| `docs/pr-evidence/` | PR 证据目录，通常不是产品级文档 |

---

## 十、建议的分批删除顺序
为了降低风险，建议按下面顺序裁剪，而不是一次性大删。

### 第一批：删除外围集成能力
目标：先删最不影响编译主链路的东西。
- `backend/app/channels/`
- `backend/app/gateway/routers/channels.py`
- `backend/app/gateway/routers/mcp.py`
- `backend/packages/harness/deerflow/mcp/`
- `docker/provisioner/`（若不用 K8s）

### 第二批：精简 skills 内容
目标：保留技能框架，移除无关技能。
- `skills/public/` 下的大多数通用 skills
- 保留/新增编译专项 skills

### 第三批：裁剪前端展示层
目标：把通用展示型前端收缩为编译工作台。
- landing 页面
- docs 页面
- 多余 ai-elements
- 多余 agents 展示页

### 第四批：收缩网关兼容接口
目标：只保留编译主链路真正使用的 API。
- `assistants_compat.py`
- `suggestions.py`
- 若不用自定义 agent，则评估 `agents.py`
- 若不用动态 skill，则评估 `skills.py`

### 第五批：清理杂项文件
- 根目录 `main.py`
- 根目录轻量 `pyproject.toml`
- 阶段性说明文档
- 低价值辅助脚本

---

## 十一、最小闭环建议保留集
如果你的目标是尽快做出“最小可运行的自动化编译系统”，建议至少保留以下集合：

### 后端最小集
- `backend/app/gateway/`
  - `app.py`
  - `routers/runs.py`
  - `routers/thread_runs.py`
  - `routers/threads.py`
  - `routers/uploads.py`
  - `routers/artifacts.py`
- `backend/packages/harness/deerflow/`
  - `agents/`
  - `compile/`
  - `config/`
  - `runtime/`
  - `sandbox/`
  - `subagents/`
  - `tools/`
  - `uploads/`
  - `models/`
  - `utils/`

### 配置与启动最小集
- `config.example.yaml`
- `config.yaml`
- `backend/langgraph.json`
- `Makefile`
- `scripts/serve.sh`
- `scripts/docker.sh`
- `docker/docker-compose.yaml`
- `docker/docker-compose-dev.yaml`
- `docker/nginx/`

### 文档最小集
- `docs/current_compile_project_implementation.md`
- `docs/run_compile_workflow_workflow_mechanism.md`

---

## 十二、结论
如果你的目标明确是“自动化编译系统”，那么当前 DeerFlow 仓库中：

### 应该优先保住的主链路
- Agent 编排
- compile session
- 编译容器执行
- thread 隔离
- 上传/日志/产物
- 基础前端工作台或 API 接口

### 应该优先裁掉的外围能力
- IM 渠道
- MCP
- 大量通用 public skills
- landing/docs 型前端内容
- 平台兼容类接口

一句话总结就是：
**保住编译执行闭环，裁掉通用平台外延。**

---

## 十三、下一步建议
如果你愿意，我下一步可以继续直接帮你做下面其中一个：

1. **逐文件级别清单**：细化到具体文件，而不是目录级别。
2. **删除顺序执行计划**：给你一份“第一轮删哪些、第二轮删哪些”的操作计划。
3. **最小编译版架构图**：基于保留后的模块，画出收敛后的系统结构。


