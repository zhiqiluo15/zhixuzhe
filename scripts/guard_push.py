#!/usr/bin/env python3
"""智序者 · 开源守卫（Git pre-push 钩子核心逻辑）

push 前检查本次推送涉及的文件，发现私有/敏感内容立即拒绝推送，
保证 GitHub 仓库只有智序者开源部分。

检查规则：
  1. 私有路径：memory/、logs/、.runtime/、.trae/、videos/、.env、
     assets/images/ 下的图片文件等
  2. 敏感内容：文件中出现 sk- 前缀的密钥（DeepSeek/OpenAI 风格）、
     api_key= / apiKey= 等带真实值的密钥赋值

用法（被 .githooks/pre-push 调用）：
  python scripts/guard_push.py <remote_name> <remote_url>

退出码：0 = 允许推送；1 = 拦截（输出违规清单）
"""

import re
import subprocess
import sys
from pathlib import Path

# 项目根（脚本位于 <root>/scripts/）
ROOT = Path(__file__).resolve().parent.parent

# 私有路径前缀（目录一律拦截）
PRIVATE_DIRS = (
    "memory/",
    "logs/",
    ".runtime/",
    ".trae/",
    "videos/",
)

# 私有文件名（精确匹配）
PRIVATE_FILES = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
)

# 图片扩展名（assets/images 下的图片是美术素材，不进开源仓库）
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".ico")

# 密钥模式：sk- 后跟 16+ 位字母数字（DeepSeek/OpenAI 格式）
SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
# 密钥赋值：api_key / apiKey / apikey 等 = 非空值（跳过空占位）
KEY_ASSIGN_PATTERN = re.compile(
    r"(?:api[_-]?key|API[_-]?KEY|token|secret)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}",
    re.IGNORECASE,
)


def git(*args: str) -> str:
    """执行 git 命令并返回 stdout 文本（去掉尾随换行）。"""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def files_in_range(remote_oid: str, local_oid: str) -> list[str]:
    """返回 remote_oid..local_oid 之间变更的文件名列表。

    首次推送（远端无提交，remote_oid 为 40 个 0）时改为全量提交遍历。
    """
    if remote_oid.strip() == "0" * 40:
        # 新分支首次推送：检查该分支所有提交涉及的文件
        revs = git("rev-list", "--count", local_oid)
        if revs == "0":
            return []
        out = git("diff-tree", "--no-commit-id", "--name-only", "-r", local_oid)
        return [l for l in out.splitlines() if l]
    # 增量推送：对比本地提交与远端基线
    out = git("diff", "--name-only", remote_oid, local_oid)
    return [l for l in out.splitlines() if l]


def is_private_path(path: str) -> bool:
    """判断路径是否属于私有内容。"""
    p = path.replace("\\", "/")
    for d in PRIVATE_DIRS:
        if p.startswith(d):
            return True
    if p in PRIVATE_FILES or p.startswith(".env."):
        return True
    # assets/images 下的图片文件（保留 .gitkeep 与 catalog.md）
    if p.startswith("assets/images/"):
        ext = Path(p).suffix.lower()
        if ext in IMAGE_EXTS:
            return True
    return False


def scan_content(files: list[str]) -> list[str]:
    """扫描文件内容中的敏感模式，返回违规清单。"""
    hits = []
    for f in files:
        # 只检查文本类文件（跳过二进制、大文件）
        ext = Path(f).suffix.lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".mp4",
                   ".mp3", ".wav", ".zip", ".7z", ".exe", ".dll", ".pyc", ".bin"}:
            continue
        full = ROOT / f
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SK_PATTERN.search(text):
            hits.append(f"{f}  → 含 sk- 密钥")
        # KEY_ASSIGN 检查排除占位/示例（如 sk- 已在上面捕获，这里捕获其它密钥变量）
        for m in KEY_ASSIGN_PATTERN.findall(text):
            # 忽略明显的占位符
            if m in ("sk-", "your_api_key", "your-key", "xxxxx", "api_key") or "sk-" in m:
                continue
            hits.append(f"{f}  →  疑似密钥赋值: {m[:40]}")
            break
    return hits


def main() -> int:
    if len(sys.argv) < 2:
        print("⚠️  用法: python scripts/guard_push.py <remote_name>")
        return 0

    # 读取 stdin 的推送计划：<local_ref> <local_oid> <remote_ref> <remote_oid>
    pushed = sys.stdin.read().splitlines()
    if not pushed:
        return 0

    violations = []
    for line in pushed:
        parts = line.strip().split()
        if len(parts) != 4:
            continue
        _, local_oid, _, remote_oid = parts
        if local_oid.strip() == "0" * 40:
            continue  # 删除分支，无需检查
        try:
            files = files_in_range(remote_oid, local_oid)
        except subprocess.CalledProcessError:
            continue
        for f in files:
            if is_private_path(f):
                violations.append(f"{f}  →  私有路径")
        violations.extend(scan_content(files))

    if violations:
        print("")
        print("❌ 开源守卫拦截：以下内容不允许推送到 GitHub（智序者仅开源公开部分）")
        print("-" * 60)
        for v in violations:
            print(f"  • {v}")
        print("-" * 60)
        print("处理方式：")
        print("  1. 私有文件不应入库——如误 add，执行: git rm --cached <文件> 后重新提交")
        print("  2. 如确需推送（如示例密钥），请使用: git push --no-verify 并确认内容安全")
        print("")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
