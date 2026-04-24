# DeerFlow 自动化编译系统源码目录说明书

## 文档目的
本文档用于帮助你从“自动化编译系统改造”的视角快速理解当前 `deer-flow` 项目：
- 先看清项目目录结构；
- 再理解各目录/文件的大致职责；
- 最后判断哪些模块与你当前目标强相关，哪些可能属于原生 DeerFlow 的冗余能力。

本文重点不是逐行源码解释，而是为后续“裁剪原生功能、保留编译链路”提供一份可落地的删改参考。

---

## 一、项目整体定位
`deer-flow` 原生是一个基于 LangGraph 的通用 AI Agent Harness，目标是组合：
- Lead Agent
- Subagents
- Sandbox
- Memory
- Skills
- MCP
- Web / IM 渠道接入
- Frontend 可视化工作台

而你当前的改造方向，是把它逐步收敛为一个**自动化编译系统**。从当前代码来看，仓库里已经开始加入编译相关能力，尤其是：
- `backend/packages/harness/deerflow/compile/`
- `docs/current_compile_project_implementation.md`

这说明当前项目实际上是“**DeerFlow 原生通用 Agent 系统 + 正在接入的自动化编译链路**”的混合状态。

---

## 二、顶层目录结构总览

```text
/workspace/deer-flow
├── backend/                  # Python 后端，核心运行时与 API
├── docker/                   # Docker / nginx / 部署编排
├── docs/                     # 项目文档与改造说明
├── frontend/                 # Next.js 前端工作台
├── logs/                     # 本地运行日志
├── scripts/                  # 启动、配置、检查、部署脚本
├── skills/                   # Skills 提示词能力包
├── temp/                     # 运行时临时目录
├── main.py                   # 根目录示例入口，当前基本无业务意义
├── pyproject.toml            # 根 Python 项目声明，几乎空壳
├── config.example.yaml       # 主配置模板
├── config.yaml               # 实际运行配置
├── Makefile                  # 统一开发/启动命令入口
├── README.md                 # 英文总说明
├── README_zh.md              # 中文总说明
├── Install.md                # 安装引导
├── extensions_config.example.json  # 扩展/技能配置模板
└── deer-flow.code-workspace  # VS Code / Cursor 工作区配置
```

---

## 三、建议先建立的认知分层
如果你准备做删减，建议先按下面 4 层理解：

### 1. 必须保留的“核心运行层”
这部分是 DeerFlow 还能跑起来的基础：
- `backend/packages/harness/deerflow/`
- `backend/app/`
- `config.yaml`
- `scripts/serve.sh`
- `docker/`
- `Makefile`

### 2. 和自动化编译强相关的“编译扩展层”
这是你当前最值得重点保留和继续改造的部分：
- `backend/packages/harness/deerflow/compile/`
- 与 compile session、容器、日志、产物、复现脚本有关的逻辑
- `docs/current_compile_project_implementation.md`

### 3. 原生 DeerFlow 的“通用增强层”
这些不是编译系统必需，但可能还有复用价值：
- `memory/` 记忆能力
- `skills/` 技能注入
- `sandbox/` 文件与命令执行抽象
- `subagents/` 子代理机制
- `uploads/` 上传与文件转换

### 4. 很可能后续可以裁剪的“外围能力层”
如果你想把系统收敛成“编译平台”而不是“通用 Agent 平台”，这部分通常是优先裁剪候选：
- IM 渠道：Feishu / Slack / Telegram / WeCom
- MCP 配置与协议支持
- 大量通用 Skills
- Landing Page / Docs 前端页面
- 一些兼容 LangGraph Platform 的接口

---

## 四、顶层关键文件说明

### 1. `README.md` / `README_zh.md`
项目总说明，偏对外介绍，帮助理解原生 DeerFlow 的产品定位。

### 2. `Makefile`
整个项目最重要的统一命令入口之一，封装了：
- 配置生成
- 环境检查
- 安装依赖
- 本地 dev / prod 启动
- Docker 启动
- 停止与清理

如果你以后想把项目改成“编译系统专用”，通常这里也要同步收敛命令集。

### 3. `config.example.yaml`
最关键的运行配置模板，定义了：
- 模型配置
- 工具组
- sandbox 配置
- memory 配置
- tracing 等

后续裁剪功能时，这个文件会直接决定哪些模块还能被启用。

### 4. `config.yaml`
本地实际运行配置。一般不要直接删除，但需要按你改造后的系统定位逐步瘦身。

### 5. `main.py`
当前只是一个简单示例入口：打印 `Hello from deer-flow!`。从实际项目运行角度看，几乎没有业务作用，属于可忽略文件。

### 6. `pyproject.toml`
根目录 Python 项目声明目前非常轻，更多像占位，不是核心运行依赖来源。真正重要的是：
- `backend/pyproject.toml`
- `backend/packages/harness/pyproject.toml`

---

## 五、`backend/`：最核心的后端目录

```text
backend/
├── app/                  # FastAPI 网关与 IM channel 层
├── docs/                 # backend 子模块文档
├── packages/
│   └── harness/          # DeerFlow 核心运行时包 deerflow
├── tests/                # 测试
├── Dockerfile            # 后端镜像构建
├── langgraph.json        # LangGraph 图注册配置
├── pyproject.toml        # 后端应用依赖
├── Makefile              # backend 子模块命令
├── ruff.toml             # Python lint 配置
└── uv.lock               # Python 锁文件
```

### 你可以把 `backend/` 理解成两层：

#### A. `backend/app/`：网关接入层
职责是对外暴露 API、接收前端请求、管理上传、skills、threads、memory、channels 等。

#### B. `backend/packages/harness/deerflow/`：真正的核心运行时
这里才是 DeerFlow Agent、工具、sandbox、compile、memory 等核心实现所在。

如果后面你要做功能裁剪，通常**优先判断 `backend/app/` 的接口哪些还需要保留**，以及**`deerflow/` 里哪些运行时模块还要继续用**。

---

## 六、`backend/app/` 目录说明

```text
backend/app/
├── channels/             # IM 渠道接入（飞书/Slack/Telegram/企业微信等）
├── gateway/              # FastAPI 网关主应用
└── __init__.py
```

### 1. `backend/app/gateway/`
这是 HTTP API 主入口。

关键文件：

#### `backend/app/gateway/app.py`
FastAPI 应用创建入口，负责：
- 启动时加载配置；
- 初始化 LangGraph runtime；
- 注册所有路由；
- 启动/停止 IM channel 服务；
- 提供 `/health` 健康检查。

可以把它看成“后端总装配入口”。

#### `backend/app/gateway/routers/`
这里按功能拆了很多 API 路由：
- `models.py`：模型列表
- `mcp.py`：MCP 配置管理
- `memory.py`：记忆数据相关
- `skills.py`：技能管理、安装、编辑
- `uploads.py`：文件上传、转换、列出、删除
- `threads.py`：线程数据与历史、清理
- `artifacts.py`：线程产物访问
- `agents.py`：Agent 管理
- `runs.py` / `thread_runs.py`：运行流式任务与兼容接口
- `suggestions.py`：问题建议
- `channels.py`：IM channel 管理
- `assistants_compat.py`：兼容 LangGraph Platform assistants 接口

##### 对自动化编译系统的删改建议
强相关、优先保留：
- `threads.py`
- `uploads.py`
- `artifacts.py`
- `runs.py` / `thread_runs.py`
- 可能保留 `models.py`

可能后续裁剪：
- `mcp.py`
- `channels.py`
- `assistants_compat.py`
- `suggestions.py`
- `skills.py`（若你不再走动态 skill 路线）
- `agents.py`（若不做通用多 agent 配置）

### 2. `backend/app/channels/`
这是 IM 渠道适配层，支持：
- Feishu
- Slack
- Telegram
- WeCom

关键作用：
- 接收消息；
- 转成 DeerFlow 可处理的请求；
- 把响应以流式或最终消息回传。

如果你的目标是“网页界面 + 自动化编译系统”或者“API 驱动的编译平台”，这整个目录大概率都不是核心。

**这是很典型的冗余裁剪候选。**

---

## 七、`backend/packages/harness/deerflow/`：核心运行时总览

```text
backend/packages/harness/deerflow/
├── agents/               # Agent 构建与图运行入口
├── community/            # 社区扩展（如 AIO sandbox 等）
├── compile/              # 自动化编译相关扩展
├── config/               # 配置解析
├── guardrails/           # 安全/约束逻辑
├── mcp/                  # MCP 集成
├── models/               # 模型适配
├── reflection/           # 反思/自检相关能力
├── runtime/              # 运行时序列化等支撑逻辑
├── sandbox/              # 沙箱抽象与实现
├── skills/               # Skills 扫描、安装、管理
├── subagents/            # 子代理执行框架
├── tools/                # 工具集合
├── tracing/              # LangSmith / Langfuse 等追踪
├── uploads/              # 上传文件管理
├── utils/                # 通用工具
├── client.py             # 嵌入式 Python 客户端
└── compile_workflow_task_summary.md
```

这部分是你后续删改时最需要谨慎的区域，因为很多目录存在依赖关系。

---

## 八、自动化编译相关目录：当前最关键

### 1. `backend/packages/harness/deerflow/compile/`
这是你当前改造方向最核心的目录。

```text
compile/
├── compile_tools.py      # 编译工具封装：准备工作区、识别构建系统、结束 session
├── docker_runtime.py     # 编译容器运行时，负责 docker run / exec / copy / cleanup
├── manager.py            # compile session 生命周期与元数据管理
├── operations.py         # 编译操作实现：prepare/clone/inspect 等
├── paths.py              # compile session 路径组织
├── schemas.py            # 编译 session、命令记录、产物等数据结构
└── __init__.py
```

#### 各文件作用
- `compile_tools.py`：偏“高层工具入口”，给 Agent 使用；负责准备编译工作区、clone 仓库、识别构建系统、校验容器视图等。
- `docker_runtime.py`：偏“底层执行器”，直接通过 Docker 创建编译容器，并在容器中执行命令。
- `manager.py`：偏“状态管理器”，维护 `session_id`、状态流转、命令记录、artifact 记录、workflow 日志等。
- `operations.py`：偏“编译流程动作库”，提供 prepare/clone/inspect/finalize 等逻辑。
- `paths.py`：统一 compile 相关路径，避免路径散落。
- `schemas.py`：定义 compile session 与命令/产物结构，是后续扩展数据库化或 API 化的重要基础。

#### 这部分的重要性
如果你要把 DeerFlow 真正变成自动化编译系统，这个目录基本属于**绝对核心保留区**。

### 2. `docs/current_compile_project_implementation.md`
这是你当前项目方向说明文档，已经明确了：
- Lead Agent 负责理解和编排；
- Compiler Subagent 负责容器内编译；
- Compile Session 负责隔离 thread/repo/container/logs/artifacts；
- 后续想结合 memory 和 skills。

这份文档不是运行代码，但它非常重要，因为它等于“当前编译改造路线图”。建议保留。

---

## 九、Agent 运行核心：`agents/`

### `backend/packages/harness/deerflow/agents/`
这个目录是 DeerFlow 的 Agent 引擎核心。

你当前至少需要知道这几件事：
- `make_lead_agent` 是 LangGraph 注册的主图入口；
- `langgraph.json` 把 `lead_agent` 注册为运行图；
- Agent 初始化时会加载 middleware、skills 缓存、模型等；
- 线程状态、沙箱状态等也围绕这里组织。

#### 关键文件
- `agents/__init__.py`：导出 `make_lead_agent`、checkpointer 等，并预热已启用 skills 缓存。
- 其它子目录/文件会继续负责 lead agent 的 prompt、factory、thread state、checkpointer 等。

#### 对你的意义
如果未来你依然保留“主 Agent 编排 + 编译子代理执行”架构，那么 `agents/` 一定要保留。

但如果以后你决定完全弱化通用 Agent，改造成固定流程编排器，那么这里可能会从“核心业务层”降级为“底层宿主框架层”。

---

## 十、`sandbox/`：沙箱抽象层
DeerFlow 原生非常依赖 sandbox 概念。

作用大致包括：
- 文件读写
- 目录浏览
- shell 命令执行
- 路径映射
- thread 级隔离

对于你的自动化编译系统，`sandbox/` 依然有价值，因为：
- 编译前后都需要线程隔离；
- 上传文件、产物、日志、工作目录都依赖路径与文件抽象；
- 只是你现在又额外引入了 `compile/docker_runtime.py` 这种“专用编译容器”。

### 判断建议
- 如果编译流程最终完全走 compile container，且不再依赖通用 sandbox 工具执行 bash，则可以逐步弱化原生 sandbox 的某些能力。
- 但不要一开始就删，因为 uploads、file tools、thread 数据目录等很可能还依赖它。

---

## 十一、`subagents/`：子代理机制
这个目录负责 DeerFlow 的多代理并行/委派能力。

你的当前改造方案里已经明确：
- Lead Agent
- Compiler Subagent

所以 `subagents/` 对你的编译系统是有直接价值的，不建议轻易删除。

但要注意：
- 原生 DeerFlow 可能支持更泛化的 subagent 体系；
- 你后续可以把它收缩成“只保留 compiler subagent”这一路。

---

## 十二、`skills/`：技能系统
分两部分看：

### 1. 运行时代码：`backend/packages/harness/deerflow/skills/`
负责：
- 扫描 skills 目录
- 加载 `SKILL.md`
- 安装 `.skill` 包
- 管理启用/禁用状态
- 刷新 system prompt 缓存

### 2. 实际技能文件：`/skills/public/*/SKILL.md`
目前仓库自带很多通用 skill，例如：
- `deep-research`
- `data-analysis`
- `image-generation`
- `podcast-generation`
- `ppt-generation`
- `frontend-design`
- `code-documentation`
等。

### 对编译改造的判断
如果你后续真的要做“编译知识技能化”，那 skill 系统可以保留，但**公共 skills 大量内容基本都不是编译系统必需**。

所以这里可以拆成两层处理：
- **保留技能框架代码**；
- **大量删除无关 public skills 内容**。

这是一个高价值的瘦身方向。

---

## 十三、`memory/` 相关能力
记忆能力虽然没有单独作为顶层目录出现，但从 README 和 gateway 路由可以确认其存在，并通过中间件接入。

作用：
- 记录用户偏好；
- 积累历史上下文；
- 提取高置信度事实；
- 注入后续 prompt。

### 对自动化编译系统的价值
这块不属于“必删项”，反而有潜力：
- 记住某类项目常见依赖；
- 记住某用户偏好的编译参数；
- 记住某仓库历史编译踩坑经验。

所以这部分建议：
- 短期先保留；
- 后续如果觉得复杂度过高，再评估是否缩减。

---

## 十四、`mcp/`：模型上下文协议集成
`mcp/` 和 `gateway/routers/mcp.py` 用于接入 MCP Server。

对于一个自动化编译平台，这通常不是必需能力，除非你打算：
- 动态接入外部工具系统；
- 把更多编译能力外包给 MCP server；
- 做插件式外部能力扩展。

否则它更偏原生 DeerFlow 的通用扩展能力。

**大概率属于可裁剪候选。**

---

## 十五、`uploads/`：上传文件管理
### 相关位置
- `backend/app/gateway/routers/uploads.py`
- `backend/packages/harness/deerflow/uploads/`

作用：
- 文件上传到 thread 目录；
- 列表、删除；
- 某些格式自动转 Markdown；
- 同步到 sandbox。

### 对编译系统的价值
如果你的编译任务允许用户上传：
- patch
- build script
- config file
- dependency file
- log file

那这部分就很有价值。

如果你的系统只接收 Git 仓库 URL，不接受附件，那么上传系统可以缩减，但通常不建议第一批就删。

---

## 十六、`frontend/`：前端工作台

```text
frontend/
├── public/
├── scripts/
├── src/
├── package.json
├── next.config.js
├── tsconfig.json
└── ...
```

前端基于 Next.js 16 + React 19，体量不小。

### `frontend/src/` 主要结构
```text
src/
├── app/               # 路由页面
├── components/        # UI 组件
├── content/           # 文档内容
├── core/              # 前端核心业务逻辑
├── hooks/             # React hooks
├── lib/               # 工具库
├── server/            # 服务端相关，如认证
├── styles/            # 样式
├── typings/           # 类型声明
├── env.js             # 环境变量封装
└── mdx-components.ts
```

### 前端中哪些是“可能冗余”的
如果你以后只需要一个简化版编译面板，那么以下内容很可能可裁：
- Landing 页面相关：`components/landing/`
- 大量通用 AI Elements：`components/ai-elements/`
- Docs 页面：`app/[lang]/docs/`、`content/`
- 多 Agent 画廊：`app/workspace/agents/`
- 很多通用设置项页面

### 哪些更可能保留
- `app/workspace/chats/`
- `components/workspace/`
- artifact 展示相关
- 输入框、消息流、线程列表等

### 你的实际策略建议
如果你当前重点是后端编译链路，而不是 UI，前端可以先**只做最小保留**，不要过早重构。

---

## 十七、`docker/`：容器部署与 nginx 反向代理

```text
docker/
├── nginx/
├── provisioner/
├── docker-compose.yaml
└── docker-compose-dev.yaml
```

### 作用
- `nginx/`：统一反向代理前端、gateway、langgraph。
- `docker-compose.yaml`：生产环境编排。
- `docker-compose-dev.yaml`：开发环境编排。
- `provisioner/`：Kubernetes 模式下的 sandbox provisioner。

### 对编译系统的判断
- `nginx` 与 compose 编排通常仍然有用；
- `provisioner/` 如果你不用 K8s sandbox，则是明显可裁候选。

---

## 十八、`scripts/`：启动与维护脚本

关键脚本：
- `configure.py`：生成 `config.yaml`、`.env` 等初始配置
- `serve.sh`：统一本地启动脚本，非常重要
- `docker.sh`：Docker 开发环境入口
- `config-upgrade.sh`：配置升级
- `check.py` / `check.sh`：环境检查
- `cleanup-containers.sh`：清理容器
- `deploy.sh`：部署脚本
- `wait-for-port.sh`：等待端口可用
- `load_memory_sample.py`：加载记忆样例
- `export_claude_code_oauth.py`：Claude Code OAuth 导出
- `tool-error-degradation-detection.sh`：工具错误检测

### 对编译系统的删改建议
强烈建议保留：
- `serve.sh`
- `docker.sh`
- `configure.py`
- `config-upgrade.sh`
- `cleanup-containers.sh`
- `wait-for-port.sh`

可能后续可删：
- 与特定平台或特定开发者工作流强绑定的辅助脚本
- `load_memory_sample.py`
- `export_claude_code_oauth.py`

---

## 十九、`skills/` 顶层目录：实际技能内容仓库
当前只有：

```text
skills/
└── public/
```

下面有 20 个 public skills，例如：
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
- `video-generation`
- `web-design-guidelines`
- `vercel-deploy-claimable`

这些大部分和“自动化编译”无关。

### 非常建议的整理方向
你可以后续把 `skills/public/` 收敛成例如：
- `repo-build-detection`
- `cmake-build`
- `autotools-build`
- `make-build`
- `build-troubleshooting`
- `artifact-collection`

而把当前这些通用内容大规模移除。

---

## 二十、`docs/`：文档目录
当前包含：
- `current_compile_project_implementation.md`：当前编译改造方案，强相关
- `run_compile_workflow_workflow_mechanism.md`：编译工作流机制文档，强相关
- `CODE_CHANGE_SUMMARY_BY_FILE.md`：改动说明
- `SKILL_NAME_CONFLICT_FIX.md`：技能相关修复说明
- `plans/`：计划类文档
- `pr-evidence/`：PR 证据目录

### 对你来说最有价值的
优先保留：
- 编译实现说明
- 编译工作流说明
- 与当前改造直接相关的文档

其余偏 PR 过程或临时说明的内容，可以后续整理归档或删除。

---

## 二十一、运行链路简化理解
如果只从“自动化编译系统”角度看，目前项目运行链路大致是：

1. 前端或用户请求进入系统
2. `backend/app/gateway/app.py` 启动的网关接收请求
3. LangGraph 使用 `langgraph.json` 注册的 `lead_agent`
4. `deerflow.agents.make_lead_agent` 构建主 Agent
5. 主 Agent 结合模型、middleware、tools、skills、memory 执行
6. 在编译场景下，调用 `deerflow.compile.*` 相关能力建立 compile session
7. 通过 compile container 进行 clone / inspect / build / artifact 收集
8. 结果再回传到前端或其他接入端

---

## 二十二、当前“保留 / 观察 / 优先裁剪”建议

### A. 建议重点保留
- `backend/packages/harness/deerflow/compile/`
- `backend/packages/harness/deerflow/agents/`
- `backend/packages/harness/deerflow/subagents/`
- `backend/packages/harness/deerflow/sandbox/`
- `backend/packages/harness/deerflow/config/`
- `backend/app/gateway/` 中与 threads / uploads / artifacts / runs 相关部分
- `docker/` 中 nginx 与 compose 主体
- `scripts/serve.sh`
- `scripts/docker.sh`
- `config.example.yaml` / `config.yaml`
- `docs/current_compile_project_implementation.md`

### B. 建议先观察，再决定是否删
- `memory` 相关能力
- `skills` 框架代码
- `uploads`
- `models`
- `tracing`
- `reflection`
- `guardrails`

### C. 很可能可优先裁剪
- `backend/app/channels/`
- `backend/app/gateway/routers/channels.py`
- `backend/app/gateway/routers/mcp.py`
- `backend/app/gateway/routers/assistants_compat.py`
- `backend/packages/harness/deerflow/mcp/`
- `skills/public/` 下大多数通用技能
- `frontend` 中 landing/docs/多余 agent 展示页面
- `docker/provisioner/`（若不用 K8s sandbox）
- 若无实际用途，`main.py` 和根目录轻量 `pyproject.toml` 也可以忽略或清理

---

## 二十三、建议你的下一步整理方式
为了后续删文件更稳，建议你下一轮按下面方式继续推进：

### 第一步：建立“编译系统最小闭环清单”
先只保留能够完成以下动作的模块：
- 输入仓库 URL
- 创建 thread / compile session
- clone 仓库
- 识别构建系统
- 执行编译
- 收集日志与 artifact
- 返回结果

### 第二步：把目录分成三类
你可以在后续继续让我帮你做更细的表格，例如：
- **必须保留**
- **可选保留**
- **可删除候选**

### 第三步：按目录分批裁剪
建议删除顺序：
1. IM 渠道
2. MCP
3. 通用 public skills
4. 前端 landing/docs
5. 非必要兼容接口

这样风险最小。

---

## 二十四、结论
当前 `deer-flow` 并不是一个纯编译系统，而是一个通用 Agent 平台上叠加了自动化编译能力。

对你后续改造最重要的判断是：
- **保住 Agent 编排、线程隔离、编译 session、容器执行、日志产物这条主链路；**
- **逐步裁掉 IM、MCP、通用 skills、前端展示性页面这些外围能力。**

如果你愿意，我下一步可以继续直接帮你输出第二份文档，例如：
1. `docs/deerflow_compile_refactor_keep_delete_list.md`：逐目录“保留/可删”清单
2. `docs/deerflow_backend_dependency_map.md`：后端模块依赖关系图
3. `docs/deerflow_compile_minimal_architecture.md`：收敛成自动化编译系统后的最小架构说明
