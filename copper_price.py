# -*- coding: utf-8 -*-
"""自动获取国家统计局最新一期“电解铜（1#）”价格。"""

import re
import time
from datetime import date, datetime
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
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            raw = resp.content
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_exc

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


def _to_date(value):
    """把 "YYYY-MM-DD" 字符串或 date 对象统一成 date。"""
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def fetch_copper_price_history(start_date, end_date, verbose=False):
    """抓取 start_date 到 end_date（含）之间每一期的电解铜价格记录。

    返回按日期升序排列的记录列表，每项包含 date、display_date、price。
    """
    start = _to_date(start_date)
    end = _to_date(end_date)
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")

    # 第一步：翻目录页，收集日期范围内的文章链接。
    candidates = []
    seen_urls = set()
    page = 0
    while page <= 60:
        page_url = LIST_URL if page == 0 else f"{LIST_URL}index_{page}.html"
        page_html = fetch_html(page_url)
        soup = BeautifulSoup(page_html, "html.parser")

        items = []
        for li in soup.select(".list-content ul li"):
            a = li.find("a")
            span = li.find("span")
            if not a:
                continue
            parsed = parse_list_date(span.get_text(strip=True) if span else "")
            if not parsed:
                continue
            items.append(
                (
                    date(*parsed),
                    a.get_text(" ", strip=True),
                    urljoin(LIST_URL, a["href"].strip()),
                )
            )

        if not items:
            break

        # 目录页按日期倒序，本页最后一条都早于 start 时，后面不用再翻。
        for item_date, title, href in items:
            if item_date < start or item_date > end:
                continue
            if KEYWORD not in title or href in seen_urls:
                continue
            seen_urls.add(href)
            candidates.append((item_date, title, href))

        if items[-1][0] < start:
            break
        page += 1

    # 第二步：逐篇抓文章，提取价格和发布日期，按日期去重。
    records = []
    seen_dates = set()
    total = len(candidates)
    for index, (item_date, title, href) in enumerate(candidates, 1):
        if verbose:
            print(f"正在抓取 {index}/{total}：{title}", flush=True)
        article_html = fetch_html(href)

        display_date = extract_publish_date(article_html, title)
        date_iso = to_iso_date(display_date) or item_date.isoformat()
        price = extract_copper_price(article_html)
        if not date_iso or date_iso in seen_dates or price is None:
            if verbose:
                print(f"跳过 {title}：未提取到有效价格或日期", flush=True)
            continue

        seen_dates.add(date_iso)
        records.append(
            {"date": date_iso, "display_date": display_date, "price": price}
        )

    records.sort(key=lambda item: item["date"])
    return records


def _supabase_client_from_env():
    """从环境变量读取 Supabase 配置并创建客户端。"""
    import os

    try:
        from supabase import create_client
    except ImportError:
        raise RuntimeError("缺少 supabase 库，请先执行 pip install supabase")

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("未找到 SUPABASE_URL / SUPABASE_KEY 环境变量")
    return create_client(url, key)


def backfill_copper_prices(start_date, end_date, supabase_client=None, verbose=True):
    """抓取历史电解铜价格并批量写入 Supabase（按 date 去重/覆盖）。

    返回写入（或更新）的记录条数。
    """
    records = fetch_copper_price_history(start_date, end_date, verbose=verbose)
    if not records:
        if verbose:
            print("没有找到该日期范围内的电解铜价格记录。", flush=True)
        return 0

    if supabase_client is None:
        supabase_client = _supabase_client_from_env()

    rows = [{"date": item["date"], "price": float(item["price"])} for item in records]
    for i in range(0, len(rows), 50):
        supabase_client.table("copper_prices").upsert(
            rows[i : i + 50], on_conflict="date"
        ).execute()
    return len(records)


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
