# -*- coding: utf-8 -*-
"""自动获取国家统计局最新一期“电解铜（1#）”价格。"""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LIST_URL = "https://www.stats.gov.cn/sj/zxfb/"
KEYWORD = "流通领域重要生产资料市场价格"
TARGET_NAME = "电解铜（1#）"
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )
}


def fetch_html(url):
    """请求网页，并按照页面声明或常见编码解码 HTML。"""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    raw = resp.content

    # 统计局新版页面是 UTF-8，历史页面多为 gb2312/gbk。
    encodings = []
    meta = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw, re.I)
    if meta:
        encodings.append(meta.group(1).decode("ascii", "ignore").lower())
    if resp.encoding and resp.encoding.lower() not in ("iso-8859-1", "ascii"):
        encodings.append(resp.encoding.lower())

    # gb18030 是 gbk/gb2312 的超集，能覆盖历史页面的编码。
    encodings = [{"gbk": "gb18030", "gb2312": "gb18030"}.get(enc, enc) for enc in encodings]
    for enc in (*encodings, "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_list_date(text):
    """把 YYYY-MM-DD 之类日期字符串转成可比较的 (年, 月, 日)。"""
    m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", text or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def find_latest_article(list_html):
    """在目录页找到标题匹配且日期最新的一篇文章链接。"""
    soup = BeautifulSoup(list_html, "html.parser")
    candidates = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if KEYWORD not in title:
            continue

        href = urljoin(LIST_URL, a["href"].strip())
        if not href.endswith(".html") or href in seen:
            continue
        seen.add(href)

        # 目录项里通常有一个“YYYY-MM-DD”的发布日期。
        date = None
        li = a.find_parent("li")
        if li:
            date_text = li.get_text(" ", strip=True)
            date = parse_list_date(date_text)
        if date is None:
            date = parse_list_date(href)
        if date is None:
            m = re.search(r"t(\d{4})(\d{2})(\d{2})", href)
            if m:
                date = tuple(int(x) for x in m.groups())
        candidates.append((date, href, title))

    if not candidates:
        return None, None

    # 日期最大的排在前面；如果都没有日期，就取页面里先出现的（目录页按新到旧排列）。
    candidates.sort(key=lambda item: (item[0] is None, item[0]), reverse=True)
    _, href, title = candidates[0]
    return href, title


def extract_publish_date(article_html, fallback_title):
    """从文章页提取发布日期，找不到时退回标题里的日期或未知。"""
    m = re.search(
        r'<meta\s+name=["\']?PubDate["\']?\s+content=["\']?([^"\'>]+)',
        article_html,
        re.I,
    )
    if m:
        parts = parse_list_date(m.group(1))
        if parts:
            year, month, day = parts
            return f"{year}年{month}月{day}日"

    m = re.search(r"发布时间[：:\s]*([0-9年月日./\-]+)", article_html)
    if m:
        parts = parse_list_date(m.group(1))
        if parts:
            year, month, day = parts
            return f"{year}年{month}月{day}日"

    if fallback_title:
        parts = parse_list_date(fallback_title)
        if parts:
            year, month, day = parts
            return f"{year}年{month}月{day}日"
    return "未知日期"


def extract_copper_price(article_html):
    """在文章表格里找到“二、有色金属”下“电解铜（1#）”的本期价格。"""
    soup = BeautifulSoup(article_html, "html.parser")
    rows = soup.find_all("tr")

    # 先根据表头定位“本期价格（元）”是哪一列。
    price_index = None
    for tr in rows:
        texts = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        for i, text in enumerate(texts):
            if "本期价格" in text:
                price_index = i
                break
        if price_index is not None:
            break

    current_section = ""
    for tr in rows:
        cells = tr.find_all(["td", "th"])
        texts = [c.get_text(" ", strip=True) for c in cells]
        if not texts:
            continue

        joined = " ".join(texts)
        section = re.match(r"\s*[一二三四五六七八九十]、\s*(\S+)", joined)
        if section:
            current_section = section.group(1)
            continue

        if "有色金属" not in current_section:
            continue

        name = re.sub(r"\s+", "", texts[0])
        if name == TARGET_NAME or ("电解铜" in name and "1#" in name):
            if price_index is None:
                price_index = 2  # 历史页面的常见列位置
            if price_index >= len(texts):
                break
            m = re.search(r"-?\d+(?:\.\d+)?", texts[price_index].replace(",", ""))
            if m:
                return m.group(0)
            break
    return None


def to_iso_date(display_date):
    """把“2026年8月4日”转成 Supabase 需要的 YYYY-MM-DD 格式。"""
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", display_date or "")
    if not m:
        return None
    year, month, day = (int(x) for x in m.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def get_latest_copper_price():
    """抓取最新一期电解铜价格，供命令行、网页和以后的定时任务共同调用。

    返回示例：{"date": "2026-08-04", "display_date": "2026年8月4日",
              "price": "105694.4", "article_url": "https://..."}
    """
    list_html = fetch_html(LIST_URL)
    article_url, article_title = find_latest_article(list_html)
    if not article_url:
        raise RuntimeError(f"目录页中没有找到标题包含“{KEYWORD}”的文章")

    article_html = fetch_html(article_url)
    display_date = extract_publish_date(article_html, article_title)
    price = extract_copper_price(article_html)
    if price is None:
        raise RuntimeError(f"文章《{article_title}》中没有找到“{TARGET_NAME}”的价格")

    return {
        "date": to_iso_date(display_date),
        "display_date": display_date,
        "price": price,
        "article_url": article_url,
    }


def main():
    try:
        result = get_latest_copper_price()
    except requests.RequestException as exc:
        print(f"获取失败：无法访问统计局网站（{exc}）")
        return
    except RuntimeError as exc:
        print(f"获取失败：{exc}")
        return

    print(f"获取成功：{result['display_date']} 的电解铜价格为： {result['price']} 元/吨")


if __name__ == "__main__":
    main()
