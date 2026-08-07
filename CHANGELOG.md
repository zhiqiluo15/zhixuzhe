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

---

### Web Server 模块（2026-08-06）

- **动机**：提供浏览器端交互界面，让智序者可通过 Web UI 使用，无需 CLI。
- **文件**：
  - `engine/web_server.py` —— 零依赖 HTTP 后端（基于 `http.server`），提供 REST API + SSE 流式推送
  - `engine/web/index.html` —— 单页前端（星空背景、流式打字效果、Markdown 渲染、API Key 设置引导）
  - `run_web.bat` / `run.ps1` / `run.bat` —— 启动脚本
- **架构**：
  - 懒初始化 Agent（首次请求时组装，`/setup` 设置 API Key 后重新初始化）
  - 线程安全（`threading.Lock` 保护 Agent 单例）
  - SSE 流式输出（`/chat` 逐 token 推送，`/task` 步骤级推送）
  - CORS 开放（`*`），仅监听 `127.0.0.1`（仅本机访问）
- **API 端点**：`GET /`（前端 UI）、`GET /status`、`POST /setup`、`GET /skills`、`POST /chat`（SSE）、`POST /task`（SSE）、`POST /reset`
- **已知局限**：Agent 组装逻辑与 CLI 入口重复（已在 v1.1 通过 factory.py 解决）；TaskRunner 输出通过 stdout 劫持捕获（已在 v1.1 通过 verbose_callback 解决）

---

### v1.1 修复：11 项问题修复（2026-08-06）

以下修复基于 2026-08-06 全面体检报告，按优先级排序。

#### P0-1: Web 端 HITL 安全修复（安全漏洞）
- **问题**：`Agent.run()` 在 web 模式下（有 `stream_callback`）将 `confirm_callback` 设为 None，导致 `run_shell` 等需确认的工具绕过 HITL。Web 端 CORS=`*` + `127.0.0.1` 监听 → CSRF 可触发 RCE。
- **修复**：
  - `Agent.run()` 新增 `confirm_callback` 参数，优先级：显式传入 > CLI 默认 `_hitl_confirm` > None
  - `web_server.py` 新增 `_make_web_confirm_callback(sse_write)`：通过 SSE `confirm_request` 事件 + `threading.Event` 等待前端 60 秒内响应
  - 新增 `/confirm` POST 端点接收前端确认结果
  - `HTTPServer` → `ThreadingHTTPServer`（支持 SSE 流期间并发处理 `/confirm`）
  - 前端新增确认覆盖层（CSS + HTML + JS）：工具名、参数展示、拒绝/允许按钮
- **影响**：Web 端安全三角闭合，chat 和 task 模式均受 HITL 保护

#### P0-2: write_file append 模式修复
- **问题**：`file_io.py` 中 `mode = "a" if append else "w"` 计算了但未使用，`path.write_text()` 永远覆盖
- **修复**：改用 `path.open(mode, encoding="utf-8")` + `f.write(content)`
- **影响**：`append=True` 时正确追加而非覆盖

#### P1-3: think() 4xx 不重试修复
- **问题**：`resp.raise_for_status()` 抛出的 `HTTPError` 被外部 `except RequestException` 捕获，导致 4xx（如 401 认证失败）也重试 3 次
- **修复**：4xx 非 429 直接 `return Message(...)` 而非抛异常
- **影响**：401/400 等不可重试错误立即返回，不浪费 API 调用

#### P1-4: CHANGELOG 补记
- 本次变更（Web Server 模块 + v1.1 修复）的全部记录（即本条目）

#### P2-6: Agent 组装工厂抽取
- **问题**：`__main__.py` 和 `web_server.py` 各有一份 ~90 行的 Agent 组装代码，完全重复
- **修复**：新建 `engine/factory.py`，`create_agent(project_root)` 统一组装；两个入口改为一行调用
- **影响**：后续新增工具/技能只需改一处，消除不一致风险

#### P2-7: stdout 劫持 hack 修复
- **问题**：`web_server.py` 通过 `_StepCapture` 类劫持 `sys.stdout` 捕获 TaskRunner 输出，与 CHANGELOG 记录的 v1.0 "stdout 捕获 hack 重构" 背道而驰
- **修复**：`TaskRunner.run()` 新增 `verbose_callback: Callable[[str], None]` 参数；Web 端传入 SSE 回调直接捕获步骤输出；删除 `_StepCapture` 类
- **影响**：消除 stdout 劫持，TaskRunner 原生支持回调输出

#### P3-8: 经验写入去重
- **问题**：`record_experience()` 不检查重复，同一条经验被连续写入多次
- **修复**：`_write_experience()` 写入前检查当日文件中是否已存在相同场景+教训组合
- **影响**：经验文件不再膨胀，每条经验只记录一次

#### P3-9: think_stream 重试
- **问题**：`think_stream()` 无重试逻辑，与 `think()` 的 3 次重试不一致
- **修复**：请求阶段包裹在 `for attempt in range(config.model.max_retries)` 循环中，429/5xx/网络错误退避重试，4xx 非 429 立即返回
- **影响**：流式路径容错能力与非流式一致

#### P3-10: 测试 assert 修复
- **问题**：`test_memory.py` 4 个测试函数末尾 `return True` 触发 `PytestReturnNotNoneWarning`
- **修复**：删除 `return True` 语句
- **影响**：消除 pytest warning，无功能变化

#### P3-11: 私有属性访问替换
- **问题**：多处直接访问 `_tools`、`_skills`、`_current` 等下划线私有属性
- **修复**：`ToolRegistry` 新增 `__len__`/`names()`/`__contains__`/`__iter__`；`SkillRegistry` 新增 `names()`/`list_all()`；`HistoryStore` 新增 `current_session_name` 属性 + `set_current_session()`；`Agent` 新增 `tool_count`/`skill_count` 属性；所有调用方替换为公共 API
- **影响**：封装性提升，外部代码不再依赖内部实现细节

---

### 启动脚本重写：去中文 + 端口自检 + 启动验证（2026-08-06，终版）

- **问题（第四轮）**：GBK+CRLF 修好后双击仍拒绝连接。
- **根因**：`start "智序者 Web" python engine\web_server.py 8080` ——即使编码正确，`start` 带中文标题在 cmd 936 下行为仍不稳定，且残留僵尸进程占端口时新启动静默失败，无任何错误提示。
- **修复（重写 `run_web.bat` / `run.bat`）**：
  - **全英文**：title / echo / start 标题全部转英文，彻底消除编码不稳定因素
  - **端口自检+自动清理**：启动前 `netstat` 查 8080 占用 → `taskkill` 杀掉残留进程
  - **启动验证循环**：最长等 10 秒，每秒检查 8080 是否 LISTENING，起不来则报 ERROR 退出
  - **隐藏窗口**：`start "" /min` 最小化 python 窗口，不干扰用户

### 文件锁修复：RotatingFileHandler delay=True（2026-08-06）

- **问题（第五轮）**：去中文后仍 PermissionError，`logs/agent.log` 写入被拒绝。
- **根因**：前次启动的 python 进程被杀后，Windows 文件句柄释放有延迟。bat 里的 `del /f /q` 对这个窗口期的文件锁无能为力 → 新进程初始化 `RotatingFileHandler(mode='a')` 时立即 `_open()` 打不开 → PermissionError。不是文件权限问题，是**进程间文件锁竞争**。
- **修复**：[engine/log.py](file:///t:/zhixuzhe/engine/log.py#L61) 中 `RotatingFileHandler` 添加 `delay=True`——延迟文件打开到第一次 `emit()`（写日志），此时旧进程的句柄已释放。这是 Python logging 处理此场景的标准做法。
- **验证**：cmd 936 模拟双击 → 8080 监听（PID 22008），`/status` → 200，`agent.log` 正常创建（116 bytes）。

### 记忆写入保护：Recorder 文件锁重试（2026-08-07）

- **问题**：Web 端聊天时报 `PermissionError: memory/diary/20260807.md`，记忆记录失败。
- **根因**：与 `agent.log` 同类问题——`Recorder._write()` 直接 `open(file, "a")`，遇文件锁立即抛异常。本次触发场景是跨天文件首次创建时旧进程尚未释放句柄。
- **修复**：[engine/core/recorder.py](file:///t:/zhixuzhe/engine/core/recorder.py#L90-L103) 新增 `_write_atomic()` 静态方法，3 次重试（0.2s → 0.4s 退避），`PermissionError` 全吞不阻断主流程。`_write()` 和 `_write_experience()` 统一走该方法。
- **测试**：20/20 全绿。

---

### 深度体检修复：配置解析 + 参数生效 + SSRF + 封装性（2026-08-07）

基于全面体检报告，按 P1→P3 优先级修复全部检出的问题。

#### P1-1 修复 config.yaml 块状列表解析失效
- **问题**：`_parse_yaml` 的 `list_context` 声明后从未赋值，`- item` 块状列表项被静默丢弃（实测 `allowed_dirs` 解析为空 dict）。
- **修复**：[engine/config.py](file:///t:/zhixuzhe/engine/config.py#L49) 重写列表解析——引入 `pending_list` 记录最近的空值 key，`- item` 缩进更深时归入其列表；原空 dict 自动转为 list。内联 `[..]`、嵌套 dict 行为不变。
- **验证**：块状/内联/嵌套三种形态均正确；原 `config.yaml` 加载回归正常。

#### P1-2 修复 temperature / max_tokens 配置未生效
- **问题**：`config.yaml` 定义了 `temperature`/`max_tokens`，但 brain 的 payload 从未携带，改配置无效。
- **修复**：[engine/brain/deepseek_api.py](file:///t:/zhixuzhe/engine/brain/deepseek_api.py#L65) 的 `think()` 与 `think_stream()` 均将两参数写入请求体。

#### P2-3 orchestrator 改用公共 API
- **问题**：`_find_skill` 直接访问 `self.skill_registry._skills` 私有属性，违反 v1.1 P3-11 已确立的封装规范。
- **修复**：[engine/core/orchestrator.py](file:///t:/zhixuzhe/engine/core/orchestrator.py#L138) 改用已存在的 `SkillRegistry.list_all()`。

#### P2-4 SSE 解析兼容无空格前缀
- **问题**：`think_stream` 只认 `data: `（带空格），`data:{...}`（无空格）会被丢弃。
- **修复**：[engine/brain/deepseek_api.py](file:///t:/zhixuzhe/engine/brain/deepseek_api.py#L191) 改为 `startswith("data:")` + `strip()` 去前缀。

#### P2-5 web_fetch 增加 SSRF 防护
- **问题**：`web_fetch` 可访问 `127.0.0.1`、内网/保留地址，存在被诱导探测内网的风险。
- **修复**：[engine/tools/web_fetch.py](file:///t:/zhixuzhe/engine/tools/web_fetch.py#L23) 新增 `_is_blocked_url()`（回环/私网/链路本地/保留/组播），请求前与重定向后各校验一次。
- **验证**：`127.0.0.1`/`localhost`/`192.168.x`/`10.x` 均拦截，公网放行。

#### P3 web_server 并发锁 + 死代码清理
- **问题**：`_pending_confirms` 全局 dict 无显式锁，依赖 GIL 原子性；`_parse_yaml` 的 `list_context` 为死代码。
- **修复**：[engine/web_server.py](file:///t:/zhixuzhe/engine/web_server.py#L36) 新增 `_pending_confirms_lock`，确认回调与 `/confirm` 端点的读改写统一加锁；死代码随 P1-1 重写清除。

#### 未纳入修复（有意保留）
- **run_shell 命令白名单**：`run_shell` 是通用 shell 工具，加白名单会破坏功能性；现有 HITL 确认（`confirm_tools`）已提供足够保护，列为远期加固而非本次修复。

- **测试**：20/20 全绿；config 解析与 SSRF 防护均实测验证。

---

### 启动脚本闪退修复：LF 换行 → CRLF + GBK 编码（2026-08-06，三轮修正，已被上述终版取代）

- **问题（第一轮）**：双击 `run_web.bat` / `run.bat` 窗口一闪而过；终端直跑 `python engine\web_server.py 8080` 却一切正常。
- **根因（第一轮）**：.bat 是 **LF（`0A`）换行**，非 Windows 批处理标准 CRLF。cmd 解析 LF-only 批处理时多行复合逻辑（`if` 块、`set /p`、`timeout`、`start`）跳行错乱 → 窗口闪退。
- **问题（第二轮）**：修好换行后不再闪退，但浏览器打开报"拒绝连接"（ERR_CONNECTION_REFUSED）——python 服务根本没被拉起。
- **根因（第二轮，判断失误）**：误信 PowerShell 终端 `chcp` 显示的 65001（UTF-8），把 .bat 转成 UTF-8 编码。但**双击 .bat 走的是 cmd，其代码页由注册表 ACP/OEMCP 决定，本机为 936（GBK）**。PowerShell 7 终端代码页 ≠ cmd 代码页。UTF-8 编码的 .bat 被 cmd 按 GBK 解码 → `start "智序者 Web" python ...` 中文标题乱码 → 命令解析失败 → python 从未启动。
- **根因（最终确认）**：注册表 `HKLM\SYSTEM\CurrentControlSet\Control\Nls\CodePage` → **ACP=936, OEMCP=936**（GBK）。双击场景 cmd 用 GBK。
- **修复**：.bat 统一为 **GBK（cp936）+ CRLF + 无 BOM**。验证方式：用 GBK 编码写测试 bat 以 cmd 936 代码页环境启动 → 8080 被 python 监听 → 服务正常。
- **教训（重要）**：
  - **判代码页要看注册表（ACP/OEMCP），不是看 PowerShell 终端 chcp**。PowerShell 7 默认 UTF-8，cmd 默认由系统区域设置决定。
  - 本机规范：Windows 批处理 = **GBK + CRLF + 无 BOM**；UTF-8 会乱码并静默破坏 `start` 带中文标题的命令。
  - 中文出现在 `start "标题"` / `title` 中时对编码尤其敏感，乱码不只是难看，会直接让命令执行失败。
  - 验证脚本启动必须模拟 cmd 936 环境，终端直跑不能代表 .bat 健康。

---

### 体检修复：测试隔离 + memory 污染清理（2026-08-06）

- **动机**：全面体检发现 P0 级数据完整性 bug——`test_react.py` 的 HistoryStore / Agent / TaskRunner 测试直接用 `PROJECT_ROOT/memory/` 作为操作目录，违反"灵魂层物理隔离"原则，造成三重损害：
  1. `test_history_*` 的 `_clean_conversations()` 执行 `rmtree` 删除整个生产 conversations 目录，**已致用户真实 10 条对话历史丢失**（`20260806_165645_110159.jsonl`）
  2. `Recorder(root=PROJECT_ROOT)` 把测试交互（MockBrain 预设的 "你是谁？"/"10加20等于几？" 等）写入生产 diary，污染两个日记文件共 183 条假条目
  3. `test_history_reset_creates_new_file` 结尾无清理，残留 2 个测试 jsonl 文件，时间戳最新 → 下次启动 `latest_session()` 会恢复到 0 字节空会话
- **根因**：测试用 `PROJECT_ROOT` 接触灵魂层，[conftest.py](engine/tests/conftest.py) 的 `root` fixture 已示范了正确的临时目录做法，但 `test_react.py` 未遵循。
- **修复**：
  - `test_react.py`：9 个 HistoryStore 测试 + 4 个 Agent/TaskRunner 测试改用 pytest `tmp_path` fixture，所有 `root=PROJECT_ROOT` → `root=tmp_path`（共 15 处）
  - 删除 `_clean_conversations()` 函数及其 9 处调用（不再需要，`tmp_path` 自动隔离）
  - 清理生产 memory 中的测试污染残留：
    - 删除 `memory/conversations/` 下 2 个测试残留 jsonl
    - 清理 `memory/diary/20260805.md`（删除 51 条测试条目，保留 11 条真实记录：手写私人经历 + 真实交互 + 硬件评估报告）
    - 清理 `memory/diary/20260806.md`（删除 132 条测试条目，保留 5 条真实 DeepSeek 对话）
    - 删除 `memory/experience/20260806.md`（4 条全为测试数据）
- **清理原则**：按 MockBrain 预设内容与 conftest 预填数据精确字符串匹配删除，真实 DeepSeek 回复（如 "我是智序者，一个基于 DeepSeek 的智能助手"）不含这些精确字符串，未被误伤。
- **验证**：测试 20/20 全绿；`memory/conversations/` 清空；生产 diary 只含真实记录；`import` 链健康。
- **教训**：测试必须用临时目录（`tmp_path`）隔离，灵魂层数据对测试是只读黑盒。已丢失的 conversations JSONL 对话内容可从 diary 找回（Recorder 独立备份）。
- **未修复项**：git 历史 commit 信息全是 "ok"（无法重写历史），建议后续 commit 遵循 `feat/fix/refactor: 描述` 规范。

### 第二次深度体检修复：复发 bug + 自进化闭环 + SkillChain 接入（2026-08-07）

- **动机**：第二轮全项目体检发现 2 个 P0 级复发 bug（其中 P0-1 是上轮已"修复"的同类问题）、自进化闭环关键断裂、SkillChain 死代码、前端 XSS 等共 11 项问题。
- **P0-1 0 字节会话文件导致历史恢复失效（复发，本次修根因）**：
  - 现象：`memory/conversations/` 残留 0 字节空会话文件（reset/异常退出后 `new_session` 只 `touch` 不写内容），时间戳最新 → `latest_session()` 误选空文件 → Agent 启动恢复到空历史，真实会话被冻结。
  - **复发根因**：上轮（2026-08-06 体检修复）只清了测试残留的 2 个空文件，**未修 `latest_session` 根因**——只要 reset 或异常退出就会再产生空文件。本次彻底修根因。
  - 修复：[history.py](engine/core/history.py) `latest_session()` 过滤 0 字节文件；`save()` 空消息列表时跳过写入（不创建空文件）；`save()` 改原子写入（临时文件 + rename，防崩溃损坏）。
  - 同步删除已存在的 0 字节残留文件。真实场景验证：`latest_session` 现正确选中 7583 字节真实会话。
- **P0-2 detect_host GPU 身份字段对比失效**：
  - 现象：`IDENTITY_KEYS` 含 `"GPU 型号"`，但 `detect_gpu()` 有 NVIDIA 卡时返回 `"GPU 列表"`，无卡才返回 `"GPU 型号"` → `read_latest()` 永远读不到 GPU 字段 → GPU 变更检测失效。
  - 修复：`IDENTITY_KEYS` 改用 `"GPU 列表"`。验证：`read_latest` 现能读到 RTX 5060 信息。
- **P1-1 经验沉淀闭环断裂（自进化核心）**：
  - 现象：`recorder.record_experience()` 定义了但全项目无生产代码调用，`memory/experience/` 无实际经验文件。CHANGELOG 宣称"分层记忆读写闭合"但经验写入路径从未运转。
  - 修复：[task.py](engine/core/task.py) `TaskRunner.run` 综合后新增 `_reflect_experience()` 反思步骤——让 Brain 判断本次执行是否有值得沉淀的教训，有则输出 JSON（scene+lesson）调 `record_experience` 写入经验库，无则 skip 避免膨胀。反思失败不阻断主流程。
  - **机制闭合，质量待运行迭代**：经验质量取决于 prompt 设计 + 真实运行，后续需跑真实任务验证经验质量后迭代 prompt。
- **P1-2 think_stream 流式重试边界 + 读取超时**：
  - 现象：`think_stream` 重试只覆盖请求建立阶段，流式迭代阶段（iter_lines）连接中断直接抛异常；且无读取超时，服务器静默不发包时无限阻塞。
  - 修复：[deepseek_api.py](engine/brain/deepseek_api.py) timeout 改元组 `(connect, read)` 防阻塞；iter_lines 包 try/except，中断时若已有累积内容则返回部分结果（标注中断），无内容则报错。**不重试流式迭代**——已向用户输出过的文本重发会造成重复显示，属合理取舍。
- **P1-3 SkillChain 接入（用户决定接入而非删除）**：
  - 现象：[orchestrator.py](engine/core/orchestrator.py) 143 行 dead code，从未被 import/调用；且访问 TaskRunner 私有方法 `_execute_step`/`_synthesize`（上轮 P2-3 声称改公共 API 只修了 `_find_skill`，这两处漏修）。
  - 修复：
    1. [task.py](engine/core/task.py) 新增公共方法 `execute_plan(goal, plan, ...) -> (final, step_results)`，封装执行+综合；`run` 内部改调它消除重复。
    2. [orchestrator.py](engine/core/orchestrator.py) `SkillChain.run` 改用 `execute_plan`，封装泄漏彻底消除；新增 `verbose_callback` 参数支持 Web 端 SSE 进度推送。
    3. [loop.py](engine/core/loop.py) REPL 新增 `chain <目标> | <技能1> <技能2>` 命令；help 文本同步更新；task/chain 结果入 history（修 P3-2，后续对话可知刚执行过任务）。
    4. [web_server.py](engine/web_server.py) 新增 `POST /chain` 端点，SSE 流式推送链式进度。
  - **未来演进**：技能增多后 Router 关键词匹配会成瓶颈（等真实冲突再升级 LLM 路由）；SkillChain 暂只做顺序串联，Parallelization/Evaluator-Optimizer 等模式等真实需求出现再加（YAGNI）；远期方向是"技能自生长"——Brain 从成功任务提炼可复用 plan 自动生成新 Skill。
- **P2-1 前端 XSS 防护**：
  - 现象：[index.html](engine/web/index.html) 多处 innerHTML 注入未转义内容——task goal（用户输入）、task step（工具输出）、user 消息、assistant 非流式渲染均走 marked.js（默认不 sanitize）。
  - 修复：新增 `escapeHtml`（纯文本转义，用于 user 消息/流式初始）、`sanitizeHtml`（白名单清理，移除 script/iframe/on* 事件属性/javascript: 协议）、`renderMarkdownSafe`（markdown→sanitize）。addMessage 的 system/assistant 非流式走 renderMarkdownSafe，user/流式走 escapeHtml；task_start 改用 markdown `**目标：**` 加粗。
  - **局限**：sanitizeHtml 是简易白名单，覆盖常见 XSS 向量但不保证对抗所有 payload；工业级防护需引 DOMPurify（破坏零依赖，暂不引入）。
- **P2-2 web_fetch DNS rebinding（保留不修）**：
  - 已有"请求前+重定向后"双私网校验，DNS rebinding 对本地 127.0.0.1 工具威胁低，实现完整防护（自定义 HTTPAdapter 固定 IP）复杂度高，性价比低，标注为已知风险，远期再加固。
- **P2-3 react_loop 轮次耗尽返回带 tool_calls 的 response**：
  - 修复：[react.py](engine/core/react.py) 轮次耗尽时若 response 仍含 tool_calls，清空 tool_calls 并标注"[已达到最大工具调用轮次]"，避免半成品 tool_calls 存入 history 造成上下文混乱。
- **P3 杂项**：
  - [history.py](engine/core/history.py) save 原子写入（见 P0-1）。
  - [config.py](engine/config.py) `load_config` 局部变量 `config` 遮蔽模块单例 → 改 `cfg`。
  - [file_io.py](engine/tools/file_io.py) `read_file` 新增二进制检测（前 2KB 含 NUL 字节视为二进制），避免 `errors="replace"` 静默损坏。
  - [detect_host.py](engine/tools/detect_host.py) 新增 `_cleanup_snapshots()`，body 快照仅保留最近 6 个（latest.md 不计入不删除），防无限增长。
  - [loop.py](engine/core/loop.py) task/chain 结果入 history（见 P1-3）。
- **验证**：测试 20/20 全绿（更新 `test_history_latest_session_picks_newest` 以反映"空文件被忽略"新语义）；import 链健康；execute_plan/SkillChain.run/_reflect_experience 签名正确；P0-1/P0-2 真实场景验证通过；help 文本含 chain 命令。
- **教训**：
  1. **复发 bug 要修根因**：上轮 P0-1 只清残留未修 `latest_session`，必然复发。本次修根因（过滤空文件 + save 跳过空写入）。
  2. **CHANGELOG 声称的"闭环"要用调用链验证**：P1-1 经验沉淀号称闭合但无调用路径，纯属文档负债。
  3. **dead code 要么接入要么删除**：SkillChain 搁置即腐烂（封装泄漏漏修）。接入时让 TaskRunner 暴露公共方法，不访问私有。

### 新增 web_search 工具 + web_research_summarize 技能（2026-08-07）

- **动机**：按用户提出的 6 个技能规划，从最高优先级开始实现。web_research_summarize 是首个"工具链完整、零新依赖、能立即验证 SkillChain"的技能。
- **发现的缺口**：factory.py 注册了 6 个工具，但 CHANGELOG 和用户规划都假设存在 `web_search`，**实际从未实现**——只有 `web_fetch`（获取单个 URL），无法"搜索"。必须先补 web_search 工具。
- **web_search 工具**（[web_search.py](engine/tools/web_search.py)）：
  - 零依赖 Bing HTML 搜索（requests + 正则解析），无需 API Key
  - 最初尝试 DuckDuckGo HTML/lite 端点，当前网络环境连接超时，改用 Bing（连通性测试确认可达）
  - 返回结构化结果：编号 + 标题 + URL + 摘要，用 `html.unescape()` 统一解码 HTML 实体
  - Bing 结果在 `<li class="b_algo">` 块中，正则解析标题（`<h2><a>`）+ URL（href）+ 摘要（b_caption/p）
  - 参数：query（必填）、max_results（默认 8，上限 20）、timeout
- **web_research_summarize 技能**（[web_research/skill.py](engine/skills/web_research/skill.py)）：
  - 三步计划：web_search 搜索 → web_fetch 抓取 3-5 个最相关页面 → 综合产出结构化报告（核心结论+关键事实+来源对比+参考URL）
  - 15 个中英文触发词：调研/搜索一下/查一下/搜一下/research/search for/look up 等
  - 第三步要求 Brain 明确标注"信息不足未能确认"的部分，避免幻觉
- **Router 冲突修复**（注册顺序 + 触发词精度）：
  - 问题：hardware_check 先注册，"QLoRA"作为独立触发词太宽泛，"搜索一下 QLoRA 论文"误匹配到硬件检测
  - 修复：
    1. 技能注册顺序调整：web_research 先注册（含显式动作词"搜索/查/调研"的技能优先），hardware_check 后注册
    2. hardware_check 的 "QLoRA" → "QLoRA微调"/"跑QLoRA"/"QLoRA可行"/"QLoRA条件"，"显卡"→"显卡配置"，新增"显存够不够/显存够吗/can i run qlora"
    3. 新增原则：**含显式意图动词（搜索/查/调研）的触发词技能优先注册，领域名词技能在后；单名词触发词须有足够领域特异性**
- **factory.py 更新**：注册 web_search 工具（第 7 个工具）+ WebResearchSkill（第 2 个技能）
- **验证**：web_search 实搜索测 DeepSeek API 文档、QLoRA 微调教程中文结果正常；Router 15 个测试用例全通过（7 个命中 web_research、5 个命中 hardware_check、3 个不命中）；测试 20/20 全绿；无空会话文件残留。
- **经验沉淀机制验证**：本次任务是 P1-1 经验反思的首次实战——_reflect_experience 在任务完成后自动触发，但因当前无 API Key 实际调用会失败（不阻断主流程），待用户提供有效 Key 后即可运行。
- **后续**：code_search_explore（需先新增 search_file/grep 工具）、data_analysis_visual、file_manage_batch，以及 hardware_check → environment_check 扩展（合并原规划的 environment_setup_check）。

---

### v1.2 升级：Web 体验优化 —— 打破黑箱 + 减截断 + 思考动画（2026-08-07）

本次升级将智序者从 v1.1 推向 v1.2，解决 Web 端三大体验痛点：消息截断、工具调用黑箱、等待无反馈。同时修复了前端中文编码损坏问题。

- **动机**：用户反馈 Web 端体验差——消息频繁截断、AI 工作过程纯黑箱（工具调用不可见）、等待体感差（无进度指示）。
- **根因分析**：
  1. **截断**：`config.yaml` 中 `max_tokens: 4096` 太低，长回复被 API 硬截断；前端 SSE 解析 `catch (e) {}` 静默丢弃异常，部分事件丢失。
  2. **黑箱**：`react_loop` 的工具调用过程对前端完全不可见——chat 模式只推文本，不推工具调用事件。
  3. **等待体感差**：工具执行期间前端无任何进度指示，只显示静态"思考中..."。
- **修复**：

  #### 后端：工具调用事件管道
  - **`config.yaml`**：`max_tokens` 从 4096 → 16384（4x），充分利用 DeepSeek V4 Pro 的 32K 输出能力。
  - **`engine/core/react.py`**：新增 `ToolEventCallback` 类型 + `tool_callback` 参数。工具调用前后触发 `tool_start`（工具名/参数/轮次）和 `tool_end`（结果预览/截断标记/取消标记）事件。
  - **`engine/core/loop.py`**：`Agent.run()` 新增 `tool_callback` 参数并透传 `react_loop`。
  - **`engine/web_server.py`**：`_handle_chat()` 中创建 `tool_callback` 闭包，将 `tool_start`/`tool_end` 事件通过 SSE 推送给前端。

  #### 前端：可见进度 + 思考动画 + 健壮解析
  - **工具调用可见**：新增 `addToolMessage()` 函数渲染工具调用卡片——`tool_start`（🔧 橙色，工具名+参数）、`tool_end`（✅ 绿色，结果预览 + 截断标签）。chat 模式下工具调用不再黑箱。
  - **思考动画**：新增 `showThinking()`/`hideThinking()` + CSS 三点脉冲动画（`.thinking-dots`）。工具调用间隙和初始等待时显示"AI 思考中..."带动画，打破纯静态等待。
  - **截断感知**：工具结果截断时显示"已截断"标签；`done` 事件中检测轮次耗尽警告。
  - **错误处理**：SSE 解析失败不再静默丢弃，改为 `console.error` 输出调试信息。
  - **CSS 新增**：`.tool-msg`（工具卡片三态：start/end/cancelled）、`.thinking-dots`（脉冲动画）、`.truncation-warning`（截断警告）。

- **影响范围**：
  - `react_loop` 签名新增可选参数 `tool_callback`，向后兼容（`None` 时行为不变）
  - `Agent.run()` 签名新增可选参数 `tool_callback`，向后兼容
  - 前端大幅增强，CSS + JS 均有新增，但不影响已有功能
- **测试**：20/20 全绿；import 链健康。
- **设计原则**：
  - **渐进披露**：工具调用默认展示摘要（参数截断 120 字符、结果预览 200 字符），不淹没对话流
  - **思考指示器做减法**：首次文本到达时自动隐藏（`hideThinking()`），避免干扰实际内容
  - **事件驱动而非轮询**：利用已有 SSE 管道，不新增 WebSocket 或轮询机制

### 前端编码修复：中文乱码（2026-08-07）

- **问题**：网页显示中文乱码（如"智序者"显示为"鏅哄簭鑰?"）。
- **根因**：`index.html` 原始 UTF-8 字节被中间工具误读为 GBK 编码后重新保存为 UTF-8，形成双重编码损坏。UTF-8 的 "智序者"（E6 99 BA E5 BA 8F E8 80 85）→ 被解读为 GBK 字节对 → 映射为错误的 Unicode 字符（鏅哄簭鑰?）→ 再编码为 UTF-8 写入文件。
- **修复**：重写整个 `index.html`，确保所有中文文本为正确的 UTF-8 编码。验证：所有关键中文文本 ✓、UTF-8 往返无损坏、HTML 结构完整。

### Web 安全加固 P0：斩断 CSRF 自动批准链（2026-08-07）

- **动机**：[web_server.py](engine/web_server.py) 此前 CORS=`*` + 无来源校验 + `/confirm` 仅凭 id 批准，构成完整的 CSRF→RCE 攻击链——恶意网页（用户本机浏览器同时打开即可）能跨域读 `/chat` 的 SSE 流拿到 `confirm_id`，再 `POST /confirm {id, approved: true}` 自动批准 `run_shell`，等效任意命令执行。`/setup`、`/reset` 同样可被跨域盲发。
- **威胁模型澄清**：智序者是 127.0.0.1 单用户本机工具，唯一真实威胁是"用户浏览器同时开着恶意网页 → CSRF 本机接口"，而非远程黑客或多用户越权。按此模型做最小有效修复，不引入为公网多用户场景设计的机制（PIN 码、HITL 验证码、命令白名单、容器化——这些要么错配，要么破坏"感知宿主机"的核心功能）。
- **三件套修复**（全部集中在 [web_server.py](engine/web_server.py)）：
  1. **CORS 收紧**：`_cors()` 从 `Allow-Origin: *` 改为动态回显——仅当请求 `Origin` 属于 `http://127.0.0.1:<port>` / `http://localhost:<port>` 时回显该 Origin，并加 `Vary: Origin` + `Allow-Credentials: true`。恶意网页跨域读不到 SSE 流 → 拿不到 `confirm_id` → 自动批准链断。
  2. **Origin/Referer 校验**：新增 `_check_origin()`，`do_POST` 与 `do_OPTIONS` 入口强制校验。Origin 优先、退化到 Referer、都没有则拒绝。挡住盲发 POST 和跨域预检。
  3. **Session 绑定**：`GET /` 首次访问下发 `session=<token>; HttpOnly; SameSite=Strict` cookie；`do_POST` 入口要求所有 POST 带有效 session cookie（挡 curl/脚本）；`/confirm` 校验 `confirm_id` 绑定的 `session_id` 与当前请求 session 一致，防跨会话代答。`_pending_confirms` 结构从 `{event, result}` 扩展为 `{event, result, session_id}`。
- **连带保护**：`/setup` 和 `/reset` 在 `do_POST` 入口被同一道 Origin + Session 校验覆盖，无需额外 PIN 码即天然安全（跨域 POST 被挡）。`/setup` 覆写 `.env` 的隐私威胁（攻击者把自己的 Key 写入 → 用户后续对话走攻击者 Key → DeepSeek 后台泄露对话内容）同步消除。
- **明确不做**（附理由，避免后续重复讨论）：
  - HITL 验证码：本机单用户场景体验灾难，HITL 弹窗的"用户主动点击"已是强意图信号，弹窗不被脚本代答即可。
  - PIN 码：为 0.0.0.0 多用户设计，127.0.0.1 单用户不需要。
  - 命令白名单/黑名单：PowerShell 别名繁多（`rm`=`Remove-Item`、`curl`=`Invoke-WebRequest`），黑名单易绕过；白名单破坏通用 shell 功能性。CHANGELOG 已多次标注"有意保留"。
  - 容器化：与"感知宿主机硬件/GPU"的设计目标根本冲突，容器内看不到宿主机 GPU。
  - API Key 加密存储：基于机器特征的派生密钥在 run_shell 被 RCE 后无效（攻击者能读到派生原料），属假安全。真正防护是"不让 run_shell 被自动批准"（本三件套已解决）。
  - 域名白名单 for web_fetch：会废掉 web_search/web_fetch 查任意资料的能力。
- **验证**：
  - 集成测试 8/9 通过（GET / 下发 cookie ✓、无 Origin POST 拒绝 ✓、恶意 Origin 拒绝 ✓、无 session POST 拒绝 ✓、合法来源放行 ✓、OPTIONS 预检恶意/本地分流 ✓）；测试 7 的 404 是 confirm_id 不存在分支先返回，非 bug。
  - 单元测试验证 session 校验逻辑：session-A 的 confirm_id 对 session-B 返回不匹配 → 403。
  - 原有测试套件 20/20 全绿，无回归。
- **遗留（P1/P2，远期）**：
  - SSRF DNS rebinding 加固（pin resolved IP）——CHANGELOG P2-2 已标注，本次未动。
  - `run_shell` 命令白名单——维持"靠 HITL 兜底"现状，CSRF 链斩断后风险回到"用户自己批准危险命令"的责任边界。

### 启动崩溃修复：GBK 控制台 emoji 编码（2026-08-07）

- **问题**：双击 `run_web.bat` 启动时 `UnicodeEncodeError: 'gbk' codec can't encode character '\u26a0'`，服务起不来；但终端直跑正常。
- **根因**：与 CHANGELOG 已记录的 .bat 编码坑同源——双击 .bat 走 cmd，代码页 936（GBK），Python 的 stdout/stderr 编码随之为 GBK。`main()` 中 `print(f"  ⚠️  Agent 未就绪...")` 的 `⚠️`（U+26A0）GBK 无法编码 → 启动即崩。终端（PowerShell 7，UTF-8）无此问题，故"终端正常、双击崩溃"的差异现象极具迷惑性。
- **修复**（[web_server.py](engine/web_server.py)）：
  1. `main()` 开头对 stdout/stderr 统一 `reconfigure(errors="replace")`——任何代码页下 emoji 都无法再触发崩溃（不可编码字符降级为 `?`）。
  2. 启动打印中的 `⚠️` 替换为普通文本 `[!]`，GBK 下显示也干净。
- **排查发现**：全项目生产代码仅 [web_server.py](engine/web_server.py) 启动路径有 emoji print；orchestrator 的 `✅` 在 web 模式走 callback 不进 stdout，CLI 模式走 PowerShell（UTF-8），均不受影响。测试文件的 emoji print 不参与启动。
- **验证**：`PYTHONIOENCODING=gbk` 模拟 cmd 环境——单点 print emoji 不崩溃；服务正常启动并响应 `/status`；测试套件 20/20 全绿。

---

### 网页填 API Key 提示"没网络"排查与加固（2026-08-07）

- **现象**：Web 端填 API Key 点确认后提示"网络错误: Failed to fetch"（前端 catch 分支），而非可读的错误文案。
- **排查过程（先证伪再定位）**：
  1. 用 http.client 完整模拟浏览器流程（同源 Origin + session cookie）→ 后端 CORS/Origin/Session 校验逻辑全部正确：成功路径 200、无 cookie 403、恶意 Origin 403。
  2. 验证 `create_agent` 三种 key（合法格式/占位符/空）→ 只抛 `ValueError`（被 `_try_init_agent` 捕获转 500），无其他异常。
  3. 验证 `HistoryStore.load` 跳过损坏行、`latest_session` 过滤 0 字节 → 会话恢复不会崩。
  4. **结论**：后端校验逻辑无 bug，"网络错误" = `fetch()` 被拒 = 连接被掐断（服务端异常击穿 handler 线程）或浏览器侧问题（旧页面缓存/服务未运行），而非真正的网络故障。
- **三处真实缺陷修复**（均会导致连接被静默掐断 → 前端误报"网络错误"）：
  1. **`_try_init_agent` 异常兜底**（[web_server.py](engine/web_server.py)）：import `engine.config`/`engine.log` 和 `init_logging()` 原在 try 块**外**，`create_agent` 也只捕 `ValueError`——任何意外异常直接击穿请求线程，连接被掐断。现整体包进 try，`except Exception` 统一转为可读错误（记录日志 + 写入 `_agent_error`）。
  2. **`/setup` 写 .env 保护**（[web_server.py](engine/web_server.py)）：`.env` 读写（可能因文件锁/杀软占用失败）、`reset_agent`、`get_agent` 全程 try/except，失败返回 500 + 具体错误而非断连。
  3. **页面禁止缓存**（[web_server.py](engine/web_server.py)）：`_serve_page` 加 `Cache-Control: no-store`——浏览器缓存旧版 HTML/JS 会导致 session cookie 不刷新、绕过校验流程，产生"网络错误"假象。
- **前端健壮性**（[index.html](engine/web/index.html)）：`submitSetup` 改为先 `resp.text()` 再 `JSON.parse`，非 JSON 响应（代理/杀软拦截页）不再误报"网络错误"；catch 文案追加"按 Ctrl+F5 强制刷新后重试"提示。
- **端到端验证**：空 `.env` 启动服务 → GET / 下发 session ✓ → /status 未就绪 ✓ → POST /setup（合法格式 key）→ **200 {tools: 7, skills: 2}** ✓ → 无 cookie 403 ✓ → 恶意 Origin 403 ✓。
- **环境提示**：调试期间 `.env` 曾被测试脚本写入假 key（含 `test` 字样触发占位符检测 → 设置报"占位符值"），现已清空为 `DEEPSEEK_API_KEY=`，用户需在网页重新填入真实 Key。
- **排查经验**：Web 端"网络错误"不等于断网——`fetch()` 拒绝仅发生在连接级失败（服务未运行/连接被掐断/CORS 违规）。服务端必须保证任何异常路径都返回 JSON 错误响应，否则前端只能看到误导性的"网络错误"。

### 网页设置 API Key 报 PermissionError：.env 写入加锁重试（2026-08-07）

- **现象**：加固后错误从"网络错误"变为可读文案——`设置过程中发生错误（PermissionError）: [Errno 13] Permission denied: 'T:\\zhixuzhe\\.env'`。真实根因浮出：**写 .env 时遇文件锁**。
- **排查**：当时无 python 进程在跑、`.env` 属性非只读、19 字节正常——排除进程占用与只读属性，指向**杀软实时扫描瞬时锁定**（Defender 对敏感文件按访问扫描）。与 CHANGELOG 已记录的 `agent.log`（RotatingFileHandler delay=True）和 `memory/diary`（Recorder._write_atomic 重试）同类问题，是**第三次同源文件锁问题**。
- **修复**（[web_server.py](engine/web_server.py)）：新增模块级 `_write_env()`——**临时文件写入 + `os.replace` 原子替换 + 3 次重试（0.2s→0.4s 退避）**，沿用 Recorder._write_atomic 的成熟重试模式。
  - 原子替换相比直接覆盖写：写一半崩溃不会损坏 Key 文件；目标文件被共享打开时 rename 成功率更高。
  - 失败 **re-raise**（与 Recorder 的"吞掉不阻断"不同）：Key 必须保存成功，由 `_handle_setup` 转为 500 + 可读错误，用户可见且可重试。
- **验证**：`_write_env` 单测通过（写入/替换/清理正常）；`GetDiagnostics` 无报错；`.env` 保持空、无残留临时文件。
- **遗留提示**：若 3 次重试仍失败（0.6s 总窗口），多半是有程序（记事本/编辑器）正以独占方式打开 `.env`，需关闭后重试——无法在代码侧彻底解决独占锁。

### 修复 _write_env 裸 raise bug + 错误提示引导（2026-08-07）

- **现象**：设置 Key 报新错 `设置过程中发生错误（RuntimeError）: No active exception to reraise`——且证明上一轮的 3 次重试（0.6s）也全部 PermissionError，锁非瞬时。
- **根因（代码 bug）**：`_write_env` 3 次重试全失败后，在 `for` 循环外、`except` 块外执行裸 `raise`——Python 无参 `raise` 只能重抛当前正在处理的异常，循环外裸用即触发 `RuntimeError: No active exception to reraise`。错误信息反而掩盖了真正的 PermissionError。
- **修复**（[web_server.py](engine/web_server.py)）：
  1. `_write_env` 改为保存 `last_error` 显式抛出（`raise last_error if ... else PermissionError(...)`）；重试 3 → 5 次（退避 0.2→0.8s，总窗口 3s），提升扛瞬时锁能力。
  2. `_handle_setup` 新增 `except PermissionError` 专门分支——返回可执行的排查指引（关闭打开 .env 的记事本/VS Code/资源管理器选中预览；检查 Windows 安全中心『受控文件夹访问』），不再显示晦涩的 `[Errno 13]`。
- **验证**：monkeypatch `os.replace` 抛 PermissionError → `_write_env` 5 次重试后正确抛 `PermissionError`（不再 RuntimeError），无残留临时文件；`GetDiagnostics` 无报错。
- **实测**：修复后当场检测 `.env` 可正常独占写入（WRITABLE-OK）——锁为间歇性（用户设置瞬间被资源管理器/杀软占用），重试+指引已覆盖。
- **教训**：Python 无参 `raise` 只能在 `except` 块内使用；循环重试后要抛出累计的异常对象，必须显式引用（`raise last_error`），不能用裸 `raise`。

---

### GitHub 知识学习系统 + 能力面板（2026-08-07）

- **动机**：智序者需要从外部世界主动获取知识，而非仅从自身经历中被动积累。能力面（2 技能 7 工具）是当前最大短板，GitHub 上的优秀开源项目是最高质量的知识来源。此次升级打通"主动学习→知识沉淀→能力档案→技能转化"的完整闭环。
- **核心设计**：
  - **知识分类树**（`engine/knowledge/taxonomy.yaml` + `engine/core/taxonomy.py`）：7 大类别、38 个可学主题，每个叶子节点预配 GitHub 搜索提示词（带 `best practices` 质量信号）、难度等级、所属领域。数据在 taxonomy.py 内联硬编码（零依赖，不与引擎耦合），taxonomy.yaml 是可读参考。
  - **TaxonomyManager**：加载分类树、节点查找、生成搜索查询（自动拼接 `site:github.com`）。
  - **ProfileManager**（`engine/core/profile.py`）：能力档案管理 —— 读写 `memory/profile/abilities.md`，客观指标评级（0条=未接触 / 1-3条=入门 / 4-7条=进阶 / 8+=熟练），学习历史记录。
  - **学习管线**（融入 TaskRunner 的现有四阶段流水线）：
    1. web_search 在 GitHub 找权威仓库（五标准筛选：README 完整、近期活跃、CI badge、被知名项目依赖、代码清晰——需满足 3/5）
    2. git clone --depth 1 到 memory/knowledge/repos/（HITL 确认）
    3. 浏览结构 + 读核心源码（最多 5 文件）
    4. Brain 提炼报告：核心模式 + 代码范式（学模式不抄代码）+ 安全边界 + 对智序者启发
    5. 自动更新能力档案
  - **Web 能力面板**（`engine/web/profile.html`）：能力画像（语言水平表）+ 知识分类卡片墙（展开每个类别看主题列表）+ 点击"开始学习"→ SSE 实时进度条 + 完成后自动标 ✅ + 画像数字刷新。
- **学习→技能的远期路径**：当前产出知识资产（memory/knowledge/），远期从学到的模式中提炼 Skill 罐装计划 → 安全审查 → 冒烟验证 → 注册进 engine/skills/（基因层，可开源繁殖）。三层资产：知识（私有，跨大脑可复用）+ 模板（基因层）+ 技能（基因层，需验证）。
- **换大脑后完全可复用**：知识是 md 文件、技能是 Python + 配置、模板是代码片段，全纯本地文件，零 API 依赖。未来本地部署 DeepSeek 换 Brain 后端，资产原样可用。
- **新文件**：
  - `engine/knowledge/taxonomy.yaml` —— 知识分类树（可读参考）
  - `engine/core/taxonomy.py` —— TaxonomyManager（~235 行，数据内联）
  - `engine/core/profile.py` —— ProfileManager（~170 行）
  - `engine/web/profile.html` —— 能力面板页面（SSE 实时学习进度）
  - `memory/knowledge/languages/` —— 知识库目录
  - `memory/profile/abilities.md` —— 能力档案
- **改造文件**：
  - `engine/factory.py` —— 组装 TaxonomyManager + ProfileManager → Agent
  - `engine/core/loop.py` —— Agent 新增 taxonomy/profile_manager 字段；REPL 新增 `learn`/`taxonomy`/`profile` 命令
  - `engine/web_server.py` —— 新增 GET `/profile`（面板页）、GET `/profile/data`（档案 JSON）、GET `/taxonomy`（分类树 JSON，含已学状态）、POST `/learn`（SSE 流式学习任务）
  - `engine/web/index.html` —— 导航栏新增"知识面板"按钮
  - `config.yaml` —— 新增 `learning` 配置段
- **CLI 使用**：
  - `taxonomy` —— 列出 7 大类 38 主题（已学的标 ✅）
  - `profile` —— 查看能力画像（语言×水平×知识量）
  - `learn <主题ID>` —— 对指定主题启动 GitHub 学习（如 `learn async-python`）
- **验证**：测试 20/20 全绿，零回归；import 链健康；7 类别 38 主题全部正确加载。
- **教训**：
  1. **自建微型 YAML 解析器为过度优化**：taxonomy.yaml 的嵌套结构（列表内对象含多属性）比 config.yaml 复杂一个量级，递归下降解析器易出边界 bug。最终选择数据内联硬编码（Python dataclass），taxonomy.yaml 退化为可读参考。纯数据文件用 Python 原生数据结构比手写解析器更可靠。
  2. **三层资产模式清晰**：知识（灵魂层私有）、技能（基因层需验证）、模板（基因层），学习→沉淀→转化的路径比直接在Skill里写学习逻辑更解耦。

---

### 自动任务模式：规则预筛 + 提示统一（2026-08-07）

- **动机**：用户反馈两点——(1) 主动说"帮我做个任务"时智序者"思考好久"才进入任务模式（因为每次都走 Brain 复杂度判断，多一次 API 往返）；(2) 主动进入和点击任务按钮的显性提示不统一（自动显示"🤖 已自动进入"、手动显示"🔧 任务模式执行中"）。
- **分析**：`should_auto_task` 的 Brain 判断是为"用户没说但任务复杂"兜底的。用户**明确要任务**时判断是纯浪费（答案必然是 true）。提示分两套文案是过度设计——触发来源是细节，UI 应统一。
- **改动**：
  - [loop.py](engine/core/loop.py)：`should_auto_task` 重构为三层决策——
    1. 强任务信号（"任务"/"帮我做"/"做个"/"部署一个"/"调研一下"等 16 个）→ 直接 True，**零 LLM 调用**秒进任务模式；
    2. 强闲聊信号（"你好"/"谢谢"/"再见"等 22 个）→ 直接 False，零 LLM 调用；
    3. 模棱两可 → 才走 Brain 轻量判断。
  - [index.html](engine/web/index.html)：`task_start` 事件移除 auto 分支，统一为"🔧 任务模式执行中 + 目标"，自动/手动进入视觉完全一致。
  - [test_react.py](engine/tests/test_react.py)：新增 2 个测试（强任务信号零 LLM 命中、强闲聊信号零 LLM 降级），断言 `brain.calls == 0`。
- **验证**：测试 25/25 全绿（新增 2 个）。
- **效果**：用户明确要任务 → 秒进任务模式（零判断延迟）；闲聊 → 秒回普通对话（零判断延迟）；只有模棱两可的请求才花一次轻量判断。
- **教训**：显式意图优先于启发式判断——用户已经说清意图时，任何"智能判断"都是延迟。规则预筛把"确定的事"挡在 LLM 之前，让智能资源只花在真正不确定的地方。

---

### 自动任务模式判断（2026-08-07）

- **动机**：用户要求"智序者自己进入任务模式也要显性提示"。排查发现此前任务模式**只存在用户显式触发**（CLI `task`/`chain`/`learn` 命令、Web「任务」按钮），普通对话即使请求复杂也不会自动升级。确认用户意图为"用 Brain 判断复杂度"。
- **设计**：普通对话入口先做一次**轻量意图判断**——不带工具、短提示词（`AUTO_TASK_JUDGE`），Brain 输出 `{"need_task": true/false}`。命中则自动升级为任务模式并显性提示；未命中走原普通对话；判断失败安全降级（不阻塞）。
- **改动**：
  - [config.yaml](config.yaml)：`agent.auto_task: true` 开关，可关闭自动升级（关闭后恢复纯显式触发）。
  - [config.py](engine/config.py)：`AgentConfig` 新增 `auto_task: bool = True`。
  - [loop.py](engine/core/loop.py)：新增 `AUTO_TASK_JUDGE` 判断提示词；`Agent.should_auto_task(user_input)` 方法（JSON 解析兼容 markdown 包裹，失败捕获降级）；CLI 普通对话分支在 `run()` 前先判断，命中则打印横幅（"检测到该请求需要多步骤执行，智序者已自动进入任务模式"）+ 走 `task_runner.run` + 结果入历史。
  - [web_server.py](engine/web_server.py)：`_handle_chat` 在普通对话前先 `agent.should_auto_task(message)`，命中则发 `task_start {auto: true}` → `task_runner.run`（verbose 走 `task_step` 事件）→ `task_done`。
  - [index.html](engine/web/index.html)：`task_start` 事件区分 auto 标识——自动进入显示"🤖 智序者已自动进入任务模式（检测到该请求需要多步骤执行）"，手动任务显示"🔧 任务模式执行中"。
  - [test_react.py](engine/tests/test_react.py)：新增 3 个测试（命中 True / 简单问候 False / 无效 JSON 降级 False）。
- **验证**：测试 23/23 全绿（新增 3 个）；配置 `auto_task=True` 正确加载。
- **代价**：普通对话每次多一次轻量 API 调用（不带工具、仅几 token 输出，成本极低）。可通过 `agent.auto_task: false` 关闭。
- **教训**：功能设计时要区分"用户显式触发"和"系统自动判断"两条路径，二者提示语、成本、安全边界都不同；自动路径必须带安全降级（判断失败不阻塞主流程）。

---

### 工具调用上限提升 + 任务模式显性提示（2026-08-07）

- **动机**：排查发现工具调用次数少的原因之一是 `max_tool_rounds: 5` 过严——日记中 3 次 `[已达到最大工具调用轮次]` 截断（uv 学习任务步骤 4/5 未执行）。同时用户反馈任务模式缺少显性提示，进入时无感知。
- **改动**：
  - [config.yaml](config.yaml)：普通对话 `agent.max_tool_rounds: 5 → 10`；任务模式新增 `task.max_tool_rounds: 15`（每步执行轮次上限，高于普通对话）；`task.max_steps: 5 → 8`。
  - [config.py](engine/config.py)：`TaskConfig` 新增 `max_tool_rounds: int = 15` 字段，默认 `max_steps` 同步为 8。
  - [task.py](engine/core/task.py)：`_execute_step` 调用 `react_loop` 时传入 `max_rounds=config.task.max_tool_rounds`（15），任务模式每步可调 15 轮工具；`PLAN_SYSTEM` 的"不超过 5 步"改为由 `config.task.max_steps` 动态注入，避免提示词与配置不一致。
  - [loop.py](engine/core/loop.py)：CLI 的 `task` / `chain` / `learn` 命令进入时打印显性横幅（任务模式已启动 + 目标 + 技能链 / 学习主题），用户对执行模式有明确感知。
  - [index.html](engine/web/index.html)：Web 端 `toggleTaskMode()` 切换任务模式时在聊天区插入系统提示（"🔧 已进入任务模式…" / "已退出任务模式"）；`task_start` SSE 事件提示升级为"🔧 任务模式执行中 + 目标"，与普通对话明确区分。
- **验证**：测试 20/20 全绿；`config.agent.max_tool_rounds=10` / `task.max_tool_rounds=15` / `task.max_steps=8` 正确加载。
- **教训**：工具轮次上限是"能力 vs 成本"的平衡点，但当前阶段应优先保能力——任务模式每步 15 轮、普通对话 10 轮足够覆盖真实任务，且 HITL 确认仍然挡在 run_shell 前面，安全不受影响。

---

### 学习系统 P0 级 Bug 修复（2026-08-07）

- **现象**：首次上线时三个主流程缺陷——前台阻塞（关页即停）、伪进度（`+15%` 视觉欺骗）、全量保存（中断全丢）。用户实测反馈后排查确认。
- **P0-1：学习成果从未落盘**：全项目无代码向 `memory/knowledge/languages/` 写内容。完整报告只在内存流一次即蒸发。修复：
  - [recorder.py](engine/core/recorder.py)：新增 `record_knowledge(parent, topic, report)` ——原子写入 `memory/knowledge/languages/<领域>/<主题>.md`（临时文件 + `os.replace`）。
  - [web_server.py](engine/web_server.py)：后台线程学习成功后调 `agent.recorder.record_knowledge()`；异常兜底不影响线程。
  - [loop.py](engine/core/loop.py)：CLI `learn` 命令完成后同样写知识文件。
- **P0-2：失败也记"已学"导致能力档案污染**：用户 HITL 拒绝 clone 或步骤执行失败 → 能力档案依然 `count + 1`。修复：
  - [task.py](engine/core/task.py)：`TaskRunner` 新增 `last_step_results` 公开属性，每次 `run()` 后更新。
  - [web_server.py](engine/web_server.py) + [loop.py](engine/core/loop.py)：学习完成后检测 `step_results` 是否含"执行失败"或"确认被拒"，是则跳过知识落盘和档案更新，提示失败。
- **P0-3：学完的知识不会在对话中生效**：`MemoryReader` 只检索 `diary` 和 `experience`，不认识 `knowledge` 目录。修复：
  - [memory_reader.py](engine/core/memory_reader.py)：新增 `retrieve_knowledge()` 方法；`retrieve()` 综合检索三源（日记→经验→知识）；`_search_dir` 对 knowledge 目录走递归（`**/*.md`）；新增 `_extract_date_from_header` 从知识文件头提取日期。
  - [memory_manager.py](engine/core/memory_manager.py)：source label 新增"知识"。
- **P1-1：后台学习**：前端关页不再中断任务。修复：
  - [web_server.py](engine/web_server.py)：`_handle_learn` 改为启动后台线程 → 立即返回 `learn_id`；新增 `_run_learn_in_background` 模块级函数（在后台线程执行完整学习管线）；新增 `GET /learn/status?learn_id=X` 供前端轮询；新增 `_learn_tasks` 全局状态 dict（线程安全）。
  - [profile.html](engine/web/profile.html)：前端从 SSE 流改为 `POST /learn` 获取 `learn_id` → `setInterval` 每 1.5s 轮询 `GET /learn/status`。
- **P1-2：真实进度**：修复前端伪进度条（`cur + 15%` → 真实 `step/total_steps * 100`）。`_run_learn_in_background` 的 `progress_callback` 从 verbose 消息中提取 `[i/n]` 模式，写入 `_learn_tasks`。前端据此算百分比。
- **P1-3：断点续传**：学习 goal 中新增步骤——先检查 `memory/knowledge/repos/` 下是否已有该仓库，已有则跳过 clone；检查 repos 总大小是否超 200MB，超限提示清理。
- **P2：异常兜底**：`record_knowledge` 和 `record_learning` 均用 try/except 包裹，失败不阻断主流程。
- **验证**：测试 20/20 全绿，零回归；import 链全链路验证通过（TaxonomyManager/ProfileManager/MemoryReader/Recorder/MemoryManager/TaskRunner）。
- **教训**：首次上线功能应做"全链路烟雾测试"——从"学一个主题"走到"在对话中引用学到的知识"，逐环节检查中间产物是否真的生成/索引/可检索。局部代码正确不能保证链路闭合。
