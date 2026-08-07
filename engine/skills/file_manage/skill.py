"""批量文件管理技能 —— 列出、重命名、移动、复制、删除、内容替换

这是智序者第五个罐装技能，封装"批量文件整理"这一高频通用任务的最佳实践流程：
list_files 查看文件清单 → batch_files 批量操作（默认 dry-run 预览 + HITL 确认）→ 产出操作报告。

触发词设计遵循 Router 沉淀原则（CHANGELOG 2026-08-07）：
- 触发词一律带"文件/批量/整理"等绑定词，保证领域特异性；
- 不用裸"整理/管理/操作"等宽泛词，避免与代码/数据意图混淆。
"""

from engine.skills.base import Skill


class FileManageSkill(Skill):
    """批量文件管理：查看清单 → 批量操作（预览+确认）→ 操作报告"""

    name = "file_manage_batch"
    description = "批量管理项目文件：列出文件、批量重命名/移动/复制/删除/内容替换（危险操作先预览后确认）"

    triggers = [
        # 中文 - 批量动作
        "批量重命名", "批量改名", "重命名文件", "批量移动",
        "批量复制", "批量删除", "批量替换", "批量处理文件",
        "批量操作文件", "批量清理",
        # 中文 - 文件整理
        "整理文件", "文件整理", "清理文件", "清理临时文件",
        "清理日志", "清理缓存", "清理目录",
        "归档文件", "文件管理", "整理一下文件", "整理下文件",
        # 英文
        "batch rename", "rename files", "bulk rename",
        "organize files", "organize project files",
        "clean up files", "clean up temp files", "cleanup",
        "batch move", "batch delete", "batch replace",
        "file management", "tidy files", "tidy up",
        "manage files", "bulk files",
    ]

    def plan(self, goal: str) -> list[str]:
        return [
            "使用 list_files 查看目标目录/匹配文件清单（名称、大小、修改时间），确定待管理的文件范围",
            "使用 batch_files 执行批量操作（rename/move/copy/delete/replace）：先以 dry_run=True 预览改动清单，确认无误后再以 dry_run=False 实际执行；delete 等危险操作必须严格走 预览→确认 流程",
            "产出操作报告：执行的操作类型与文件数、关键改动前后对比、跳过/异常项、后续建议；若用户目标不明确（如缺目标目录/替换文本），在报告中明确说明所需信息",
        ]
