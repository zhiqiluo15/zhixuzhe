#!/usr/bin/env python3
"""智序者 · 抖音竖屏视频制作工具

把一段口播文案制作成抖音竖屏短视频：
  文案切句 → 逐句配音 → PIL 生成渐变字幕背景 → moviepy 合成 MP4

配音引擎（voice 参数）：
  zh-CN-* 等 edge-tts 音色  → edge-tts 优先，失败回退 Windows 本地 SAPI5
  cosyvoice:中文女声         → 本地 CosyVoice 零样本克隆（需 .runtime/cosyvoice 私有部署，
                               自动拉起本地服务，失败回退 SAPI5）

用法：
  python engine/tools/video_maker.py                      # 内置智序者宣传文案
  python engine/tools/video_maker.py --text "自定义文案"
  python engine/tools/video_maker.py --voice zh-CN-YunxiNeural --out videos/out.mp4
  python engine/tools/video_maker.py --voice cosyvoice:中文女声 --out videos/out.mp4
  python engine/tools/video_maker.py --voice cosyvoice:中文女声 --prompt-wav cross --out videos/out.mp4

API：
  make_douyin_video(text, out_path, voice) -> str        # 返回报告，供 Tool 调用

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

# 默认内置文案：宣传智序者（约 45 秒口播）
DEFAULT_TEXT = (
    "你知道为什么 AI 越来越聪明，却总记不住你是谁吗？"
    "我是智序者，一个会自己成长的开源智能体。"
    "每天，我把每一次对话、每一次任务、每一次踩坑，都写进自己的记忆。"
    "我还会在深夜回顾这些经验，让自己变得更好。"
    "这就像人类一样，智慧，来自于秩序。"
    "我的基因是开源的，任何人都能查看我的进化记录；"
    "但我的灵魂是私有的，只有你能看到我的记忆。"
    "我用现在的云端模型积累经验，等本地模型成熟那天，"
    "这些经验会全部带回你的电脑。"
    "现在，你也可以拥有一个会成长的 AI。开源地址，就在简介里。"
)


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


def render_frame(background: np.ndarray, title: str, subtitle: str, font_path: str) -> np.ndarray:
    """在渐变背景上绘制标题 + 当前句字幕，返回 RGB uint8 数组"""
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

    # 底部提示
    foot_font = ImageFont.truetype(font_path, 36)
    foot = "智序者 · 自进化开源智能体"
    fw = draw.textlength(foot, font=foot_font)
    draw.text(((W - fw) / 2, H - 200), foot, font=foot_font, fill=(160, 175, 200))

    return np.array(img)


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


def tts_cosyvoice(sentence: str, prompt_text: str, out_wav: Path, prompt_wav: str | None = None) -> float:
    """本地 CosyVoice 零样本克隆合成单句配音（需 .runtime/cosyvoice 私有部署）。

    prompt_text 为音色描述（如「中文女声」）；prompt_wav 为克隆底音参考音频
    （内置名 zero/cross 或自定义 wav 路径，空则服务端用默认音色）。
    返回时长（秒），wav 写入 out_wav。
    """
    import requests

    base = _ensure_cosyvoice_server()
    payload = {"text": sentence, "prompt_text": prompt_text}
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
    sentence: str, voice: str, out_mp3: Path, rate: str = "+0%", prompt_wav: str | None = None
) -> tuple[float, str, Path]:
    """合成单句配音：
    - voice 以 `cosyvoice:` 开头 → 本地 CosyVoice 克隆引擎（失败回退 SAPI5）
    - 其它 voice → edge-tts 优先，失败自动回退本地 SAPI5
    返回 (时长, 引擎名, 实际文件路径)
    """
    if voice.startswith("cosyvoice:"):
        prompt_text = voice.split(":", 1)[1].strip() or "中文女声"
        wav = out_mp3.with_suffix(".wav")
        try:
            dur = await asyncio.to_thread(tts_cosyvoice, sentence, prompt_text, wav, prompt_wav)
            return dur, "cosyvoice", wav
        except Exception as exc:
            logger.warning(f"  cosyvoice 失败（{exc}），回退本地 SAPI5")
            dur = tts_local(sentence, wav)
            return dur, "sapi5", wav
    try:
        dur = await tts_edge(sentence, voice, out_mp3, rate)
        return dur, "edge-tts", out_mp3
    except Exception as exc:
        logger.warning(f"  edge-tts 失败（{exc}），回退本地 SAPI5")
        wav = out_mp3.with_suffix(".wav")
        dur = tts_local(sentence, wav)
        return dur, "sapi5", wav


async def _synthesize_async(
    sentences: list[str], voice: str, workdir: Path, prompt_wav: str | None = None
) -> list[tuple[str, Path, float]]:
    """逐句合成配音，返回 [(句子, 音频文件路径, 时长)]"""
    results = []
    engines = set()
    for i, sent in enumerate(sentences):
        mp3 = workdir / f"seg_{i:03d}.mp3"
        duration, engine, audio_path = await tts_one(sent, voice, mp3, prompt_wav=prompt_wav)
        engines.add(engine)
        results.append((sent, audio_path, duration))
        logger.info(f"  [TTS] 句 {i + 1}/{len(sentences)}: {duration:.2f}s（{engine}）「{sent[:20]}...」")
    return results, engines


def make_douyin_video(
    text: str = DEFAULT_TEXT,
    out_path: str = "",
    voice: str = "zh-CN-XiaoxiaoNeural",
    prompt_wav: str | None = None,
) -> str:
    """制作抖音竖屏短视频，返回报告。供 Tool 调用。

    prompt_wav：CosyVoice 克隆底音参考音频（内置名 zero/cross 或自定义 wav 路径）。
    """
    from moviepy import AudioFileClip, ImageClip, concatenate_audioclips, concatenate_videoclips

    root = Path(__file__).resolve().parent.parent.parent
    videos_dir = root / "videos"
    videos_dir.mkdir(exist_ok=True)

    if not out_path:
        out_path = str(videos_dir / f"douyin_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
    out_path = str(Path(out_path).resolve())
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    workdir = videos_dir / "_tmp_video_maker"
    workdir.mkdir(exist_ok=True)

    lines = []
    lines.append("── 文案切句 ────────────────────────────")
    sentences = split_sentences(text)
    lines.append(f"共 {len(sentences)} 句")

    # 1. TTS 逐句配音（edge-tts / 本地 CosyVoice / 兜底 SAPI5）
    lines.append("── 语音合成（edge-tts / CosyVoice / SAPI5）──")
    t0 = time.perf_counter()
    segments, engines = asyncio.run(_synthesize_async(sentences, voice, workdir, prompt_wav))
    lines.append(f"配音完成，耗时 {time.perf_counter() - t0:.1f}s，引擎: {', '.join(sorted(engines))}")

    # 2. 生成渐变背景 + 逐句字幕帧
    lines.append("── 字幕渲染 + 视频合成（moviepy）──────")
    t0 = time.perf_counter()
    font_path = find_cjk_font()
    background = make_gradient_bg()
    title = "智序者 · 自进化开源智能体"

    clips, audios = [], []
    for sent, mp3, duration in segments:
        frame = render_frame(background, title, sent, font_path)
        clip = ImageClip(frame).with_duration(duration).with_fps(FPS)
        audio = AudioFileClip(str(mp3))
        clip = clip.with_audio(audio)
        clips.append(clip)
        audios.append(audio)

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
    parser.add_argument("--text", default=DEFAULT_TEXT, help="口播文案（缺省用内置智序者宣传文案）")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="音色：edge-tts 如 zh-CN-YunxiNeural；本地克隆用 cosyvoice:中文女声")
    parser.add_argument("--out", default="", help="输出路径（缺省 videos/douyin_时间戳.mp4）")
    parser.add_argument("--prompt-wav", default="", help="CosyVoice 克隆底音：内置 zero/cross，或自定义参考音频 wav 路径")
    args = parser.parse_args()

    print(make_douyin_video(args.text, args.out, args.voice, args.prompt_wav or None))


if __name__ == "__main__":
    main()
