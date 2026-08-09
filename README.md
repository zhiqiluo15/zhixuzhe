# 智序者（zhixuzhe）

> 智慧与秩序：一个自进化的开源智能体。

**特色**：用现在成熟的模型基座，为将来的本地模型攒经验。

## 是什么

智序者是一个"自进化"的智能体项目，最终目标是 AGI：

- **大脑**：模型无关基座（当前 DeepSeek，可换任何 OpenAI 兼容模型 / 本地部署）
- **手脚**：自建工具层（宿主机检测、GPU 算力验证等），不依赖第三方
- **记忆**：日志驱动的自进化闭环 —— 变更 → 记录 → 回顾 → 优化

**攒经验哲学**：现在的每一份记忆与经验都不会浪费——先跑通进化机制、积累经验资产，等本地模型成熟时直接复用。

## 三层架构

| 层 | 目录 | 内容 | 可否开源 |
|---|---|---|---|
| **基因层** | `engine/` | 工具、技能、模板、公共经验 | ✅ 随项目发布 |
| **灵魂层** | `memory/` | 身体档案、私人经历、个人经验 | 🔒 私有，gitignore 隔离 |
| **公共日志** | `CHANGELOG.md` | 机制/工具/架构决策记录 | ✅ 随项目发布 |

核心哲学：**开源分享的是"基因"（引擎机制），每个人都能长出属于自己的智序者（私有记忆）**。发布的进化版只包含引擎改进与公共经验，天然不含私密信息。

## 快速开始

### 1. 配置 API Key

```bash
# 方式一：项目根 .env 文件（推荐，已 gitignore）
echo DEEPSEEK_API_KEY=你的key > .env

# 方式二：环境变量
$env:DEEPSEEK_API_KEY='你的key'     # PowerShell
export DEEPSEEK_API_KEY='你的key'    # Linux/macOS
```

获取 Key：https://platform.deepseek.com/api_keys

### 2. 启动 Agent

```bash
# 安装核心依赖
python -m pip install -r requirements.txt

# 可选：GPU 算力验证需要 CUDA 版 PyTorch（RTX 50 系请用 cu128 源）
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128

# 启动交互式 Agent
python -m engine.core
```

REPL 命令：
- 直接输入文字 → 普通对话（自动调工具）
- `task <目标>` → 自主任务模式（规划→执行→综合）
- `reset` → 重置对话历史
- `exit` → 退出

### 3. 单独运行工具

```bash
# 感知身体：检测宿主机并生成身体档案（写入 memory/body/）
python engine/tools/detect_host.py

# 体检 GPU：验证 CUDA 算力
python engine/tools/verify_gpu.py
```

## 发布一个进化版

只发布引擎与公共日志，灵魂层被 .gitignore 强制隔离：

```bash
git add engine/ CHANGELOG.md README.md .gitignore
git commit -m "feat: 新增 X 手脚 / 优化 Y 机制"
```

## 许可

- 本项目代码：MIT License
- 模型基座：DeepSeek（MIT License，微调/商用/再分发自由）
