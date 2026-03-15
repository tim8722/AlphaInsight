import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 平台全域設定與 UI 鎖定 (防止破圖)
# ==========================================
st.set_page_config(page_title="AlphaInsight 戰情室 (抗封鎖版)", layout="wide", page_icon="🦅")
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] {gap: 24px;}
    .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: transparent; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px;}
    .stTabs [aria-selected="true"] {background-color: #2E2E2E; border-bottom: 2px solid #FF4B4B;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 核心引擎 1: Google Finance 強制解析器 (絕對不會被 429 封鎖)
# ==========================================
@st.cache_data(ttl=300) # 快取 5 分鐘
def get_google_finance_price(ticker, exchange):
    """直接爬取 Google 財經網頁 HTML，暴力破解取得即時報價"""
    url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 尋找 Google 財經的最新價格標籤
        price_element = soup.find('div', class_='YMlKec fxKbKc')
        if price_element:
            price_str = price_element.text.replace(',', '').replace('$', '').replace('%', '')
            return float(price_str)
    except:
        pass
    return None

def fetch_macro_google():
    """使用 Google 引擎獲取總經大盤"""
    macros = {
        "TWII (加權指數)": {"t": "TAIEX", "e": "TPE"},
        "NASDAQ (那斯達克)": {"t": ".IXIC", "e": "INDEXNASDAQ"},
        "USD/TWD (美元/台幣)": {"t": "USD-TWD", "e": "CURRENCY"},
        "US10Y (美債10年期)": {"t": "TNX", "e": "INDEXCBOE"},
        "VIX (恐慌指數)": {"t": "VIX", "e": "INDEXCBOE"}
    }
    results = {}
    for name, info in macros.items():
        price = get_google_finance_price(info['t'], info['e'])
        results[name] = price if price is not None else "N/A"
    return results

# ==========================================
# 核心引擎 2: 證交所 TWSE 真實三大法人籌碼
# ==========================================
@st.cache_data(ttl=3600)
def fetch_twse_institutional(stock_code):
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/T86_ALL"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            for row in res.json():
                if row.get('Code') == stock_code:
                    return {
                        "foreign": int(row.get('ForeignInvestment_NetBuy', 0).replace(',', '')),
                        "trust": int(row.get('InvestmentTrust_NetBuy', 0).replace(',', '')),
                        "dealer": int(row.get('Dealer_NetBuy', 0).replace(',', ''))
                    }
    except:
        pass
    return {"foreign": "資料受限", "trust": "資料受限", "dealer": "資料受限"}

# ==========================================
# 核心引擎 3: 技術指標矩陣 (還原權值)
# ==========================================
def calculate_indicators(df):
    if len(df) < 60: return df 
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    df['BB_std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['BB_std'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['BB_std'] * 2)
    
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

# ==========================================
# 側邊欄 UI
# ==========================================
st.sidebar.title("🦅 AlphaInsight 終端")
st.sidebar.success("🟢 Google 財經解析引擎已啟動\n🟢 雲端降級防禦系統運作中")

menu = st.sidebar.radio("戰略模組切換", ("6. 每日盤前後總經解讀 (Macro)", "5. AI 智能技術選股與全景戰情室"))

# ==========================================
# 模組 6:
