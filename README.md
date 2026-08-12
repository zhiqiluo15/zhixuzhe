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

## 可选增强：语义检索（按需启用）

记忆检索默认走轻量的 2-gram 关键词匹配，**零依赖零下载**即可正常使用。
当记忆量积累到数百条、出现"聊过但检索不到"的场景时，可启用向量语义检索：

```bash
# 1. 安装依赖（torch 通常已随项目安装）
python -m pip install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 首次检索时自动下载 BGE 中文模型（约 100MB）
#    下载慢可设镜像：
$env:HF_ENDPOINT = 'https://hf-mirror.com'   # PowerShell
```

- 配置开关：`config.yaml` → `memory.semantic`（默认 `enabled: true`，懒加载）
- 未安装/下载失败时**自动降级**为关键词检索，不影响任何功能
- 效果：向量与关键词结果 RRF 融合，同义改写、概念相关（如"训练"↔"微调"）也能命中

## 发布一个进化版

只发布引擎与公共日志，灵魂层被 .gitignore 强制隔离：

```bash
git add engine/ CHANGELOG.md README.md .gitignore
git commit -m "feat: 新增 X 手脚 / 优化 Y 机制"
```

### 开源守卫（push 自动拦截私有内容）

仓库自带 **Git pre-push 钩子**（`.githooks/pre-push` + `scripts/guard_push.py`），
push 前自动扫描本次推送涉及的文件，发现私有/敏感内容立即拒绝：

- **私有路径**：`memory/`、`logs/`、`.runtime/`、`.trae/`、`videos/`、`.env`、图片素材等
- **敏感内容**：`sk-` 密钥、`api_key=` 等带真实值的密钥赋值

clone 后启用一次（必须）：

```bash
git config core.hooksPath .githooks
```

误推私有文件被拦截时，用 `git rm --cached <文件>` 解除跟踪后重新提交；
确需推送示例密钥等，可 `git push --no-verify`（谨慎使用）。

## 许可

- 本项目代码：MIT License
- 模型基座：DeepSeek（MIT License，微调/商用/再分发自由）
