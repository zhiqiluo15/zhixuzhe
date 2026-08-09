#!/usr/bin/env python3
"""智序者 · 抖音竖屏视频制作工具

把一段口播文案制作成抖音竖屏短视频：
  文案切句 → 逐句配音 → PIL 生成渐变字幕背景 → moviepy 合成 MP4

配音引擎（voice 参数）：
  zh-CN-* 等 edge-tts 音色  → edge-tts 优先，失败回退 Windows 本地 SAPI5
  cosyvoice:中文女声         → 本地 CosyVoice 零样本克隆（需 .runtime/cosyvoice 私有部署，
                               自动拉起本地服务，失败回退 SAPI5）

用法：
  python engine/tools/video_maker.py --text "口播文案（必填）"
  python engine/tools/video_maker.py --text "文案" --voice zh-CN-YunxiNeural --out videos/out.mp4
  python engine/tools/video_maker.py --text "文案" --voice cosyvoice:中文女声 --out videos/out.mp4
  python engine/tools/video_maker.py --text "文案" --voice cosyvoice:中文女声 --prompt-wav cross --out videos/out.mp4

API：
  make_douyin_video(text, out_path, voice) -> str        # 返回报告，供 Tool 调用（text 必填）

依赖（venv）：
  .venv\\Scripts\\python.exe -m pip install edge-tts moviepy Pillow
"""

import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# 确保项目根在 sys.path 中（脚本直接 python engine/tools/video_maker.py 运行时需要）
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from engine.log import get_logger

logger = get_logger(__name__)

# 竖屏规格
W, H = 1080, 1920
FPS = 30


def split_sentences(text: str) -> list[str]:
    """按中英文句末标点切句，保留标点"""
    parts = re.split(r"(?<=[。！？.!?])", text)
    return [p.strip() for p in parts if p.strip()]


def find_cjk_font() -> str:
    """找 Windows 中文字体（微软雅黑优先，回退黑体/宋体）"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
        r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑粗体
        r"C:\Windows\Fonts\simhei.ttf",   # 黑体
        r"C:\Windows\Fonts\simsun.ttc",   # 宋体
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise FileNotFoundError("未找到中文字体（C:\\Windows\\Fonts\\msyh.ttc 等）")


def split_lines(draw, text: str, font, max_width: int) -> list[str]:
    """按像素宽度换行"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_width:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def render_frame(background: np.ndarray, title: str, subtitle: str, font_path: str, cta_url: str = "") -> np.ndarray:
    """在渐变背景上绘制标题 + 当前句字幕，返回 RGB uint8 数组。
    cta_url：可选，底部终端风格显示的 CTA 链接。
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.fromarray(background)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(font_path, 52)
    body_font = ImageFont.truetype(font_path, 64)

    # 顶部小标题
    title_w = draw.textlength(title, font=title_font)
    draw.text(((W - title_w) / 2, 150), title, font=title_font, fill=(255, 255, 255))

    # 分隔线
    draw.rectangle([(W / 2 - 120, 250), (W / 2 + 120, 254)], fill=(94, 234, 212, 255))

    # 中间大字幕（自动换行，最多 4 行）
    lines = split_lines(draw, subtitle, body_font, W - 160)[:4]
    line_h = 96
    total_h = len(lines) * line_h
    y = (H - total_h) / 2
    for line in lines:
        lw = draw.textlength(line, font=body_font)
        draw.text(((W - lw) / 2, y), line, font=body_font, fill=(255, 255, 255))
        y += line_h

    # 底部提示 / CTA URL
    if cta_url:
        term_font = ImageFont.truetype(font_path, 28)
        prompt = "$ git clone "
        pw = draw.textlength(prompt, font=term_font)
        uw = draw.textlength(cta_url, font=term_font)
        total_w = pw + uw
        pad_x, pad_y = 28, 14
        term_x = (W - total_w) // 2 - pad_x
        term_y = H - 78 - pad_y
        draw.rounded_rectangle(
            [term_x, term_y, term_x + total_w + pad_x * 2, term_y + 28 + pad_y * 2],
            radius=10, fill=(0, 0, 0, 180),
        )
        draw.rectangle([term_x, term_y, term_x + 3, term_y + 28 + pad_y * 2], fill=(94, 234, 212, 200))
        draw.text((term_x + pad_x + 8, term_y + pad_y - 2), prompt, font=term_font, fill=(160, 175, 200))
        draw.text((term_x + pad_x + 8 + pw, term_y + pad_y - 2), cta_url, font=term_font, fill=(94, 234, 212))
    else:
        foot_font = ImageFont.truetype(font_path, 36)
        foot = "智序者 · 自进化开源智能体"
        fw = draw.textlength(foot, font=foot_font)
        draw.text(((W - fw) / 2, H - 200), foot, font=foot_font, fill=(160, 175, 200))

    return np.array(img)


def _load_web_shots(shots_dir: Path | None) -> dict[str, np.ndarray]:
    """加载网页/用户截图。

    默认加载 .runtime/shots/ 下的 hd_*.png 智序者页面（home/memory/genome/knowledge）。
    若传入其它目录（如用户截图目录），目录下所有 png 均按文件名（去后缀）作为 key 加载。
    返回 {页面名: RGB 数组}，没有可用截图时返回空 dict（此时退回纯渐变背景渲染）。
    """
    if shots_dir is None:
        shots_dir = ROOT / ".runtime" / "shots"
    shots: dict[str, np.ndarray] = {}
    if not shots_dir.exists():
        return shots
    # 默认目录：只认智序者已知页面名；用户截图目录：加载全部 png
    if shots_dir == ROOT / ".runtime" / "shots":
        allowed = {"home", "memory", "genome", "knowledge"}
    else:
        allowed = None  # 允许任意命名
    # hd_ 高清截图优先，普通截图兜底（同名只取高清）
    hd_files = sorted(shots_dir.glob("hd_*.png"))
    plain_files = sorted(shots_dir.glob("*.png"))
    for f in hd_files + plain_files:
        name = f.stem
        if name.startswith("hd_"):
            name = name[3:]
        if allowed is not None:
            if name not in allowed or name in shots:
                continue
        elif name in shots:
            continue
        try:
            from PIL import Image

            with Image.open(f) as im:
                shots[name] = np.array(im.convert("RGB"))
        except Exception as exc:
            logger.warning(f"  截图加载失败 {f.name}: {exc}")
    return shots


def _pick_web_shot(
    sentence: str, shots: dict[str, np.ndarray], page_hint: str | None, idx: int
) -> str | None:
    """按句子语义 + 页面 hint 挑选展示的页面名。

    规则：调用方可传 page_hint（优先使用）；否则按关键词匹配；
    都未命中时按 idx 轮换。无截图返回 None。
    """
    if not shots:
        return None
    if page_hint and page_hint in shots:
        return page_hint
    keywords = {
        "knowledge": ("知识", "学习", "云端", "模型", "电脑"),
        "genome": ("基因", "进化", "开源", "查看", "公开"),
        "memory": ("记忆", "记住", "记不住", "忘", "回顾", "经验", "私有", "灵魂"),
        "home": ("你好", "开始", "成长", "拥有", "欢迎"),
    }
    for name, words in keywords.items():
        if name not in shots:
            continue
        if any(w in sentence for w in words):
            return name
    return list(shots.keys())[idx % len(shots)]


def _draw_text_with_stroke(draw, xy, text, font, fill, stroke_fill, stroke_width=3):
    """在 PIL 上画带描边的文字（用于视频字幕，增强可读性）"""
    x, y = xy
    # 描边：8 方向偏移
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx == 0 and dy == 0:
                continue
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _blur_image(img, radius=30):
    """对 PIL 图像做高斯模糊（用于全屏背景虚化）"""
    from PIL import ImageFilter
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def render_web_frame(
    background: np.ndarray,
    web_img: np.ndarray,
    title: str,
    subtitle: str,
    font_path: str,
    page_label: str | None = None,
    progress: float = 0.0,
    cta_url: str = "",
) -> np.ndarray:
    """全屏网页实景帧：模糊背景铺底 + 清晰截图完整居中 + 描边字幕。

    progress: 0~1，片段内进度（用于 Ken Burns 缩放，本函数仅渲染单帧；
             动态缩放由外层 _make_kb_clip 通过 resize+position 实现）。
    cta_url：可选，底部固定显示的 CTA 链接（终端/代码风格绿色字），
             用于引导观众访问 GitHub 等地址。
    布局：
      - 底层：同图 cover 铺满 + 高斯模糊+压暗，填满所有空白提供氛围
      - 中层：网页截图 contain 等比缩放居中完整显示（所有细节可见，带圆角+投影）
      - 顶层：品牌角标 + 页面标签（贴截图右下角）+ 底部描边字幕（暗化区）+ CTA URL
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W, H = 1080, 1920
    web_pil = Image.fromarray(web_img).convert("RGB")

    # === 底层：模糊背景（同图 cover 铺满 + 高斯模糊，填满所有空白提供氛围）===
    # 横屏桌面截图（16:9 / 16:10）放到竖屏（9:16）会有大量留白，
    # 用同一截图的模糊版本铺满作为底，既填满全屏又不突兀
    scale_cover = max(W / web_pil.width, H / web_pil.height)
    nw_c, nh_c = int(web_pil.width * scale_cover), int(web_pil.height * scale_cover)
    blur_layer = web_pil.resize((nw_c, nh_c), Image.LANCZOS)
    left_c = (nw_c - W) // 2
    top_c = (nh_c - H) // 2
    blur_layer = blur_layer.crop((left_c, top_c, left_c + W, top_c + H))
    blur_layer = blur_layer.filter(ImageFilter.GaussianBlur(radius=40))
    # 压暗模糊背景（避免和清晰前景抢注意力）
    darken = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    canvas = Image.alpha_composite(blur_layer.convert("RGBA"), darken)

    # === 中层：清晰完整图（contain 模式，等比缩放居中，所有细节完整可见）===
    # 宽度占满画布（1080px），高度按比例自适应——横屏图宽满高自然，竖屏图高满宽自然
    # 垂直偏上放置（顶部留 110px 给品牌角标）
    scale_contain = W / web_pil.width  # 宽度优先：宽满屏，高按比例
    nw_s, nh_s = int(web_pil.width * scale_contain), int(web_pil.height * scale_contain)
    # 如果高度超出可用区域（截图本身很长），则改为高度限制
    max_h = H - 360  # 底部留 360px 给字幕+CTA
    if nh_s > max_h:
        scale_contain = max_h / web_pil.height
        nw_s, nh_s = int(web_pil.width * scale_contain), max_h
    sharp_layer = web_pil.resize((nw_s, nh_s), Image.LANCZOS)
    # 水平居中，垂直偏上
    paste_x = (W - nw_s) // 2
    paste_y = 110  # 顶部留出品牌角标空间
    # 给清晰图加投影（浮起感，与模糊背景分层）
    shadow = Image.new("RGBA", (nw_s + 40, nh_s + 40), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([20, 20, nw_s + 20, nh_s + 20], radius=12, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
    canvas.paste(shadow, (paste_x - 20, paste_y - 10), shadow)
    # 贴清晰图（圆角）
    sharp_rgba = sharp_layer.convert("RGBA")
    mask = Image.new("L", (nw_s, nh_s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, nw_s, nh_s], radius=12, fill=255)
    canvas.paste(sharp_rgba, (paste_x, paste_y), mask)

    draw = ImageDraw.Draw(canvas)

    # === 中层：字幕区纯色覆盖 ===
    # 清晰图下方的模糊背景会隐约透出网页文字，直接用纯色深色盖住字幕区，
    # 顶部 30px 渐变过渡避免硬边，保证字幕区是干净的深色背景
    sharp_bottom = paste_y + nh_s
    subtitle_bg_top = sharp_bottom - 30
    # 字幕区纯色底
    draw.rectangle([0, sharp_bottom, W, H], fill=(10, 12, 28))
    # 顶部渐变过渡（30px 半透明条，从透明到纯色，柔和衔接）
    for y in range(30):
        alpha = int(255 * ((y + 1) / 30))
        draw.line([(0, subtitle_bg_top + y), (W, subtitle_bg_top + y)], fill=(10, 12, 28, alpha))
    draw = ImageDraw.Draw(canvas)

    # === 顶层文字 ===
    title_font = ImageFont.truetype(font_path, 44)
    body_font = ImageFont.truetype(font_path, 64)
    foot_font = ImageFont.truetype(font_path, 32)

    # 顶部品牌标识（左上角 ZX logo + 名称，半透明背景不遮挡网页）
    brand = "Z · 智序者"
    bw_text = draw.textlength(brand, font=foot_font)
    draw.rounded_rectangle([30, 50, 30 + bw_text + 32, 92], radius=8, fill=(0, 0, 0, 100))
    draw.text((46, 57), brand, font=foot_font, fill=(94, 234, 212))

    # 页面标签（贴在清晰截图右下角，标识当前展示的页面）
    if page_label:
        label = page_label
        lw = draw.textlength(label, font=foot_font)
        label_right = paste_x + nw_s - 16
        label_bottom = sharp_bottom - 14
        label_x = label_right - lw - 24
        label_y = label_bottom - 36
        draw.rounded_rectangle(
            [label_x, label_y, label_right, label_y + 38],
            radius=10, fill=(0, 0, 0, 150),
        )
        draw.text((label_x + 12, label_y + 5), label, font=foot_font, fill=(220, 230, 245))

    # 底部字幕（居中，描边+半透明底衬增强可读性，位于截图下方暗化区域）
    lines = split_lines(draw, subtitle, body_font, W - 100)[:3]
    line_h = 94
    total_h = len(lines) * line_h
    # 字幕放在渐变暗化区域中间偏上
    subtitle_area_top = sharp_bottom + 80
    subtitle_area_bottom = H - (130 if cta_url else 200)
    y = subtitle_area_top + max(0, (subtitle_area_bottom - subtitle_area_top - total_h) // 2)
    # 字幕底衬（半透明圆角矩形）
    pad_x, pad_y = 44, 22
    text_max_w = max(draw.textlength(l, font=body_font) for l in lines) if lines else 0
    bg_rect_x = (W - text_max_w) // 2 - pad_x
    bg_rect_y = y - pad_y
    bg_rect_w = text_max_w + pad_x * 2
    bg_rect_h = total_h + pad_y * 2 - 8
    draw.rounded_rectangle(
        [bg_rect_x, bg_rect_y, bg_rect_x + bg_rect_w, bg_rect_y + bg_rect_h],
        radius=18, fill=(0, 0, 0, 160),
    )
    for line in lines:
        lw = draw.textlength(line, font=body_font)
        lx = (W - lw) / 2
        _draw_text_with_stroke(draw, (lx, y), line, body_font, fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=4)
        y += line_h

    # 底部标语 / CTA URL（终端风格代码字）
    if cta_url:
        # 终端命令条样式：深色圆角底 + $ 提示符 + 绿色 URL，智性代码感
        term_font = ImageFont.truetype(font_path, 28)
        prompt = "$ git clone "
        url_text = cta_url
        pw = draw.textlength(prompt, font=term_font)
        uw = draw.textlength(url_text, font=term_font)
        total_w = pw + uw
        pad_x, pad_y = 28, 14
        term_x = (W - total_w) // 2 - pad_x
        term_y = H - 78 - pad_y
        draw.rounded_rectangle(
            [term_x, term_y, term_x + total_w + pad_x * 2, term_y + 28 + pad_y * 2],
            radius=10, fill=(0, 0, 0, 180),
        )
        # 左侧细绿边（终端光标感）
        draw.rectangle([term_x, term_y, term_x + 3, term_y + 28 + pad_y * 2], fill=(94, 234, 212, 200))
        draw.text((term_x + pad_x + 8, term_y + pad_y - 2), prompt, font=term_font, fill=(160, 175, 200))
        draw.text((term_x + pad_x + 8 + pw, term_y + pad_y - 2), url_text, font=term_font, fill=(94, 234, 212))
    else:
        foot = "开源 · 自进化 · 私有记忆"
        fw = draw.textlength(foot, font=foot_font)
        draw.text(((W - fw) / 2, H - 80), foot, font=foot_font, fill=(200, 210, 230))

    return np.array(canvas.convert("RGB"))


def make_gradient_bg() -> np.ndarray:
    """生成深蓝渐变背景 (H, W, 3) uint8"""
    top = np.array([18, 20, 46], dtype=np.float64)     # #12142E
    bottom = np.array([15, 52, 96], dtype=np.float64)  # #0F3460
    t = np.linspace(0, 1, H, dtype=np.float64)[:, None, None]
    bg = (top[None, None, :] * (1 - t) + bottom[None, None, :] * t).astype(np.uint8)
    return np.repeat(bg, W, axis=1)


async def tts_edge(sentence: str, voice: str, out_mp3: Path, rate: str = "+0%") -> float:
    """edge-tts 合成单句配音（云端，国内直连可能被墙，支持代理）。"""
    import edge_tts

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("https_proxy")
    communicate = edge_tts.Communicate(sentence, voice=voice, rate=rate, proxy=proxy)
    await communicate.save(str(out_mp3))

    from moviepy import AudioFileClip

    with AudioFileClip(str(out_mp3)) as a:
        return a.duration


def tts_local(sentence: str, out_wav: Path, rate: int = 175) -> float:
    """本地 SAPI5 兜底合成（pyttsx3，零网络依赖，用 Windows 自带中文语音 Huihui）。"""
    import pyttsx3
    from moviepy import AudioFileClip

    engine = pyttsx3.init()
    # 优先选择中文语音
    for v in engine.getProperty("voices"):
        if "ZH-CN" in v.id.upper() or "Chinese" in v.name:
            engine.setProperty("voice", v.id)
            break
    engine.setProperty("rate", rate)
    engine.save_to_file(sentence, str(out_wav))
    engine.runAndWait()

    if not out_wav.exists():
        raise RuntimeError(f"本地 SAPI5 未生成音频: {out_wav}")

    with AudioFileClip(str(out_wav)) as a:
        return a.duration


# CosyVoice 本地服务（私有部署于 .runtime/cosyvoice，不在公共仓库）
COSYVOICE_PORT = 9880

# CosyVoice 内置参考音色（零样本克隆底音）
COSYVOICE_BUILTIN_PROMPTS = {
    "zero": "zero_shot_prompt.wav",
    "default": "zero_shot_prompt.wav",
    "cross": "cross_lingual_prompt.wav",
    "cross_lingual": "cross_lingual_prompt.wav",
}

# 内置音色档案：名称 → (参考音频, prompt_text=参考音频真实朗读内容)
# 注意：CosyVoice 规范要求 prompt_text 必须与参考音频内容一致，
# 否则 LLM 引导混乱，会导致合成内容与字幕错位（此前用「中文女声」描述是错误用法）。
COSYVOICE_VOICES = {
    "晓伊": {
        "wav": ROOT / ".runtime" / "cosyvoice" / "prompt_xiaoyi_bright.wav",
        "text": "你好呀！很高兴遇见你。我喜欢清晨的阳光，喜欢认真做事的人，也喜欢和你一起探索未知的每一天。让我们一起加油，成为更好的自己吧！",
    },
    "zero": {
        "wav": ROOT / ".runtime" / "cosyvoice" / "CosyVoice-main" / "asset" / "zero_shot_prompt.wav",
        "text": "希望你以后能够做的比我还好呦。",
    },
}


def _resolve_cosyvoice_voice(voice: str, prompt_wav: str | None) -> tuple[str | None, str]:
    """解析 voice 与 --prompt-wav 为 CosyVoice 需要的 (参考音频, prompt_text)。

    优先级：
    1. voice 形如 `cosyvoice:名字` 且命中内置档案（晓伊/zero）→ 用档案（wav+text 配对正确）
    2. 提供了 --prompt-wav 自定义参考音频 → 参考音频用它，冒号后内容作为 prompt_text
       （调用者须提供与音频一致的文字，否则内容会漂移）
    3. 其它 → 默认 zero 档案
    """
    name = (voice.split(":", 1)[1] if ":" in voice else "").strip()
    if name in COSYVOICE_VOICES:
        v = COSYVOICE_VOICES[name]
        return str(v["wav"]), v["text"]
    if prompt_wav:
        resolved = resolve_cosyvoice_prompt(prompt_wav)
        if resolved:
            return resolved, (name or COSYVOICE_VOICES["zero"]["text"])
    v = COSYVOICE_VOICES["zero"]
    return str(v["wav"]), v["text"]


def resolve_cosyvoice_prompt(prompt_wav: str) -> str | None:
    """把参考音频参数解析为服务端可用的绝对路径。

    内置名（zero/cross 等）→ .runtime/cosyvoice/CosyVoice-main/asset 下的示例音频；
    自定义路径 → 原样绝对化；空/无效 → None（服务端用默认音色）。
    """
    if not prompt_wav:
        return None
    if prompt_wav in COSYVOICE_BUILTIN_PROMPTS:
        return str(
            ROOT / ".runtime" / "cosyvoice" / "CosyVoice-main" / "asset"
            / COSYVOICE_BUILTIN_PROMPTS[prompt_wav]
        )
    p = Path(prompt_wav)
    if p.exists():
        return str(p.resolve())
    logger.warning(f"  CosyVoice 参考音频不存在（{prompt_wav}），回退默认音色")
    return None


def _ensure_cosyvoice_server() -> str:
    """确保 CosyVoice 本地 TTS 服务在运行，返回 base url。

    服务未启动时自动拉起：.runtime/cosyvoice/.venv311 的 Python 运行
    cosyvoice_server.py，轮询 /health 直到就绪（模型加载约 15 秒）。
    """
    import requests

    base = f"http://127.0.0.1:{COSYVOICE_PORT}"
    try:
        requests.get(base + "/health", timeout=2)
        return base
    except Exception:
        pass

    venv_py = ROOT / ".runtime" / "cosyvoice" / ".venv311" / "Scripts" / "python.exe"
    server_py = ROOT / ".runtime" / "cosyvoice" / "cosyvoice_server.py"
    if not venv_py.exists() or not server_py.exists():
        raise RuntimeError(
            "未找到 CosyVoice 本地部署（.runtime/cosyvoice），无法使用 cosyvoice 引擎。"
        )
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.Popen(
        [str(venv_py), str(server_py)],
        cwd=str(server_py.parent),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            requests.get(base + "/health", timeout=2)
            return base
        except Exception:
            time.sleep(3)
    raise RuntimeError("CosyVoice 服务启动超时")


def tts_cosyvoice(
    sentence: str, prompt_text: str, out_wav: Path, prompt_wav: str | None = None, speed: float = 1.05
) -> float:
    """本地 CosyVoice 零样本克隆合成单句配音（需 .runtime/cosyvoice 私有部署）。

    prompt_text 必须为参考音频的实际朗读内容（CosyVoice 规范，否则内容漂移）；
    prompt_wav 为克隆底音参考音频路径（空则服务端用默认音色）；
    speed 默认 1.05（略快于默认，更明亮有精神，适合宣传）。
    返回时长（秒），wav 写入 out_wav。
    """
    import requests

    base = _ensure_cosyvoice_server()
    payload = {"text": sentence, "prompt_text": prompt_text, "speed": speed}
    resolved = resolve_cosyvoice_prompt(prompt_wav)
    if resolved:
        payload["prompt_wav"] = resolved
    resp = requests.post(base + "/tts", json=payload, timeout=600)
    resp.raise_for_status()
    out_wav.write_bytes(resp.content)
    dur = float(resp.headers.get("X-Duration", 0))
    if dur <= 0:
        from moviepy import AudioFileClip

        with AudioFileClip(str(out_wav)) as a:
            dur = a.duration
    return dur


async def tts_one(
    sentence: str, voice: str, out_mp3: Path, rate: str = "+0%",
    prompt_wav: str | None = None, speed: float = 1.05,
) -> tuple[float, str, Path]:
    """合成单句配音：
    - voice 以 `cosyvoice:` 开头 → 本地 CosyVoice 克隆引擎（失败回退 SAPI5）
    - 其它 voice → edge-tts 优先，失败自动回退本地 SAPI5
    返回 (时长, 引擎名, 实际文件路径)

    speed：语速倍数，cosyvoice 透传；edge-tts 转换为 rate 百分比偏移；sapi5 调整 rate 参数。
    """
    # 非 cosyvoice 引擎的语速换算
    edge_rate = f"+{int((speed - 1.0) * 100):+d}%" if speed != 1.0 else "+0%"
    sapi_rate = int(175 * speed)
    if voice.startswith("cosyvoice:"):
        prompt_wav_path, prompt_text = _resolve_cosyvoice_voice(voice, prompt_wav)
        wav = out_mp3.with_suffix(".wav")
        try:
            dur = await asyncio.to_thread(
                tts_cosyvoice, sentence, prompt_text, wav, prompt_wav_path, speed
            )
            return dur, "cosyvoice", wav
        except Exception as exc:
            logger.warning(f"  cosyvoice 失败（{exc}），回退本地 SAPI5")
            dur = tts_local(sentence, wav, rate=sapi_rate)
            return dur, "sapi5", wav
    try:
        dur = await tts_edge(sentence, voice, out_mp3, rate=edge_rate)
        return dur, "edge-tts", out_mp3
    except Exception as exc:
        logger.warning(f"  edge-tts 失败（{exc}），回退本地 SAPI5")
        wav = out_mp3.with_suffix(".wav")
        dur = tts_local(sentence, wav, rate=sapi_rate)
        return dur, "sapi5", wav


async def _synthesize_async(
    sentences: list[str], voice: str, workdir: Path,
    prompt_wav: str | None = None, speed: float = 1.05,
) -> list[tuple[str, Path, float]]:
    """逐句合成配音，返回 [(句子, 音频文件路径, 时长)]

    speed：TTS 语速倍数（cosyvoice 透传；edge-tts 换算为 rate 百分比；sapi5 换算为 rate 整数）。
    """
    results = []
    engines = set()
    for i, sent in enumerate(sentences):
        mp3 = workdir / f"seg_{i:03d}.mp3"
        duration, engine, audio_path = await tts_one(sent, voice, mp3, prompt_wav=prompt_wav, speed=speed)
        engines.add(engine)
        results.append((sent, audio_path, duration))
        logger.info(f"  [TTS] 句 {i + 1}/{len(sentences)}: {duration:.2f}s（{engine}）「{sent[:20]}...」")
    return results, engines


def _make_kb_clip(frame_arr: np.ndarray, duration: float) -> "VideoClip":
    """用 Ken Burns 效果把静态帧包装成动画片段：缓慢放大 + 轻微上移。

    电影感的核心动效：每段画面 1.0 → 1.07 缓慢 zoom in，同时轻微上移，
    比纯静态图片更有"呼吸感"，是抖音/B站产品宣传视频常用手法。
    """
    from moviepy import VideoClip
    from PIL import Image

    # 预放大到 1.12x 做裁剪池
    BIG = 1.12
    big_img = Image.fromarray(frame_arr).resize(
        (int(W * BIG), int(H * BIG)), Image.LANCZOS
    )
    big_arr = np.array(big_img)
    bw, bh = big_img.size

    def make_frame(t):
        p = min(t / max(duration, 0.01), 1.0)
        scale = 1.0 + 0.07 * p  # 1.00 → 1.07 缓慢放大
        # 当前裁剪区域大小
        cw, ch = int(W / scale), int(H / scale)
        # 中心 + 轻微上移（开始居中，结束上移约 25px）
        cx, cy = bw // 2, bh // 2 - int(30 * p)
        left = max(0, cx - cw // 2)
        top = max(0, cy - ch // 2)
        left = min(left, bw - cw)
        top = min(top, bh - ch)
        crop = big_arr[top : top + ch, left : left + cw]
        # resize 回 1080x1920
        img = Image.fromarray(crop).resize((W, H), Image.LANCZOS)
        return np.array(img)

    return VideoClip(frame_function=make_frame, duration=duration).with_fps(FPS)


def make_douyin_video(
    text: str = "",
    out_path: str = "",
    voice: str = "zh-CN-XiaoxiaoNeural",
    prompt_wav: str | None = None,
    shots_dir: str | None = None,
    short: bool = False,
    cta_url: str = "",
) -> str:
    """制作抖音竖屏短视频，返回报告。供 Tool 调用。

    text：口播文案，**必填**——由调用方（Agent）根据用户意图动态构思生成，
         不内置默认文案。空文本直接报错。
    prompt_wav：CosyVoice 克隆底音参考音频（内置名 zero/cross 或自定义 wav 路径）。
    shots_dir：智序者网页截图目录（默认 .runtime/shots/，存在截图时画面用网页实景）。
    short：True 时使用稍快语速 + 电影感 Ken Burns 动效（约 20 秒快节奏）。
    cta_url：可选，底部终端风格显示的 CTA 链接（如 GitHub 地址），智性代码感。
    """
    if not text or not text.strip():
        raise ValueError(
            "未提供口播文案（text）。请先根据用户意图构思口播文案："
            "hook 开场（3 秒内抓住注意力）→ 卖点 → CTA 收尾，短句口语化，"
            "再传入 text 制作视频。"
        )
    from moviepy import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        VideoClip,
        concatenate_audioclips,
        concatenate_videoclips,
        vfx,
    )

    root = Path(__file__).resolve().parent.parent.parent
    videos_dir = root / "videos"
    videos_dir.mkdir(exist_ok=True)

    # short 模式：稍快语速 + 电影感 Ken Burns 动效（文案由调用方提供）
    tts_speed = 1.08 if short else 1.05

    if not out_path:
        tag = "short" if short else "douyin"
        out_path = str(videos_dir / f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
    out_path = str(Path(out_path).resolve())
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    workdir = videos_dir / "_tmp_video_maker"
    workdir.mkdir(exist_ok=True)

    lines = []
    lines.append("── 文案切句 ────────────────────────────")
    sentences = split_sentences(text)
    lines.append(f"共 {len(sentences)} 句" + ("（短模式）" if short else ""))

    # 1. TTS 逐句配音（edge-tts / 本地 CosyVoice / 兜底 SAPI5）
    lines.append("── 语音合成（edge-tts / CosyVoice / SAPI5）──")
    t0 = time.perf_counter()
    # 注意：short 模式下需要把 tts_speed 传给 tts_cosyvoice——这里通过临时覆盖全局 speed
    # 简单做法：直接调用 _synthesize_async，内部 tts_cosyvoice 默认 speed=1.05，
    # 我们在下面 monkey-patch 一下不太优雅，改为修改 _synthesize_async 接收 speed 参数
    segments, engines = asyncio.run(
        _synthesize_async(sentences, voice, workdir, prompt_wav, speed=tts_speed)
    )
    lines.append(f"配音完成，耗时 {time.perf_counter() - t0:.1f}s，引擎: {', '.join(sorted(engines))}")

    # 2. 渲染背景帧（电影感 Ken Burns 或简单静态）
    lines.append("── 画面渲染 + 视频合成（moviepy）──────")
    t0 = time.perf_counter()
    font_path = find_cjk_font()
    background = make_gradient_bg()
    title = "智序者 · 自进化开源智能体"
    web_shots = _load_web_shots(Path(shots_dir) if shots_dir else None)
    # 同时加载 assets/images/截图/ 下用户自己的截图作为额外素材
    user_shots_dir = ROOT / "assets" / "images" / "截图"
    if user_shots_dir.exists():
        extra = _load_web_shots(user_shots_dir)
        # 重命名为 user1/user2... 避免和 hd_ 截图冲突
        for i, (name, arr) in enumerate(extra.items()):
            web_shots[f"page{i+1}"] = arr
    if web_shots:
        lines.append(f"网页实景画面: {len(web_shots)} 张")
    else:
        lines.append("未找到网页截图，使用渐变背景")

    CROSSFADE = 0.18 if short else 0.0
    clips, audios = [], []
    for i, (sent, mp3, duration) in enumerate(segments):
        if web_shots:
            page = _pick_web_shot(sent, web_shots, None, i)
            frame = render_web_frame(background, web_shots[page], title, sent, font_path, page_label=page, cta_url=cta_url)
        else:
            frame = render_frame(background, title, sent, font_path, cta_url=cta_url)

        if short:
            # 电影感：Ken Burns 缓慢放大 + 轻微上移
            clip = _make_kb_clip(frame, duration + CROSSFADE)
            clip = clip.with_effects([vfx.CrossFadeIn(CROSSFADE), vfx.CrossFadeOut(CROSSFADE)])
        else:
            clip = ImageClip(frame).with_duration(duration).with_fps(FPS)
        audio = AudioFileClip(str(mp3))
        clip = clip.with_audio(audio)
        clips.append(clip)
        audios.append(audio)

    if short:
        # crossfade 衔接：padding 为负实现交叉淡入淡出
        final_video = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE)
    else:
        final_video = concatenate_videoclips(clips, method="chain")
    final_audio = concatenate_audioclips(audios)
    final_video = final_video.with_audio(final_audio)

    total_dur = sum(a.duration for a in audios)
    final_video.write_videofile(
        out_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )
    for c in clips:
        c.close()
    for a in audios:
        a.close()
    final_video.close()
    final_audio.close()
    lines.append(f"合成完成，耗时 {time.perf_counter() - t0:.1f}s")

    # 3. 清理临时目录
    for f in workdir.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        workdir.rmdir()
    except OSError:
        pass

    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    lines.append("── 输出 ────────────────────────────────")
    lines.append(f"视频: {out_path}")
    lines.append(f"时长: {total_dur:.1f}s  大小: {size_mb:.1f} MB  规格: {W}x{H} @ {FPS}fps")
    lines.append("✅ 制作完成，可在抖音创作者平台手动上传发布")

    logger.info("\n".join(lines))
    return "\n".join(lines)


def main() -> None:
    """独立运行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="智序者 · 抖音竖屏视频制作")
    parser.add_argument("--text", required=True, help="口播文案（必填，由调用方构思生成；不内置默认文案）")
    parser.add_argument("--voice", default="cosyvoice:晓伊", help="音色：cosyvoice:晓伊/zero（本地克隆，默认）；edge-tts 如 zh-CN-XiaoxiaoNeural")
    parser.add_argument("--out", default="", help="输出路径（缺省 videos/douyin_时间戳.mp4 或 short_时间戳.mp4）")
    parser.add_argument("--prompt-wav", default="", help="CosyVoice 克隆底音：内置 zero/cross，或自定义参考音频 wav 路径")
    parser.add_argument("--shots-dir", default="", help="智序者网页截图目录（默认 .runtime/shots/ + assets/images/截图/）")
    parser.add_argument("--short", action="store_true", help="短模式：稍快语速 + Ken Burns 电影感动效 + crossfade 过渡（文案由 --text 提供）")
    parser.add_argument("--cta-url", default="", help="可选，底部终端风格显示的 CTA 链接（如 GitHub 地址）")
    args = parser.parse_args()

    print(make_douyin_video(
        args.text, args.out, args.voice, args.prompt_wav or None,
        args.shots_dir or None, short=args.short, cta_url=args.cta_url or "",
    ))


if __name__ == "__main__":
    main()
