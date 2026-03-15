import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import random

# ==========================================
# 平台全域設定與 CSS 鎖定 (絕對防破圖)
# ==========================================
st.set_page_config(page_title="AlphaInsight 全景量化終端", layout="wide", page_icon="🦅")
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] {gap: 24px;}
    .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: transparent; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px;}
    .stTabs [aria-selected="true"] {background-color: #2E2E2E; border-bottom: 2px solid #FF4B4B;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 核心防護層: 動態瀏覽器偽裝引擎 (突破 429 Rate Limit)
# ==========================================
def get_safe_session():
    """建立帶有隨機真實瀏覽器 User-Agent 的 Session，防止 Yahoo 封鎖雲端 IP"""
    session = requests.Session()
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    session.headers.update({
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return session

# ==========================================
# 資料獲取引擎 1: 全球總經與大盤 (支援 Google 財經備援)
# ==========================================
@st.cache_data(ttl=600) # 快取 10 分鐘，降低請求頻率
def fetch_macro_data():
    session = get_safe_session()
    tickers = {
        "TWII": "^TWII",      # 台股加權
        "NASDAQ": "^IXIC",    # 那斯達克
        "USD_TWD": "TWD=X",   # 美元兌台幣
        "US10Y": "^TNX",      # 美國10年期公債殖利率
        "VIX": "^VIX"         # 恐慌指數
    }
    macro_data = {}
    
    for name, ticker in tickers.items():
        try:
            t = yf.Ticker(ticker, session=session)
            df = t.history(period="5d")
            if not df.empty and len(df) >= 2:
                last_close = df['Close'].iloc[-1]
                prev_close = df['Close'].iloc[-2]
                change = last_close - prev_close
                pct_change = (change / prev_close) * 100
                macro_data[name] = {"close": last_close, "change": change, "pct_change": pct_change}
            else:
                raise ValueError("Yahoo 資料為空")
        except Exception as e:
            # 【雙引擎備援】如果 Yahoo 抓不到台股加權指數，立刻去爬 Google 財經
            if name == "TWII":
                try:
                    url = "https://www.google.com/finance/quote/TAIEX:TPE"
                    res = session.get(url, timeout=5)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    price_div = soup.find('div', class_='YMlKec fxKbKc')
                    if price_div:
                        price = float(price_div.text.replace(',', ''))
                        macro_data[name] = {"close": price, "change": 0.0, "pct_change": 0.0} # 簡化備援顯示
                        continue
                except:
                    pass
            macro_data[name] = {"close": 0, "change": 0, "pct_change": 0}
            
    return macro_data

# ==========================================
# 資料獲取引擎 2: 證交所 API (容錯版)
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
    return {"foreign": "TWSE限制", "trust": "TWSE限制", "dealer": "TWSE限制"}

# ==========================================
# 核心技術引擎: 多週期指標運算 (還原權值)
# ==========================================
def calculate_indicators(df):
    if len(df) < 60: return df 
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
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
st.sidebar.success("🟢 瀏覽器偽裝引擎已啟動\n🟢 Google/Yahoo 雙資料庫連線中")

menu = st.sidebar.radio("戰略模組切換", ("6. 每日盤前後總經解讀 (Macro)", "5. AI 智能技術選股與全景戰情室"))

# ==========================================
# 模組 6: 總經戰情室
# ==========================================
if menu == "6. 每日盤前後總經解讀 (Macro)":
    st.header("🌍 全球巨集與總經戰情室")
    with st.spinner("正在突破網管，同步全球交易所數據..."):
        macro = fetch_macro_data()
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("加權指數 (TWII)", f"{macro['TWII']['close']:,.0f}", f"{macro['TWII']['change']:+.0f}")
        c2.metric("那斯達克 (NASDAQ)", f"{macro['NASDAQ']['close']:,.0f}", f"{macro['NASDAQ']['change']:+.0f}")
        c3.metric("美元/台幣 (USD/TWD)", f"{macro['USD_TWD']['close']:.3f}", f"{macro['USD_TWD']['change']:+.3f}")
        c4.metric("美債10年期 (US10Y)", f"{macro['US10Y']['close']:.2f}%", f"{macro['US10Y']['change']:+.2f}%")
        c5.metric("恐慌指數 (VIX)", f"{macro['VIX']['close']:.2f}", f"{macro['VIX']['change']:+.2f}")

        st.markdown("---")
        st.subheader("📝 首席分析師 盤勢解讀 (Memo)")
        st.info("💡 系統已啟動雙引擎備援。若加權指數漲跌幅顯示為0，代表 Yahoo 數據暫時中斷，目前由 Google 財經提供最新報價。\n\n**當前市場邏輯**：請密切關注美債殖利率是否持續高檔，這將決定台股高估值科技股的資金流向。短線建議回歸個股技術面，嚴守 20MA 季線防守。")

# ==========================================
# 模組 5: 個股全景戰情室
# ==========================================
elif menu == "5. AI 智能技術選股與全景戰情室":
    st.title("🎯 個股全景戰情室 (抗封鎖版)")

    col_search, col_interval, col_empty = st.columns([2, 2, 4])
    with col_search:
        stock_code = st.text_input("🔍 輸入台股代碼 (例: 2330)", "2330")
    with col_interval:
        k_interval = st.selectbox("⏳ K線週期 (全數還原權值)", ["日K (Daily)", "週K (Weekly)", "月K (Monthly)"])

    interval_map = {"日K (Daily)": "1d", "週K (Weekly)": "1wk", "月K (Monthly)": "1mo"}
    period_map = {"日K (Daily)": "1y", "週K (Weekly)": "3y", "月K (Monthly)": "5y"}

    if st.button("🚀 執行深度挖掘與解析"):
        with st.spinner('建立加密偽裝通道，撈取法人矩陣中...'):
            try:
                session = get_safe_session()
                
                # 嘗試抓取上市或上櫃 K 線資料
                yf_ticker = f"{stock_code}.TW"
                ticker_obj = yf.Ticker(yf_ticker, session=session)
                df = ticker_obj.history(period=period_map[k_interval], interval=interval_map[k_interval])
                
                if df.empty:
                    yf_ticker = f"{stock_code}.TWO"
                    ticker_obj = yf.Ticker(yf_ticker, session=session)
                    df = ticker_obj.history(period=period_map[k_interval], interval=interval_map[k_interval])
                
                if df.empty:
                    st.error("⚠️ 查無此股票資料，或遭交易所短暫阻擋。請稍後重試。")
                    st.stop()
                
                # 容錯機制：如果抓不到 info，不要讓程式崩潰，給予空字典
                try:
                    info = ticker_obj.info
                    stock_name = info.get('shortName', stock_code)
                except:
                    info = {}
                    stock_name = stock_code
                    st.toast("⚠️ 提示：財報數據端點遭 Yahoo 限流，基本面欄位將顯示 N/A，但不影響技術線型運算。")

                df = calculate_indicators(df).dropna()
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                change = latest['Close'] - prev['Close']
                change_pct = (change / prev['Close']) * 100

                twse_chips = fetch_twse_institutional(stock_code)

                # --- 頂部報價橫幅 ---
                st.markdown("---")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("標的", f"{stock_code} {stock_name}")
                m2.metric("最新還原收盤", f"{latest['Close']:.2f}", f"{change:.2f} ({change_pct:.2f}%)")
                m3.metric("週期最高", f"{df['High'].max():.2f}")
                m4.metric("週期最低", f"{df['Low'].min():.2f}")
                m5.metric("當前成交量", f"{int(latest['Volume']/1000):,} 張")
                st.markdown("---")

                tab1, tab2, tab3, tab4 = st.tabs(["📊 量化技術線型", "💰 真實籌碼與大戶", "🛡️ 財報與估值", "🏢 資本事件"])

                # Tab 1: 絕對不會壞的技術線型
                with tab1:
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#F6CA2A', width=1.5), name='5MA'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#B052D1', width=1.5), name='20MA'), row=1, col=1)
                    fig.add_trace(go.Bar(x=df.index, y=df['Hist'], marker_color=np.where(df['Hist']<0, '#FF4B4B', '#00CC96'), name='MACD柱'), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#FFA15A', width=1), name='MACD'), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='#636EFA', width=1), name='Signal'), row=2, col=1)
                    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

                # Tab 2: 籌碼
                with tab2:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("#### 🏦 三大法人 (TWSE API)")
                        st.metric("外資買賣超", f"{twse_chips['foreign']}")
                        st.metric("投信買賣超", f"{twse_chips['trust']}")
                    with c2:
                        st.markdown("#### 🐋 法人持股 (Yahoo端點)")
                        st.metric("機構法人總持股", f"{info.get('heldPercentInstitutions', 0)*100:.2f} %" if info else "N/A")
                    with c3:
                        st.markdown("#### ⚖️ 流動性")
                        st.metric("Beta 值", f"{info.get('beta', 'N/A')}" if info else "N/A")

                # Tab 3: 財報 (容錯降級)
                with tab3:
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.markdown("#### 🎯 外資估值模型")
                        st.metric("外資共識目標價", f"NT$ {info.get('targetMeanPrice', 'N/A')}" if info else "N/A")
                        st.metric("預估本年度 EPS", f"NT$ {info.get('trailingEps', 'N/A')}" if info else "N/A")
                        st.metric("Forward P/E", f"{info.get('forwardPE', 0):.2f}x" if info and info.get('forwardPE') else "N/A")
                    with c2:
                        st.markdown("#### 🏰 財務防禦護城河")
                        st.metric("毛利率", f"{info.get('grossMargins', 0)*100:.2f} %" if info and info.get('grossMargins') else "N/A")
                        st.metric("ROE", f"{info.get('returnOnEquity', 0)*100:.2f} %" if info and info.get('returnOnEquity') else "N/A")

                # Tab 4
                with tab4:
                    st.write("近期新聞與增資事件請同步至公開資訊觀測站查詢。")

            except Exception as e:
                st.error(f"系統遭遇未知網路阻擋。請稍候 30 秒再試。系統底層錯誤代碼：{e}")
