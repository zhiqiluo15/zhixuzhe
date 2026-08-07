"""网络请求工具 —— 获取网页内容

基于 requests 库，用于让 Agent 具备"上网"能力。
含 SSRF 防护：拒绝访问本地/内网/保留地址，防止被诱导探测内网。
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

# 常见浏览器 User-Agent，避免被拒绝
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _is_blocked_url(url: str) -> bool:
    """判断 URL 是否指向本地/内网/保留地址（用于 SSRF 防护）。"""
    host = urlparse(url).hostname
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 域名，尝试解析为 IP 再判断
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except Exception:
            return False
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast
    )


def web_fetch(url: str, timeout: int = 15, max_chars: int = 8000) -> str:
    """获取指定 URL 的网页内容（纯文本）。

    Args:
        url: 网页地址
        timeout: 请求超时秒数
        max_chars: 返回内容的最大字符数

    Returns:
        网页文本内容（截断后）
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # SSRF 防护：请求前检查目标地址
    if _is_blocked_url(url):
        return f"错误: 禁止访问本地/内网/保留地址 — {url}"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.Timeout:
        return f"请求超时（>{timeout}秒）: {url}"
    except requests.ConnectionError:
        return f"无法连接到: {url}"
    except requests.HTTPError as e:
        return f"HTTP 错误 {e.response.status_code}: {url}"
    except Exception as e:
        return f"请求失败: {e}"

    # 重定向后的最终地址也需校验（防重定向到内网）
    if _is_blocked_url(resp.url):
        return f"错误: 重定向到本地/内网/保留地址 — {resp.url}"

    # 简单提取纯文本（去除 HTML 标签）
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type or "text/plain" in content_type:
        text = _strip_html(resp.text)
    else:
        text = resp.text

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[已截断，原文 {len(text)} 字符]"

    return text


def _strip_html(html: str) -> str:
    """去除 HTML 标签，保留纯文本。"""
    import re
    # 移除 script/style
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # 移除标签
    html = re.sub(r"<[^>]+>", "", html)
    # 压缩空白
    html = re.sub(r"\s+", " ", html)
    # 解码常见 HTML 实体
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return html.strip()
