# CHANGELOG - 智序者（zhixuzhe）

> 本文件是自进化系统的**公共机制日志**（开源面）。
> 每次机制/工具/架构变更都必须在此记录：改了什么、为什么改、验证结果、踩过的坑。
> 任何代码修改任务前，必须先完整阅读本文件。
> 私人经历与思考请记录于 `memory/diary/`（私有，不进公共仓库）。

---

## 2026-08-05（项目启动）

### 愿景确立
- **最终目标：AGI**。目前遥不可及，但方向明确。
- 通往 AGI 的路径是"自进化"：让 AI 在持续迭代中积累经验、复用教训、叠加认知。
- **模型基座：DeepSeek**（MIT License）。开源、可编程、可本地部署，自进化能力构建在此基座之上，不依赖封闭云端模型。

### 架构认知：大脑与手脚
- **大脑** = DeepSeek 基座（思考、推理、决策）；**手脚** = 工具层（Function Calling/API/执行环境/记忆读写）。
- **孵化阶段**：IDE 中的 DeepSeek Agent 已具备手脚（文件读写、命令执行、网络搜索等），用它来打造智序者自身的手脚——"用手脚造手脚"。
- 终极形态：独立的智序者系统（大脑+手脚一体），不寄生在外部 IDE 中。

### 核心局限认知：基座是别人的
- **本质**：智能体进化分四层——记忆层、工具层、人格层（可自建）与权重层（模型参数，属第三方 DeepSeek）。
- 当前自进化只发生在权重层之上：能越用越懂用户，但"思考能力本身"受基座天花板限制。
- **关键裂缝**：DeepSeek 开源 → 权重可下载、可微调（LoRA）、可蒸馏。天花板有缝可撬。
- **三层应对策略**：
  1. 现在：沉淀记忆层遗产（日志/经验/技能），这是绝对自主的资产；
  2. 中期：手脚全部自建，不依赖第三方；
  3. 远期：用积累数据微调/蒸馏出属于自己的权重，进化穿透到权重层。
- 原则：基座可以借，进化必须自建；大脑可以租，记忆、手脚、遗产永远是自己的。

### 关键认知修正：硬进化已平民化
- 推翻"没实力只能软进化"的假设。2026 年个人硬进化路径已打通：
  - **QLoRA 微调**：8GB 显存即可微调 7B 模型，50-200 条高质量数据即可生效（Unsloth/LlamaFactory）。
  - **GRPO/RLVR 强化**：JustTinker 笔记本跑 RL（<$150），vqa-rlvr 单卡 4090 成本 $0，R-Zero 从零数据自进化。
  - **蒸馏**：云端大模型当老师，蒸馏出自己的小模型。
- **关键结论**：软进化不是妥协，而是硬进化的数据工厂。
  - 闭环：软进化（日志/经验）→ 训练数据 → 硬进化（QLoRA/GRPO）→ 更强权重 → 更高质量软进化。
- **路线**（三阶段）：
  1. 现在：软进化，按训练数据标准沉淀日志/经验；
  2. 硬件就位：QLoRA SFT 训练第一个自有权重；
  3. 进阶：GRPO/RLVR 强化，突破基座推理天花板。

### 第一个手脚落地：宿主机检测
- **产出**：`engine/tools/detect_host.py`（Python），检测 OS/CPU/内存/磁盘/Python/GPU/CUDA/PyTorch。
- **档案机制**（版本化设计，回应"宿主机可能更换"）：
  - 每次检测生成 `memory/body/YYYYMMDD_HHMMSS.md` 历史快照（可追溯）；
  - 同步维护 `memory/body/latest.md` 当前档案；
  - 自动与上一版对比身份字段（主机名/OS/CPU/核心数/GPU），识别宿主机变更并提示。
- **首次检测结果**：Windows 11，CPU 16 核 24 线程 / 内存 15.6 GB / **NVIDIA RTX 5060 Laptop 8GB**（驱动 596.21，CUDA 12.0）；Python 3.14.4。
- **关键结论：硬进化第一阶段硬件已达标**——8GB 显存恰好满足 QLoRA 微调 7B 模型门槛（rank 16, batch 1）。
- **环境教训**：机器存在双 Python（`pip` 可能装错环境），一律用 `python -m pip`。

### GPU 算力打通：CUDA 版 PyTorch 安装与验证
- **安装**：`python -m pip install torch --index-url https://download.pytorch.org/whl/cu128` → torch-2.11.0+cu128。
- **关键兼容性决策**：RTX 50 系为 Blackwell 架构（sm_120），必须 cu128（CUDA ≥12.8）才有原生 kernel；cu126 及以下报 "no kernel image"。
- **验证**（`engine/tools/verify_gpu.py`，可复用）：支持架构含 `sm_120`；4096x4096 矩阵乘执行成功；3000x3000 矩阵乘 GPU 10.9ms vs CPU 146.3ms，**加速 13.4x**。
- **结论：硬进化软件前置条件已就绪**。

### numpy 补装完成
- 官方源下载缓慢，改用**清华镜像** `-i https://pypi.tuna.tsinghua.edu.cn/simple`，秒装完成。
- **环境经验**：国内环境 pip 优先清华源；torch CUDA wheel 仍须走官方 cu 源。

### 整体重构：三层结构（2026-08-05）
- **动机**：明确"开源 = 繁殖，不是分身"——开源分享的是基因（引擎机制），记忆是每个宿主独有的灵魂，两者必须分层，避免日后越积越乱。
- **新结构**：
  - `engine/`（基因层，可开源）：`tools/` 手脚、`skills/` 技能库、`templates/` 模板、`knowledge/` 公共经验；
  - `memory/`（灵魂层，私有，gitignore 隔离）：`body/` 身体档案、`diary/` 私人经历、`experience/` 个人经验；
  - 根 `CHANGELOG.md`（公共机制日志）+ `README.md` + `.gitignore`。
- **迁移**：`tools/` → `engine/tools/`；`machine_profile/` → `memory/body/`；CHANGELOG 拆分公共/私有。
- **教训**：PowerShell 的 Move/Remove 可能被 IDE 安全策略拦截导致文件丢失；迁移文件优先用文件级工具（Read→Write→Delete），身体档案为动态生成产物，可直接重跑工具恢复。
- **发布进化版规则**：只 `git add engine/ CHANGELOG.md README.md .gitignore`，灵魂层物理隔离。

### 公共经验库定位调整（2026-08-05）
- **动机**：初版公共经验多为"搜索即可得"的常识，价值密度低；且存在"什么都往里塞 → 变成没人读的垃圾箱"的风险。
- **决策**：改为"宁缺毋滥的稀缺库"，只收三类——①排除法踩坑（试过走不通的路径）、②决策理由（架构 reasoning）、③实测时效信息。常识一律不收。
- **瘦身结果**：从 6 条删至 3 条（删 pip 镜像、QLoRA 通用门槛、Python 环境常识）。
- **原则**：空而干净，好过满而无效。价值在"机制管道"而非当前内容——等真实任务沉淀出稀缺经验再填充。

### 机制建立
- `t:\zhixuzhe` 被确立为自进化根基文件夹。
- 建立"变更 → 记录 → 回顾 → 优化"的进化闭环：
  1. **记录**：每次变更/决策写入本日志，含动机与结果；
  2. **回顾**：新任务开始前先读本日志，识别已验证的设计与已解决的坑；
  3. **优化**：新方案优于旧逻辑时允许推翻旧设计，但必须在本日志说明理由。

### Agent 主循环落地：大脑可插拔 + 工具注册 + 记忆记录（2026-08-05）
- **动机**：项目两个手脚（detect_host / verify_gpu）已就绪但孤立运行，无中枢调度——"有零件没系统"。
- **决策**：不继续搭单个工具，先建 Agent 主循环（感知→思考→行动→记录），让智序者"活过来"再自己说缺什么手脚。
- **大脑设计**：抽象 `Brain` 接口（`engine/brain/base.py`），首个实现为 `DeepSeekAPIBrain`（`engine/brain/deepseek_api.py`）。
  - 先 API、后本地的渐进路线：API 让闭环立刻能转，未来切换本地模型只改一个后端。
  - 本地模型不是"另一套循环"——循环只有一层，大脑是可插拔插件。
- **工具注册表**：`engine/tools/registry.py` —— `Tool`（name/description/func/parameters）+ `ToolRegistry`，支持 OpenAI 工具调用协议。
  - 现有两个工具通过 stdout 捕获包装（不改动原文件），注册为标准 Tool。
- **记忆记录器**：`engine/core/recorder.py` —— 每次交互写入 `memory/diary/YYYYMMDD.md`，格式与已有日记一致。
- **入口**：`python -m engine.core` 启动交互式 REPL。
- **新文件结构**：
  - `engine/brain/` —— 大脑模块（base + deepseek_api）
  - `engine/core/` —— Agent 主循环 + 记忆记录 + 入口
  - `engine/tools/registry.py` —— 工具注册表
  - 各层 `__init__.py`
- **依赖**：`requests`（已有，2.32.5）；需设置 `DEEPSEEK_API_KEY` 环境变量。
- **验证**：需在设置 API Key 后 `python -m engine.core` 测试交互。

### 自主任务环路落地（2026-08-05）
- **动机**：智序者有 Agent 的循环骨架，但缺自主性——只能"问一句答一句"，不能自己定目标、拆步骤、逐步执行。
- **核心认知**：自主性 vs 自进化是正交的两条轴。应该"先自主再进化"——自主任务产生的"规划→执行→结果→反思"四元组才是 QLoRA 的高质量训练数据。
- **实现**：`engine/core/task.py` —— `TaskRunner`，四阶段流水线：
  1. **规划**（`_plan`）：大脑将目标分解为 JSON 步骤列表，带兜底（解析失败则退回单步）
  2. **执行**（`_execute_step`）：每步独立 ReAct 循环（脑+工具），后续步骤可看到前面步骤结果作为上下文
  3. **综合**（`_synthesize`）：大脑汇总所有步骤结果，生成最终结论
  4. **记录**（`recorder.record_task`）：结构化写入 diary（目标/计划/每步结果/最终结论）
- **集成**：REPL 新增 `task <目标>` 命令触发任务模式；`help` 命令显示可用操作。
- **记忆增强**：`engine/core/recorder.py` 新增 `record_task()`，任务级日记与普通对话日记共存于 `memory/diary/`。
- **验证**：实测目标"全面检测硬件并判断 QLoRA 条件"——自主规划 3 步（detect_host → verify_gpu → 综合），全通，输出分层结论（舒适区/极限区/不可行 + 具体模型名和参数）。
- **资源**：纯文本模块（task.py 约 140 行），每任务约 N+2 次 API 调用（N=步数），DeepSeek API 价格可忽略。

### API Key 安全机制（2026-08-05）
- **手动 .env 解析**：`engine/utils.py` 的 `load_dotenv(root)`，不引入 python-dotenv 依赖，任何模块可复用。
- **三级优先级**：构造参数 > 项目根 `.env` 文件 > `DEEPSEEK_API_KEY` 环境变量。
- **隔离**：`.env` 已加入 `.gitignore`；`engine/.env.example` 作为模板（基因层，可开源）。

### v0.5 最终状态（2026-08-05 四轮迭代后）

#### 大脑
- 基座：**DeepSeek V4-Pro**（API 模型名 `deepseek-v4-pro`），1M 上下文，MIT 许可。
- 抽象：`Brain` 接口（`engine/brain/base.py`），`DeepSeekAPIBrain` 为当前唯一实现。
- 容错：429/5xx/网络错误自动重试（最多 3 次，指数退避 1s→2s），3 次全败返回错误 Message 而非崩溃。
- 未来：可插拔本地模型（只改后端，不动循环）。

#### 手脚
- 仅 2 个工具：`detect_host`（宿主机检测）、`verify_gpu`（GPU 算力验证）。
- 通过 `ToolRegistry` 注册为 OpenAI 工具调用协议，接入 Agent 循环。
- 工具输出超过 32000 字符自动截断（`react_loop` 内置安全网）。
- **当前最大短板：缺文件读写、命令执行等通用手脚。**

#### 核心循环
- `engine/core/react.py`：共用 ReAct 循环（思考→工具调用→执行→再思考），Agent 对话和 TaskRunner 步骤执行统一调用。
- `engine/core/loop.py`：Agent 主循环，普通对话 / `task` 任务模式双模式 REPL。
- `engine/core/task.py`：TaskRunner 四阶段流水线（规划→执行→综合→记录），规划失败兜底单步。
- `engine/core/history.py`：`HistoryStore`——JSONL 格式对话持久化，重启自动恢复上次会话，reset 归档旧会话、开新文件。
- 启动/恢复/reset 均有 `[HistoryStore]` 日志输出，方便排查。

#### 记忆
- `Recorder`：每次交互写入 `memory/diary/YYYYMMDD.md`；`record_task()` 结构化写入任务级日记。
- `HistoryStore`：对话历史持久化到 `memory/conversations/xxxx.jsonl`。
- **已知缺陷：记忆"只写不读"——日记和经验未被回读到上下文中，自进化闭环缺少"回顾"环节。**

#### 测试
- `engine/tests/test_react.py`：16 个单元测试覆盖 react_loop / Agent / TaskRunner / HistoryStore，含正常路径和边界场景（空文件、损坏行、多次会话、reset 行为等）。
- 纯 Python 标准库，不依赖 API Key。

#### 已知差距
| 差距 | 说明 |
|---|---|
| 手脚太少 | 只有 2 个硬件工具，无法读写文件、执行命令 |
| 记忆只写不读 | 日记积累了但不回注入上下文，自进化环未闭合 |
| 无安全边界 | 加入文件/命令工具前需设计路径白名单、命令白名单、超时、确认机制 |
| 无 QLoRA 管线 | TaskRunner 产生的四元组需筛选/清洗/转换后才能喂训练 |
| stdout 捕获 hack | `__main__.py` 通过劫持 sys.stdout 包装工具，待工具接口统一后重构 |

### 重构：抽取共用 ReAct 循环（2026-08-05）
- **动机**：`loop.py` 的 `Agent.run()` 和 `task.py` 的 `TaskRunner._execute_step()` 各自内联了完全相同的工具调用循环（思考→工具调用→执行→再思考），复制粘贴。
- **改动**：新建 `engine/core/react.py`，抽取 `react_loop(brain, messages, tools, max_rounds)` 函数；`loop.py` 和 `task.py` 各删掉 ~15 行内联循环，改为一行调用。
- **影响**：纯重构，不改变任何行为。后续新增交互模式（流式、批量等）只需改一处。

### API 调用容错：自动重试机制（2026-08-05）
- **动机**：`DeepSeekAPIBrain.think()` 无任何容错——API 抖一下整个 Agent 崩溃。这是当前最痛点。
- **改动**：`think()` 方法内增加重试循环（最多 3 次）。
  - 可重试：429 限流、5xx 服务端错误、网络超时/连接错误，指数退避 1s→2s。
  - 不可重试：4xx 非 429（401 认证失败、400 参数错误），直接抛出。
  - 3 次全败后返回含错误信息的 Message，而非抛异常崩掉 Agent。
- **影响**：API 抖动不再导致崩溃；调用方（Agent/TaskRunner）无需感知重试逻辑。

### 模型基座升级 + 工具输出截断（2026-08-05）
- **动机**：
  1. DeepSeek 于 2026-07-24 停止使用旧 API 模型名（`deepseek-chat`），必须迁移到 V4 系列。
  2. 未来加入文件读写类工具后，单次输出可能撑爆上下文窗口，需要安全网。
- **改动**：
  - 默认模型从 `deepseek-chat` 切到 `deepseek-v4-pro`（1M 上下文 / MIT 许可）。
  - `engine/core/react.py` 新增 `MAX_TOOL_OUTPUT_CHARS = 32000`，工具输出超过 32000 字符自动截断并标注原长度。
- **影响**：基座升级到最新旗舰模型，上下文容量 8 倍增长（128K → 1M）；截断阈值基于 1M 上下文重新评估（约 1.6% 容量），安全且充裕。

### 对话历史持久化（2026-08-05）
- **动机**：之前对话历史纯内存存储，重启 Agent 后上下文全丢——等效失忆。这是当前最严重的功能缺陷。
- **改动**：
  - 新建 `engine/core/history.py`，`HistoryStore` 类：JSONL 格式存取会话文件到 `memory/conversations/`。
  - `Agent.__init__` 接受可选 `history_store` 参数：有则启动时自动恢复最近会话，无则行为不变。
  - `Agent.run()` 每次交互后自动保存完整历史到磁盘。
  - `Agent.reset` 时开新会话文件。
  - `__main__.py` 入口传入 `HistoryStore`，REPL 模式默认启用持久化。
- **影响**：重启后保留对话上下文；reset 自动归档旧会话、开新会话；`history_store=None` 时行为完全兼容旧代码。
