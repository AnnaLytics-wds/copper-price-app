# -*- coding: utf-8 -*-
"""电解铜价格看板：Streamlit 网页 + Supabase 云端存储。"""

import pandas as pd
import streamlit as st

from copper_price import get_latest_copper_price


st.set_page_config(page_title="电解铜价格看板", layout="centered")

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error(
        "未配置 Supabase 密钥：请在 Streamlit Cloud 的 Settings → Secrets 中"
        "设置 SUPABASE_URL 和 SUPABASE_KEY。"
    )
    st.stop()


@st.cache_resource
def get_supabase_client():
    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_KEY)


def load_history(client):
    """从 Supabase 读取全部价格记录，返回按日期排序的 DataFrame。"""
    try:
        response = client.table("copper_prices").select("date, price").execute()
    except Exception as exc:
        st.error(f"读取 Supabase 数据失败：{exc}")
        return pd.DataFrame(columns=["date", "price"])

    if not response.data:
        return pd.DataFrame(columns=["date", "price"])

    df = pd.DataFrame(response.data)
    df["date"] = pd.to_datetime(df["date"])
    df["price"] = pd.to_numeric(df["price"])
    return df.sort_values("date").reset_index(drop=True)


client = get_supabase_client()
history = load_history(client)

latest_text = "最新铜价：暂无数据"
latest_date = None
if not history.empty:
    latest = history.iloc[-1]
    latest_text = f"最新铜价：{latest['price']} 元/吨"
    latest_date = latest["date"].date()

st.markdown(
    f'<p style="font-size:44px; font-weight:800; text-align:center; '
    f'margin:16px 0 4px;">{latest_text}</p>',
    unsafe_allow_html=True,
)
if latest_date:
    st.caption(f"最新数据日期：{latest_date}")

if "update_message" not in st.session_state:
    st.session_state.update_message = None

if st.button("🔄 更新最新价格", type="primary", use_container_width=True):
    with st.spinner("正在从国家统计局抓取最新价格..."):
        try:
            result = get_latest_copper_price()
        except Exception as exc:
            st.session_state.update_message = ("error", f"抓取失败：{exc}")
        else:
            if not result["date"]:
                st.session_state.update_message = (
                    "error",
                    f"抓取成功，但无法识别发布日期（{result['display_date']}），未写入数据库。",
                )
            else:
                try:
                    get_supabase_client().table("copper_prices").upsert(
                        {"date": result["date"], "price": float(result["price"])},
                        on_conflict="date",
                    ).execute()
                    st.session_state.update_message = (
                        "success",
                        f"已更新：{result['display_date']} 电解铜价格为 {result['price']} 元/吨",
                    )
                except Exception as exc:
                    st.session_state.update_message = ("error", f"写入 Supabase 失败：{exc}")
    st.rerun()

if st.session_state.update_message:
    kind, text = st.session_state.update_message
    if kind == "success":
        st.success(text)
    else:
        st.error(text)
    st.session_state.update_message = None

st.subheader("历史价格趋势")
if history.empty:
    st.info("暂无历史数据，点击上方按钮抓取第一条价格。")
else:
    st.line_chart(history.set_index("date")["price"])
    st.caption(f"共 {len(history)} 条价格记录")
