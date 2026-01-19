import streamlit as st
import subprocess
import sys
import time
from datetime import datetime, timedelta
import pandas as pd # Needed for timezone conversion

# --- AUTO-INSTALLER ---
def install_and_import(package):
    try:
        __import__(package)
    except ImportError:
        st.warning(f"⚙️ Installing missing tool: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_and_import('feedparser')
install_and_import('textblob')
install_and_import('altair')

try:
    from textblob import TextBlob
except ImportError:
    import textblob
    from textblob import TextBlob

try:
    _ = TextBlob("test").sentiment 
except:
    st.warning("⚙️ Downloading sentiment vocabulary...")
    subprocess.check_call([sys.executable, "-m", "textblob.download_corpora"])

# --- IMPORTS ---
import feedparser
from textblob import TextBlob
import altair as alt
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- CONFIGURATION ---
API_KEY = 'AKB23LUHJC5LIK3ZTAQY2DCOM7'
SECRET_KEY = 'DL7aKA86uhnZCVyGCj8BNwaK12st3QBUeAxj4zxMSnGE'
SYMBOL = 'SPY' 
NEWS_URL = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"

# --- APP SETUP ---
st.set_page_config(page_title="Market Bot", layout="wide")
st.title(f"🇺🇸 {SYMBOL} Market Tracker")

# Connect to STOCK System
client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
data_container = st.empty()

def get_market_data():
    """Fetches stock data."""
    request_params = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Minute,
        start=datetime.now() - timedelta(days=5), 
        limit=390
    )
    bars = client.get_stock_bars(request_params)
    df = bars.df.reset_index()
    
    # --- TIMEZONE FIX ---
    # Convert UTC (Server Time) to America/New_York (Market Time)
    df['timestamp'] = df['timestamp'].dt.tz_convert('America/New_York')
    
    # Indicators
    df['sma_20'] = df['close'].rolling(window=20).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df.iloc[-60:]

def get_news_sentiment():
    try:
        feed = feedparser.parse(NEWS_URL)
        if not feed.entries: return 0, []
        
        score = 0
        articles = []
        for entry in feed.entries[:5]:
            blob = TextBlob(entry.title)
            p = blob.sentiment.polarity
            score += p
            icon = "🟢" if p > 0.1 else "🔴" if p < -0.1 else "⚪"
            articles.append((icon, entry.title, entry.link))
            
        return (score / len(articles)) if articles else 0, articles
    except:
        return 0, []

# --- MAIN LOOP ---
while True:
    try:
        # 1. Get Data
        df = get_market_data()
        
        if df.empty:
            st.warning("No data found. The market might be closed.")
            time.sleep(10)
            continue

        current_price = df.iloc[-1]['close']
        prev_price = df.iloc[-2]['close']
        price_change = current_price - prev_price
        current_rsi = df.iloc[-1]['rsi']
        current_sma = df.iloc[-1]['sma_20']
        
        # Get latest time in readable format
        latest_time = df.iloc[-1]['timestamp'].strftime('%H:%M %p')
        
        news_score, news_list = get_news_sentiment()
        
        # 2. Trends
        tech_trend = "BULLISH 🟢" if current_price > current_sma else "BEARISH 🔴"
        
        if news_score > 0.1: news_mood = "Positive 😃"
        elif news_score < -0.1: news_mood = "Negative 😨"
        else: news_mood = "Neutral 😐"

        # 3. Update App
        with data_container.container():
            # Status Banner
            if datetime.now().weekday() > 4: 
                st.info(f"🔔 Market is Closed (Weekend). Showing data from Friday at {latest_time} ET.")

            # Metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Price", f"${current_price:,.2f}", f"${price_change:.2f}")
            c2.metric("Tech Trend", tech_trend)
            c3.metric("RSI", f"{current_rsi:.1f}")
            c4.metric("News Mood", news_mood, f"{news_score:.2f}")

            # Charts & News
            col_chart, col_news = st.columns([2, 1])
            
            with col_chart:
                st.write("### 🕯️ Price Action")
                
                base = alt.Chart(df).encode(
                    x=alt.X('timestamp:T', axis=alt.Axis(title='New York Time', format='%I:%M %p')), # 12-hour format
                    tooltip=['timestamp', 'open', 'high', 'low', 'close', 'sma_20']
                )

                rule = base.mark_rule().encode(
                    y=alt.Y('high:Q', scale=alt.Scale(zero=False)),
                    y2=alt.Y2('low')
                )
                
                bars = base.mark_bar().encode(
                    y=alt.Y('open:Q', scale=alt.Scale(zero=False)),
                    y2=alt.Y2('close'),
                    color=alt.condition("datum.close >= datum.open", alt.value("#00C805"), alt.value("#FF333A"))
                )
                
                sma = base.mark_line(color='blue').encode(
                    y=alt.Y('sma_20:Q', scale=alt.Scale(zero=False))
                )
                
                chart = (rule + bars + sma).properties(height=400)
                st.altair_chart(chart, use_container_width=True)

                st.write("### 📊 Momentum")
                rsi_chart = alt.Chart(df).mark_line(color='#9C27B0').encode(
                    x=alt.X('timestamp:T', axis=alt.Axis(title=None)),
                    y=alt.Y('rsi', scale=alt.Scale(domain=[0, 100]))
                ).properties(height=150)
                st.altair_chart(rsi_chart, use_container_width=True)

            with col_news:
                st.write("### 📰 Headlines")
                for icon, title, link in news_list:
                    st.markdown(f"{icon} [{title}]({link})")
            
            st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

        time.sleep(60)

    except Exception as e:
        st.error(f"Waiting for market data... ({e})")
        time.sleep(10)    
      
