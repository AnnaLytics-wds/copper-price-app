# -*- coding: utf-8 -*-
"""每周更新后向微信（Server酱）推送最新电解铜价格。

由 GitHub Actions 调用：
    python notify.py

需要的环境变量：
    SUPABASE_URL / SUPABASE_KEY   读取最新价格
    SERVERCHAN_SENDKEYS           逗号分隔的多个 SendKey（一个微信用户一个）
"""

import os
import tomllib
from pathlib import Path

import requests


def load_supabase_client():
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
        raise SystemExit("未找到 Supabase 配置：请设置 SUPABASE_URL 和 SUPABASE_KEY")
    return create_client(url, key)


def get_latest_price(client):
    """从 Supabase 读取最新一条铜价记录。"""
    resp = (
        client.table("copper_prices")
        .select("date, price")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise SystemExit("Supabase 中还没有铜价数据")
    return resp.data[0]["date"], resp.data[0]["price"]


def send_wechat(keys, title, desp):
    """向每个 Server酱 SendKey 推送一条消息。"""
    failures = []
    for key in keys:
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": desp},
                timeout=20,
            )
            result = resp.json()
            if result.get("code") != 0:
                failures.append(f"{key[:8]}...：{result.get('message', '未知错误')}")
            else:
                print(f"微信推送成功：{key[:8]}...")
        except Exception as exc:
            failures.append(f"{key[:8]}...：{exc}")

    for message in failures:
        print(f"推送失败：{message}")
    if failures and len(failures) == len(keys):
        raise SystemExit("所有微信推送都失败了")


def main():
    keys = [
        key.strip()
        for key in os.environ.get("SERVERCHAN_SENDKEYS", "").split(",")
        if key.strip()
    ]
    if not keys:
        raise SystemExit("未配置 SERVERCHAN_SENDKEYS（逗号分隔的多个 SendKey）")

    client = load_supabase_client()
    price_date, price = get_latest_price(client)

    title = "电解铜价格周报"
    desp = (
        "### 电解铜最新价格\n\n"
        f"- 数据日期：{price_date}\n"
        f"- 价格：{price} 元/吨"
    )
    send_wechat(keys, title, desp)


if __name__ == "__main__":
    main()
