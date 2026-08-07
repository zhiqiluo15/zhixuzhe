"""网络搜索工具 —— Bing HTML 搜索（零 API Key，零额外依赖）

使用 Bing 的 HTML 搜索接口，返回标题+URL+摘要的结构化结果列表。
不依赖第三方搜索库，仅用 requests + 正则解析，保持项目零额外依赖原则。
搜索域名固定为 bing.com，结果 URL 不做二次请求。
"""

import re
import html as html_module

import requests

_SEARCH_URL = "https://www.bing.com/search"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def web_search(query: str, max_results: int = 8, timeout: int = 15) -> str:
    """搜索网页，返回结果列表（标题 + URL + 摘要）。

    Args:
        query: 搜索关键词
        max_results: 最多返回几条结果（默认 8，上限 20）
        timeout: 请求超时秒数

    Returns:
        格式化的搜索结果文本，每行一个结果
    """
    if not query.strip():
        return "错误: 搜索关键词不能为空"

    max_results = max(1, min(max_results, 20))

    try:
        resp = requests.get(
            _SEARCH_URL,
            headers=_HEADERS,
            params={"q": query, "setlang": "zh-CN"},
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.Timeout:
        return f"搜索超时（>{timeout}秒）"
    except requests.ConnectionError:
        return "搜索失败：无法连接到搜索引擎（检查网络）"
    except requests.HTTPError as e:
        return f"搜索失败: HTTP {e.response.status_code}"
    except Exception as e:
        return f"搜索失败: {e}"

    results = _parse_results(resp.text)

    if not results:
        return f'未找到与 "{query}" 相关的结果'

    lines = [f'搜索: "{query}"（找到 {len(results)} 条结果）\n']
    for i, r in enumerate(results[:max_results], 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    {r['url']}")
        if r["snippet"]:
            lines.append(f"    {r['snippet']}")
        lines.append("")

    return "\n".join(lines)


def _parse_results(html: str) -> list[dict]:
    """从 Bing HTML 响应中解析搜索结果。

    Bing 结果结构：<li class="b_algo"> 包含一个结果
      - 标题+链接: <h2><a href="URL">标题</a></h2>
      - 摘要: <p>...</p> 或 <div class="b_caption"><p>...</p></div>
    """
    results = []

    # 按 <li class="b_algo"> 分割
    blocks = re.split(r'<li\s+class="b_algo"', html)

    for block in blocks[1:]:
        # 提取标题和链接
        title_match = re.search(
            r'<h2[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            block, re.DOTALL,
        )
        if not title_match:
            continue

        url = title_match.group(1)
        title = _strip_html(title_match.group(2))

        # 过滤非 http(s) 链接（Bing 有时混入内部链接）
        if not url.startswith(("http://", "https://")):
            continue

        # 提取摘要：优先找 b_caption 内的 p，否则取第一个 p
        snippet = ""
        caption_match = re.search(
            r'class="b_caption"[^>]*>(.*?)</div>',
            block, re.DOTALL,
        )
        if caption_match:
            p_match = re.search(r"<p[^>]*>(.*?)</p>", caption_match.group(1), re.DOTALL)
            if p_match:
                snippet = _strip_html(p_match.group(1))
        if not snippet:
            p_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
            if p_match:
                snippet = _strip_html(p_match.group(1))

        results.append({
            "title": title.strip(),
            "url": url,
            "snippet": snippet.strip()[:300],
        })

    return results


def _strip_html(text: str) -> str:
    """移除 HTML 标签，解码所有实体，返回纯文本。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    # html.unescape 处理所有实体（&amp; &nbsp; &#183; &ensp; 等）
    text = html_module.unescape(text)
    return text.strip()
