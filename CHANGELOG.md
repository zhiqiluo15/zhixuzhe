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

### route + skill 架构落地（2026-08-06）
- **动机**：TaskRunner 每次任务都靠 LLM 即兴分解步骤——灵活但不稳定，同类任务可能拆出不同步骤，且每次多花一次规划 API 调用。需要在"灵活即兴"与"稳定高效"之间搭建路由层。
- **核心设计**：
  - **Skill** = "罐装 TaskRunner 计划"：预先验证过的、可复用的任务步骤模板。每个 Skill 有 name/description/triggers（触发词）+ plan() 返回预设步骤。
  - **Route** = 意图→技能匹配：Router 根据用户输入关键词匹配 SkillRegistry 中注册的技能，命中则跳过 LLM 规划阶段，直接用罐装计划执行；未命中回退到原有 LLM 即兴规划。
  - **集成方式**：Router 嵌入 TaskRunner.run() 的规划阶段，不新建执行引擎、不推翻 TaskRunner 的四阶段流水线。Agent 和 TaskRunner 原有行为完全向后兼容。
- **新文件**：
  - `engine/skills/base.py` — `Skill` 抽象基类（name/description/triggers/plan）
  - `engine/skills/registry.py` — `SkillRegistry`（注册 + 关键词匹配）
  - `engine/core/router.py` — `Router`（封装 SkillRegistry 匹配逻辑）
  - `engine/skills/hardware_check/skill.py` — 首个罐装技能：硬件检测 + QLoRA 判断
- **改造文件**：
  - `engine/skills/__init__.py` — 导出 `Skill` / `SkillRegistry`
  - `engine/core/task.py` — TaskRunner 接受可选 `skill_registry`，`run()` 中优先 Router 匹配
  - `engine/core/loop.py` — Agent 接受可选 `skill_registry` 并透传；REPL 新增 `skills` 命令
  - `engine/core/recorder.py` — `record_task()` 新增 `plan_source` 参数记录规划来源
  - `engine/core/__main__.py` — 入口创建 SkillRegistry 并注册 HardwareCheckSkill
- **向后兼容**：`skill_registry=None`（默认）时行为与旧代码完全一致；TaskRunner / Agent 原有测试无改动且全部通过（16/16）。
- **效果**：用户输入 `task 检测硬件并判断QLoRA条件` → Router 匹配 `hardware_check` → 跳过 LLM 规划，直接执行 3 步罐装计划 → 省 1 次 API 调用，步骤始终一致。
- **层次关系**：Tool（原子动作）→ Skill（Tool + 预设推理的复合体）→ TaskRunner（Skill 编排 + LLM 即兴兜底）。三层各司其职，不互相替代。

### 分层记忆落地：读写闭合（2026-08-06）
- **动机**：CHANGELOG 标记的已知缺陷"记忆只写不读"——Recorder 负责写日记，HistoryStore 负责持久化对话，但没有任何东西把历史经验回注入上下文。自进化闭环缺"回顾"环节。
- **核心设计**：
  - **MemoryReader**（读端）：从 `memory/diary/` 和 `memory/experience/` 检索相关历史条目。v1 检索策略为混合中英文分词（中文 2-gram + 英文单词）+ 关键词重叠评分 + Jaccard 去重，无外部依赖。
  - **MemoryManager**（协调层）：调用 Reader 检索 → 格式化 → 返回上下文字符串，供 Agent 注入 system prompt。
  - **Recorder.record_experience()**（写端增强）：新增经验写入方法，格式 `**场景**/ **教训**`，写入 `memory/experience/YYYYMMDD.md`，与日记并行但独立检索。
- **Agent 集成**：每轮 `run()` 前调用 `MemoryManager.build_context(user_input)`，命中则拼接到 system prompt 末尾的 `【相关历史经验】` 区块；无命中则透传原 system prompt。对 Brain 完全透明。
- **检索效果验证**：
  - `QLoRA 微调条件` → 命中硬件检测任务（score 0.75）
  - `GPU 显卡型号` → 命中 2 条相关记录（score 0.75）
  - `今天晚饭吃什么` → 无结果（正确，无晚餐相关记录）
  - 去重有效：大量测试产生的重复条目被折叠
- **新文件**：
  - `engine/core/memory_reader.py` — `MemoryReader`：日记/经验解析 + 检索
  - `engine/core/memory_manager.py` — `MemoryManager`：检索协调 + 上下文格式化
- **改造文件**：
  - `engine/core/recorder.py` — 新增 `record_experience()`，`experience_dir` 初始化
  - `engine/core/loop.py` — Agent 接受可选 `memory_manager`，`run()` 注入记忆上下文
  - `engine/core/__main__.py` — 入口组装 MemoryReader → MemoryManager → Agent
- **向后兼容**：`memory_manager=None` 时行为与旧代码完全一致；所有测试无需修改且全部通过（16/16）。
- **已知局限**：
  - 检索为纯关键词匹配，无语义理解（未来可升级为向量检索）
  - 经验目录为空，需实际任务积累后才能体现效果
  - TaskRunner（任务模式）暂未注入记忆上下文，待后续迭代

### 安全执行三角落地：命令执行 + 错误恢复 + HITL（2026-08-06）
- **动机**：CHANGELOG 标记的已知差距"手脚太少"和"无安全边界"——之前只有 2 个硬件检测工具，没有文件读写、命令执行等通用手脚。加入外部操作工具前必须先建立安全边界（超时、确认、重试），否则误操作风险高。
- **核心设计**：三个正交机制叠加构成安全执行三角：
  - **命令执行 Tool**（`engine/tools/shell.py`）：PowerShell 命令执行，超时保护（默认 30s，最大 120s），工作目录限制在项目根，非交互模式（-NoProfile -NonInteractive），stdin=DEVNULL 防挂起。
  - **错误恢复（Retry）**：`Tool.execute()` 新增 `max_retries` 参数，指数退避（1s→2s→4s），最多 3 次。默认 0（不重试），网络/瞬态错误类 Tool 可设 `max_retries=2`。
  - **HITL（Human-in-the-Loop）**：`react_loop()` 新增 `confirm_callback` 参数，每轮工具调用前触发。Agent 维护 `confirm_tools` 集合（默认 `{"run_shell"}`），命中时 REPL 交互式询问 `[y/N]`。TaskRunner 同步支持，确保任务模式和对话模式一致的安全策略。
- **Tool 数量**：从 2 个（detect_host / verify_gpu）增加到 3 个（+ run_shell）。一个 Shell 工具覆盖文件读写（cat/dir/ls）、环境检测（python -m pip list）、代码执行（python script.py）等 —— 以最少的工具数撬动最大的操作面。
- **改造文件**：
  - `engine/tools/shell.py` — 新文件：run_shell(command, timeout)
  - `engine/tools/registry.py` — `Tool` 新增 `max_retries`，`execute()` 内置重试循环
  - `engine/core/react.py` — `react_loop()` 新增 `confirm_callback` 参数，HITL 拦截点
  - `engine/core/loop.py` — Agent 新增 `confirm_tools` + `_hitl_confirm()` 方法；help 文本更新
  - `engine/core/task.py` — `TaskRunner.run()` / `_execute_step()` 透传 `confirm_callback`
  - `engine/core/__main__.py` — 注册 run_shell Tool（max_retries=2），注入 DEFAULT_CONFIRM_TOOLS
- **向后兼容**：`max_retries=0`（默认）行为不变；`confirm_callback=None`（默认）不触发 HITL；`confirm_tools` 默认为空集合时所有工具直接放行。所有原有测试无需修改且全部通过（16/16 + 4/4 内存测试）。
- **安全三角运转流程**：
  ```
  Brain 决定调 run_shell(command="pip list")
    → HITL: ⚠️ 工具调用: run_shell(command=pip list) → 执行? [y/N]
    → 用户输入 y → 执行
    → 失败? → 自动重试（1s 后）→ 失败? → 自动重试（2s 后）
    → 仍失败 → 返回错误信息给 Brain
  ```

---

### v1.0 升级：六项补全（2026-08-06）

本次升级将智序者从 v0.6 推向 v1.0，补全了工具层、配置系统、日志系统、记忆注入和技能编排。

#### 1. 工具补全（3 → 6 个）
- **新增文件读写 Tool**（`engine/tools/file_io.py`）：`read_file(filepath)` / `write_file(filepath, content, append)`
  - 安全：仅允许项目根目录内读写，越界拒绝
  - 大文件自动截断（默认 1MB，由 `config.tools.file.max_file_size` 控制）
- **新增网页抓取 Tool**（`engine/tools/web_fetch.py`）：`web_fetch(url)` 
  - 基于 requests，自动 HTML→纯文本，超时保护
- **工具总数**：detect_host / verify_gpu / run_shell / read_file / write_file / web_fetch = 6 个

#### 2. stdout 捕获 hack 重构
- `detect_host.py`：原 `main()` 只 print，现增加 `detect_host()` 函数直接返回格式化字符串
- `verify_gpu.py`：同理，原 `main()` → 新 `verify_gpu()` 返回字符串
- `__main__.py` 移除了 `_capture_stdout` 包装器（40 行 hack 代码消失）

#### 3. 统一配置系统
- **新文件**：`config.yaml`（项目根）+ `engine/config.py`（解析 + 数据类）
- 零依赖微型 YAML 解析器，支持环境变量插值 `${env:VAR_NAME}`
- 所有硬编码常量（MAX_TOOL_ROUNDS、MAX_STEPS、MIN_SCORE 等）全部迁移到配置
- 配置数据类：ModelConfig / AgentConfig / TaskConfig / MemoryConfig / LoggingConfig / ToolsConfig

#### 4. 结构化日志
- **新文件**：`engine/log.py` —— 基于 stdlib logging 的统一日志系统
- 双通道输出：控制台（INFO 级别）+ 文件 `logs/agent.log`（DEBUG 级别，RotatingFileHandler 10MB×5）
- 全项目 `print()` 替换为 `logger.info/debug/error/warning()`
- Agent 生命周期事件全部记录（启动、会话恢复、退出、任务模式、工具调用）

#### 5. TaskRunner 记忆注入
- `TaskRunner` 新增 `memory_manager` 参数，在第一步 `_execute_step()` 中注入记忆上下文
- 闭合了 CHANGELOG 标记的"任务模式无法利用历史经验"缺口
- EXECUTE_SYSTEM 提示词新增 `{memory}` 占位符

#### 6. SkillChain（Orchestrator v1）
- **新文件**：`engine/core/orchestrator.py`
- 实现 Anthropic 五模式中的 **Prompt Chaining**（顺序串联）
- `SkillChain.run(initial_goal, skill_names)`：Skill A 输出 → 作为 Goal 喂给 Skill B
- 每步走 `skill.plan()` 生成步骤，复用 TaskRunner 的 `_execute_step()` + `_synthesize()`
- 设计原则：不做 DAG、不做并行、不做事件总线 —— 只做一件事：顺序串联

#### 改造文件清单
| 文件 | 改动 |
|------|------|
| `config.yaml` | 新文件：全局配置 |
| `engine/config.py` | 新文件：配置解析 + 数据类 |
| `engine/log.py` | 新文件：日志系统 |
| `engine/tools/file_io.py` | 新文件：文件读写工具 |
| `engine/tools/web_fetch.py` | 新文件：网页抓取工具 |
| `engine/core/orchestrator.py` | 新文件：技能链编排器 |
| `engine/tests/conftest.py` | 新文件：测试夹具 |
| `engine/core/__main__.py` | 重写：移除 stdout hack，注册 6 个工具，初始化 config + logging |
| `engine/core/react.py` | 重构：max_rounds 从 config 读取，logging 替换 print |
| `engine/core/loop.py` | 重构：TaskRunner 传 memory_manager，logging 替换 print |
| `engine/core/task.py` | 重构：memory_manager 参数 + 注入，config 读取，logging |
| `engine/tools/detect_host.py` | 重构：新增 detect_host() 返回字符串，logging |
| `engine/tools/verify_gpu.py` | 重构：新增 verify_gpu() 返回字符串，logging |
| `engine/tools/shell.py` | 重构：timeout 从 config 读取 |
| `engine/brain/deepseek_api.py` | 重构：model/url/retries/timeout 从 config 读取 |
| `engine/core/memory_manager.py` | 重构：MAX_ENTRY_CHARS/max_entries 从 config 读取 |
| `engine/core/memory_reader.py` | 重构：MIN_SCORE/DEDUP_THRESHOLD 从 config 读取 |
| `engine/core/history.py` | 重构：print 替换为 logging |
| `engine/core/recorder.py` | 重构：import logger |

#### 测试结果
- **20/20 全部通过**（16 个 react 测试 + 4 个 memory 测试）
- 配置解析验证通过（int/float/str/list 类型全部正确）
- 新增文件 IO 工具验证通过

---

### 流式输出（SSE）（2026-08-06）

- **动机**：v1 的 `brain.think()` 一次性返回完整响应，用户需等待全部输出后才能看到内容，体验差。
- **设计原则**：不与 ReAct 循环耦合。`think_stream()` 是 Brain 的可选能力，`react_loop()` 通过 `stream_callback` 透明接入。
- **实现层次**：
  - `Brain` 基类新增 `think_stream()` 方法：默认回退到 `think()`，一次性产出全部文本后 done。子类可覆写实现真正的 SSE。
  - `DeepSeekAPIBrain.think_stream()`：使用 `stream: true` + `iter_lines()` 解析 SSE 数据流。tool_calls 跨 chunk 累积合并，文本块逐 token 产出。
  - `react_loop()` 新增 `stream_callback: Callable[[str], None]` 参数。内部 `_get_response()` 统一分流：有 callback 走 `think_stream()`，无则走 `think()`。
  - `Agent.run()`（chat 模式）：默认注入 `stream_print` 回调，以 `智序者 > ` 前缀 + `flush` 实时逐字输出。工具调用轮次期间的文本（如有）也会被流式输出。
  - 任务模式（TaskRunner）：**不走流式**，保持 verbose 步骤输出，因为分步执行比逐 token 更有意义。
- **向后兼容**：所有测试 SpyBrain/MockBrain 走基类 `think_stream()` → `think()` 回退，语义不变。`stream_callback=None` 时 react_loop 行为与 v1.0 完全一致。
- **测试**：20/20 全绿
