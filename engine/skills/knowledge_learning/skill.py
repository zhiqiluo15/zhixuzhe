"""知识学习技能 —— 罐装的GitHub源码学习计划

封装"搜索→clone→阅读源码→提炼报告"的最佳实践流程，每步有明确的成功条件，
避免LLM即兴规划导致的步骤遗漏或轮次耗尽。
"""

from engine.skills.base import Skill


class KnowledgeLearningSkill(Skill):
    """GitHub仓库搜索+源码阅读+知识提炼（用于learn命令）"""

    name = "knowledge_learning"
    description = "从GitHub搜索权威开源仓库，浅克隆后阅读核心源码，提炼结构化知识报告"

    # 这个技能不通过自然语言触发（learn是显式命令），triggers留空
    triggers = []

    def __init__(self, topic_name: str = "", search_query: str = "", repo_hint: str = ""):
        """
        Args:
            topic_name: 学习主题名（如"包管理"、"异步编程"）
            search_query: GitHub搜索关键词
            repo_hint: 推荐仓库提示（如"astral-sh/uv"），可为空
        """
        self.topic_name = topic_name
        self.search_query = search_query
        self.repo_hint = repo_hint

    def plan(self, goal: str) -> list[str]:
        repo_hint_text = f"\n推荐仓库：{self.repo_hint}" if self.repo_hint else ""
        return [
            # 步骤1：搜索仓库
            (
                f"使用 web_search 在 GitHub 上搜索关于「{self.topic_name}」最权威最活跃的开源仓库。"
                f"搜索关键词：{self.search_query}{repo_hint_text}。"
                f"要求：找到 README 完整、近6个月有commit、stars最多的1个官方或知名社区仓库。"
                f"输出：仓库完整URL（owner/repo格式）和一句话简介。"
            ),
            # 步骤2：浅克隆
            (
                f"使用 run_shell 将上一步选定的仓库执行 git clone --depth 1 到 memory/knowledge/repos/ 目录下"
                f"（目录名用仓库名）。如果目标目录已存在则跳过clone直接使用。"
                f"clone成功后用 run_shell 执行 dir 或 ls 确认目录存在并列出顶层文件结构。"
                f"如果clone失败（网络/权限问题），改用 web_fetch 获取仓库 README 和核心文档内容作为替代。"
            ),
            # 步骤3：探索结构并定位核心文件
            (
                f"使用 list_files 和 search_file（或者 run_shell 的 Get-ChildItem/dir）查看已clone仓库的目录结构，"
                f"重点关注 src/、lib/、核心模块目录，以及 README.md、Cargo.toml/pyproject.toml 等配置文件，"
                f"确定最多5个需要阅读的核心源码文件（入口文件、核心逻辑模块，而非测试/文档/示例）。"
                f"输出：要阅读的文件路径列表（相对仓库根目录），以及选择每个文件的理由。"
            ),
            # 步骤4：阅读核心源码
            (
                f"使用 read_file 逐个阅读上一步确定的核心源码文件（最多5个），每个文件关注："
                f"核心数据结构、关键算法、设计模式、错误处理方式、对外接口。"
                f"如果文件过长，优先读取开头的模块文档、类/函数定义和关键注释，跳过琐碎实现细节。"
                f"如果read_file失败或文件是二进制，跳过该文件并尝试找替代文件。"
            ),
            # 步骤5：提炼结构化报告
            (
                f"基于搜索结果、仓库README和阅读到的源码内容，输出结构化学习报告，包含以下章节：\n"
                f"### 1. 仓库定位与现状\n"
                f"- 选定仓库、URL、简介、活跃度（stars/commit频率）\n"
                f"### 2. 核心设计模式与架构亮点\n"
                f"（表格形式：模式/组件 + 说明）\n"
                f"### 3. 关键代码范式\n"
                f"（核心数据结构、关键算法、接口设计、错误处理等具体实现，引用文件路径）\n"
                f"### 4. 安全边界与常见踩坑点\n"
                f"（如果源码中有相关设计）\n"
                f"### 5. 对智序者的启发\n"
                f"（设计哲学、可迁移经验、值得借鉴的模式）\n\n"
                f"学模式不抄代码，重点提炼可复用的设计思想。"
            ),
        ]
