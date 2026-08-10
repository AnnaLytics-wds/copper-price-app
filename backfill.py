# -*- coding: utf-8 -*-
"""一键回填历史电解铜价格到 Supabase。

用法：
    python backfill.py
    python backfill.py 2024-08-10 2026-08-10
"""

import os
import sys
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


def main():
    args = sys.argv[1:]
    if len(args) >= 2:
        start_date, end_date = args[0], args[1]
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
