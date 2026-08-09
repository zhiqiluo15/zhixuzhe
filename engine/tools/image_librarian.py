#!/usr/bin/env python3
"""智序者 · 美术资源库自动分类工具

把 assets/images/_inbox 里的图片按「图片类型」自动分类归档：
  照片 / 插画 / 截图 / 图标 / 其他

分类逻辑（规则预判 + CLIP 智能复核）：
  1. 规则预判（快、确定性强）：
     - 含透明通道（半透明像素多）→ 图标
     - 极小尺寸（宽高 ≤ 64px）→ 图标
     - 量化色彩数极少（≤ 4）→ 图标
  2. CLIP 复核：剩余图片用多语言 CLIP（xlm-roberta-base-ViT-B-32，
     支持中文 prompt）计算与各类型的相似度概率
  3. 置信度阈值：最高概率 < 0.45 → 归入「其他」
     色彩数少（≤ 12）且 CLIP 偏插画/图标 → 归「图标」

用法：
  python engine/tools/image_librarian.py                    # 扫描并归档 _inbox
  python engine/tools/image_librarian.py --inbox path --dry-run

API：
  classify_and_archive() -> str     # 返回报告，供 Tool 调用

依赖（venv）：
  .venv\\Scripts\\python.exe -m pip install torch open_clip_torch
  模型首次调用自动下载（约 600MB，走 HF 镜像 hf-mirror.com）
"""

import os
import shutil
import sys
import time
from pathlib import Path

# 确保项目根在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.log import get_logger

logger = get_logger(__name__)

# 美术资源库根目录（分类后归档区）
IMAGES_DIR = ROOT / "assets" / "images"
INBOX_DIR = IMAGES_DIR / "_inbox"

# 图片类型 → 归档子目录名
TYPES = ["照片", "插画", "截图", "图标", "其他"]

# 支持的文件扩展名
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}

# CLIP 各类型的模板（层级二分类，每步仅两类，准确率更高）
# 第一步：截图 vs 其它（截图识别 CLIP 极准）
CLIP_SCREENSHOT_TEMPLATES = {
    "截图": ["一张屏幕截图，软件界面", "一张电脑屏幕的截屏", "一张网页或应用的截图"],
    "其它": ["一张照片", "一张插画"],
}
# 第二步：照片 vs 插画（非截图非图标部分）
CLIP_ART_TEMPLATES = {
    "照片": ["一张真实的照片，相机拍摄，有自然光影细节", "真实世界的照片"],
    "插画": ["一张手绘插画，有笔触和艺术风格", "一张绘画作品"],
}

# 置信度阈值：低于此值归「其他」
CONF_THRESHOLD = 0.45

# 规则预判阈值
ICON_MIN_SIZE = 64        # 宽高 ≤ 此尺寸视为图标
ICON_MAX_COLORS = 4       # 量化色彩数 ≤ 此值视为图标（纯色扁平图标）
ICON_SMALL_FLAT = (256, 24)  # 尺寸 ≤ 256 且色彩 ≤ 24 → 小尺寸扁平图视为图标
ICON_MAX_COLORS_CLIP = 12  # CLIP 复核后色彩数 ≤ 此值且偏插画/图标 → 图标


def _load_clip():
    """懒加载多语言 CLIP 模型（首次调用下载权重，约 600MB，走 HF 镜像）。

    返回 (model, preprocess, tokenizer, {阶段名: 标签矩阵})，
    标签矩阵为每阶段两类的平均文本特征。
    """
    if os.environ.get("HF_ENDPOINT") is None:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    import open_clip
    import torch

    m, _, preprocess = open_clip.create_model_and_transforms(
        "xlm-roberta-base-ViT-B-32", pretrained="laion5b_s13b_b90k"
    )
    m.eval()
    tok = open_clip.get_tokenizer("xlm-roberta-base-ViT-B-32")

    def build_matrix(templates: dict[str, list[str]]):
        all_texts = [t for g in templates.values() for t in g]
        text_feats = m.encode_text(tok(all_texts))
        text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)
        feats = []
        i = 0
        for group in templates.values():
            feats.append(text_feats[i : i + len(group)].mean(dim=0))
            i += len(group)
        mat = torch.stack(feats)
        return mat / mat.norm(dim=-1, keepdim=True)

    labels = {
        "shot": build_matrix(CLIP_SCREENSHOT_TEMPLATES),
        "art": build_matrix(CLIP_ART_TEMPLATES),
    }
    return m, preprocess, tok, labels


def _clip_probs(clip_model, preprocess, img, label_mat):
    """计算图片与某阶段标签矩阵的 softmax 概率（返回 list，顺序同模板 dict）。"""
    import torch

    proc_img = preprocess(img.convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        img_feat = clip_model.encode_image(proc_img)
    img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
    probs = (100 * img_feat @ label_mat.T).softmax(dim=-1)[0]
    return [float(p.detach()) for p in probs]


def _quantize_colors(img):
    """量化统计图片主色数量（感知相似色合并），用于图标/扁平插画预判。"""
    import numpy as np
    from PIL import Image

    small = img.convert("RGB").resize((64, 64), Image.LANCZOS)
    arr = np.array(small).reshape(-1, 3)
    # 量化到 4bit/通道 → 4096 桶，统计非空桶
    buckets = (arr // 16).astype(np.int32)
    unique = len(np.unique(buckets, axis=0))
    return unique


def _has_transparency(img) -> bool:
    """检测图片是否含透明通道且有半透明像素（PNG 图标/贴图特征）。"""
    import numpy as np

    if img.mode not in ("RGBA", "LA", "P"):
        return False
    rgba = img.convert("RGBA")
    alpha = np.array(rgba.getchannel("A"))
    return (alpha < 250).sum() / alpha.size > 0.02


def _classify_one(img, clip_ctx, mode) -> tuple[str, dict]:
    """对单张图分类，返回 (类型, 详情)。

    层级策略：
      1. 规则预判 → 图标（透明通道 / 极小尺寸 / 色彩极少）
      2. CLIP 阶段一：截图 vs 其它（截图概率 ≥ 阈值 → 截图）
      3. CLIP 阶段二：照片 vs 插画
      4. 任一阶段置信度不足 → 其他
    mode: 'clip' 走 CLIP；'rule' 仅规则（无模型环境时兜底）。
    """
    w, h = img.size
    # 规则预判
    if _has_transparency(img) or (w <= ICON_MIN_SIZE and h <= ICON_MIN_SIZE):
        return "图标", {"rule": "透明通道/极小尺寸"}

    colors = _quantize_colors(img)
    if colors <= ICON_MAX_COLORS:
        return "图标", {"rule": f"量化色彩数 {colors} 过少"}
    # 小尺寸扁平图形（logo/图标常用形态）
    if (
        w <= ICON_SMALL_FLAT[0]
        and h <= ICON_SMALL_FLAT[0]
        and colors <= ICON_SMALL_FLAT[1]
    ):
        return "图标", {"rule": f"小尺寸扁平图（{w}x{h}, {colors} 色）"}

    if mode == "rule":
        return "照片", {"rule": "无 CLIP 环境，规则兜底"}

    clip_model, preprocess, _tok, labels = clip_ctx

    # 阶段一：截图 vs 其它
    shot_probs = _clip_probs(clip_model, preprocess, img, labels["shot"])
    shot_prob = shot_probs[0]  # 截图概率
    detail = {"shot": f"{shot_probs[0]:.2f}", "art": ""}
    if shot_prob >= 0.6:
        return "截图", detail

    # 阶段二：照片 vs 插画
    art_probs = _clip_probs(clip_model, preprocess, img, labels["art"])
    detail["art"] = f"照片={art_probs[0]:.2f} 插画={art_probs[1]:.2f}"
    art_idx = 0 if art_probs[0] >= art_probs[1] else 1
    art_name = ("照片", "插画")[art_idx]
    art_prob = max(art_probs)

    # 色彩极少且偏插画 → 图标（扁平插画素材）
    if colors <= ICON_MAX_COLORS_CLIP and art_name == "插画" and art_prob >= 0.3:
        return "图标", detail

    if art_prob < CONF_THRESHOLD:
        return "其他", detail
    return art_name, detail


def classify_and_archive(
    inbox: str = "",
    dry_run: bool = False,
    use_clip: bool = True,
) -> str:
    """扫描 _inbox 图片并分类归档到 assets/images/<类型>/，返回报告。"""
    from PIL import Image

    inbox_dir = Path(inbox) if inbox else INBOX_DIR
    if not inbox_dir.exists():
        return f"❌ 入库目录不存在: {inbox_dir}"

    files = [
        f
        for f in sorted(inbox_dir.iterdir())
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    ]
    if not files:
        return f"📭 入库目录为空（{inbox_dir}），无需分类"

    lines = []
    lines.append("── 美术资源库自动分类 ──────────────")
    lines.append(f"入库: {inbox_dir}  共 {len(files)} 张图片")

    # 加载 CLIP（懒加载；失败则退化为纯规则）
    clip_ctx = None
    mode = "clip" if use_clip else "rule"
    if use_clip:
        try:
            t0 = time.perf_counter()
            clip_ctx = _load_clip()
            lines.append(f"CLIP 模型加载完成（{time.perf_counter() - t0:.1f}s，支持中文 prompt）")
        except Exception as exc:
            logger.warning(f"CLIP 加载失败，退化为规则分类: {exc}")
            mode = "rule"

    # 预创建类型目录
    for t in TYPES:
        (IMAGES_DIR / t).mkdir(parents=True, exist_ok=True)

    counts = {t: 0 for t in TYPES}
    details = {}
    for f in files:
        try:
            with Image.open(f) as im:
                im.load()
                fmt = (im.format or "").upper()
                # SVG 直接按图标/插画处理（矢量图形素材）
                if f.suffix.lower() == ".svg":
                    kind = "图标" if any(k in f.name.lower() for k in ("icon", "logo", "ico")) else "插画"
                    detail = {"rule": "SVG 矢量素材"}
                else:
                    kind, detail = _classify_one(im, clip_ctx, mode)
                counts[kind] += 1
                details[f.name] = {"kind": kind, "detail": detail, "size": f"{im.width}x{im.height}", "format": fmt}
        except Exception as exc:
            counts["其他"] += 1
            details[f.name] = {"kind": "其他", "detail": {"error": str(exc)}, "size": "-", "format": "-"}

    # 执行归档（非 dry-run）
    archived = []
    for f in files:
        info = details[f.name]
        kind = info["kind"]
        dest_dir = IMAGES_DIR / kind
        dest = dest_dir / f.name
        if not dry_run and f != dest:
            shutil.move(str(f), str(dest))
        archived.append((f.name, kind))

    lines.append("── 分类结果 ────────────────────────")
    for t in TYPES:
        lines.append(f"  {t}: {counts[t]} 张")
    for name, info in details.items():
        d = "; ".join(f"{k}={v}" for k, v in info["detail"].items())
        lines.append(f"  [{info['kind']}] {name} ({info['size']}, {info['format']}) {d}")

    if dry_run:
        lines.append("（dry-run，未移动文件）")
    else:
        # 更新 catalog.md 索引
        _write_catalog()
        lines.append(f"✅ 已归档 {len(archived)} 张 → {IMAGES_DIR}")
        lines.append("索引已更新: assets/images/catalog.md")

    logger.info("\n".join(lines))
    return "\n".join(lines)


def _write_catalog() -> None:
    """生成 assets/images/catalog.md 资源索引。"""
    from PIL import Image

    lines = [
        "# 智序者 · 美术资源库目录",
        "",
        "> 自动生成（image_librarian 工具）。图片放入 `_inbox/` 后运行分类工具自动归档。",
        "",
    ]
    for t in TYPES:
        d = IMAGES_DIR / t
        if not d.exists():
            continue
        files = sorted(d.glob("*"))
        if not files:
            continue
        lines.append(f"## {t}（{len(files)}）")
        lines.append("")
        for f in files:
            try:
                with Image.open(f) as im:
                    dim = f"{im.width}x{im.height}"
            except Exception:
                dim = "?"
            lines.append(f"- {f.name} （{dim}）")
        lines.append("")
    (IMAGES_DIR / "catalog.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="智序者 · 美术资源库自动分类")
    parser.add_argument("--inbox", default="", help="入库目录（默认 assets/images/_inbox）")
    parser.add_argument("--dry-run", action="store_true", help="只预览分类结果，不移动文件")
    parser.add_argument("--no-clip", action="store_true", help="跳过 CLIP 模型，仅规则分类")
    args = parser.parse_args()

    print(classify_and_archive(args.inbox, args.dry_run, use_clip=not args.no_clip))


if __name__ == "__main__":
    main()
