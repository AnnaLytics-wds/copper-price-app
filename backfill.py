# -*- coding: utf-8 -*-
"""一键回填历史电解铜价格到 Supabase。

用法：
    python backfill.py                 # 回填最近两年（首次初始化用）
    python backfill.py --days 45       # 只回填最近 45 天（每周自动更新用）
    python backfill.py 2024-08-10 2026-08-10
"""

import argparse
import os
import tomllib
from datetime import date, timedelta
from pathlib import Path

from copper_price import backfill_copper_prices


def load_supabase_client():
    """优先读取 .streamlit/secrets.toml，其次读取环境变量。"""
    from supabase import create_client

    secrets_file = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if secrets_file.exists():
        with secrets_file.open("rb") as f:
            data = tomllib.load(f)
        url = data.get("SUPABASE_URL", url)
        key = data.get("SUPABASE_KEY", key)

    if not url or not key:
        raise SystemExit(
            "未找到 Supabase 配置：请先在本地创建 .streamlit/secrets.toml，"
            "并填入 SUPABASE_URL 和 SUPABASE_KEY。"
        )
    return create_client(url, key)


def parse_args():
    parser = argparse.ArgumentParser(description="回填电解铜历史价格到 Supabase。")
    parser.add_argument(
        "dates",
        nargs="*",
        help="可选的 起始日期 结束日期，例如 2024-08-10 2026-08-10",
    )
    parser.add_argument(
        "--days",
        type=int,
        help="只回填最近 N 天，每周自动更新建议用 45",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.days:
        end = date.today()
        start = end - timedelta(days=args.days)
        start_date, end_date = start.isoformat(), end.isoformat()
    elif len(args.dates) == 2:
        start_date, end_date = args.dates[0], args.dates[1]
    else:
        end = date.today()
        start = end - timedelta(days=365 * 2)
        start_date, end_date = start.isoformat(), end.isoformat()

    client = load_supabase_client()
    print(f"开始回填 {start_date} ~ {end_date} 的电解铜价格...")
    count = backfill_copper_prices(start_date, end_date, supabase_client=client)
    print(f"回填完成：共写入/更新 {count} 条记录")


if __name__ == "__main__":
    main()
