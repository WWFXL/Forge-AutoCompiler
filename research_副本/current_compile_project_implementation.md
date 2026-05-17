# 自动化编译项目实现方案

## 目标
面向远程仓库编译任务的自动化编译系统：由主 Agent 负责任务理解、流程编排与结果汇总，由 Compiler Subagent 负责容器内编译执行，逐步沉淀编译经验到记忆系统，并为未来 Skill 动态加载预留扩展位。

## 当前实现方案

### 1. Agent 编排
- **Lead Agent**：接收用户编译请求，识别仓库、分支、构建目标和产物要求。
- **Compile Session**：先创建独立 compile session，绑定 thread、repo、container、logs、artifacts。
- **预处理阶段**：完成容器准备、仓库 clone、构建系统识别。
- **Compiler Subagent**：在已绑定的 compile session 中执行真正的编译命令，只操作 `/workspace/repo`。
- **结果回收**：主 Agent 汇总 configure / make 结果、关键日志、二进制位置、复现实验脚本与产物。

### 2. 当前编译链路
1. 用户提出编译任务。
2. Lead Agent 调用 compile 相关工具，建立 session。
3. 系统 clone 仓库并识别构建系统。
4. Lead Agent 通过 `task(..., subagent_type="compiler")` 启动编译子代理。
5. Compiler Subagent 在 compile container 中执行依赖检查、configure、make、日志记录与结果汇总。
6. 最终由 Lead Agent 返回统一结果给用户。

### 3. 当前项目中的记忆系统
- **位置**：通过 `MemoryMiddleware` 挂在主 Agent 执行链上。
- **作用**：记录用户偏好、历史成功经验、纠错信号和有效做法。
- **当前能力**：
  - 记录用户上下文与历史摘要。
  - 注入高置信度 facts 到后续对话。
  - 识别“你理解错了”“重试”“这样就对了”等反馈信号。
- **对编译系统的价值**：后续可沉淀“某类项目常见依赖”“某类 configure 失败应关闭哪些 feature”“用户偏好的产物格式”等经验。

## 未来扩展方向

### 1. Skill 动态加载
未来将把编译流程拆成可插拔 skill，在每个环节补充说明、策略和领域知识：
- **仓库识别 Skill**：识别 CMake / Make / Autotools / Meson 等项目类型。
- **依赖安装 Skill**：根据项目特征动态补充系统依赖、工具链和库依赖说明。
- **构建诊断 Skill**：在 configure 或 make 失败时，提供针对性的排障建议。
- **产物识别 Skill**：自动判断可执行文件、库文件、安装目录和复现脚本。
- **项目特化 Skill**：例如 ffmpeg、linux kernel、compiler、multimedia 项目等专项编译知识。

### 2. Skill 在编排中的位置
- Lead Agent 负责决定当前阶段需要什么能力。
- Skill 作为阶段补充说明注入到 prompt / system prompt / 执行策略中。
- Compiler Subagent 在具体执行前读取对应 Skill，减少盲目试错。
- 记忆系统和 Skill 可组合：Skill 提供通用知识，Memory 保存用户与历史任务经验。

## 推荐的系统定位
- **Lead Agent**：编排者
- **Compiler Subagent**：执行者
- **Memory System**：经验沉淀层
- **Skill System**：阶段知识增强层
- **Compile Session**：任务隔离与可复现载体

## 最终效果
![image-20260421173435775](C:\Users\XL_WWF\AppData\Roaming\Typora\typora-user-images\image-20260421173435775.png)

形成一个统一的编译自动化系统：

- 流程统一，不另起炉灶
- 编译过程可追踪、可复现、可扩展
- 经验可沉淀，能力可通过 Skill 动态增强
- 适合逐步演进为专属自动化编译平台





## 编译系统发展过程

v1：leadAgent -> compileAgent     leadAgent 仅充当意图识别角色，compileAgent大包大揽（compileAgent承担过多任务）

v2：leadAgent -> run-compile-workflow(工具)     leadAgent 调用工作流，固定执行路线，编译阶段启用subagent处理应对不确定的编译错误。（灵活性不好）

