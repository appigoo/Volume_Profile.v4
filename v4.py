import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 页面配置
st.set_page_config(layout="wide", page_title="Intraday Volume Profile")

st.title("⚡ 多周期筹码分布分析 (支持 1m - 1h)")

# 侧边栏配置
with st.sidebar:
    st.header("行情配置")
    symbol = st.text_input("股票代码", value="AAPL")
    
    # 周期与对应的时间跨度限制
    interval_map = {
        "1m": "1d",    # 1分钟线通常建议看1天
        "5m": "5d",    # 5分钟线看5天
        "15m": "1mo",
        "30m": "1mo",
        "1h": "2y",
        "1d": "max"
    }
    interval = st.selectbox("K线周期", list(interval_map.keys()), index=1)
    
    # 根据选择的周期自动推荐时间跨度
    suggested_period = interval_map[interval]
    period = st.text_input("数据跨度 (如 1d, 5d, 1mo)", value=suggested_period)
    
    st.divider()
    bins_count = st.slider("价格区间细分", 50, 200, 80)
    va_percent = st.slider("价值区域占比 (%)", 50, 90, 70) / 100.0

@st.cache_data(ttl=60) # 分钟级数据建议缓存时间设短一点
def load_intraday_data(ticker, p, i):
    df = yf.download(ticker, period=p, interval=i)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # 处理日期，确保 Plotly 能正确识别时间
    df.index = pd.to_datetime(df.index)
    return df

try:
    df = load_intraday_data(symbol, period, interval)

    if df.empty:
        st.warning(f"未找到 {symbol} 在 {interval} 周期下的数据。请尝试缩短数据跨度。")
    else:
        # --- 计算逻辑 ---
        price_min, price_max = df['Low'].min(), df['High'].max()
        bins = np.linspace(price_min, price_max, bins_count)
        
        # 使用成交量加权分配
        df['bin_mid'] = pd.cut(df['Close'], bins=bins, labels=bins[:-1] + np.diff(bins)/2)
        vp = df.groupby('bin_mid', observed=True)['Volume'].sum().reset_index()
        vp['bin_mid'] = vp['bin_mid'].astype(float)
        
        # POC 计算
        poc_idx = vp['Volume'].idxmax()
        poc_price = vp.loc[poc_idx, 'bin_mid']
        
        # Value Area (VA) 计算
        total_vol = vp['Volume'].sum()
        target_vol = total_vol * va_percent
        current_vol = vp.loc[poc_idx, 'Volume']
        up_i, down_i = poc_idx, poc_idx
        
        while current_vol < target_vol:
            v_up = vp.loc[up_i + 1, 'Volume'] if up_i + 1 < len(vp) else 0
            v_down = vp.loc[down_i - 1, 'Volume'] if down_i - 1 >= 0 else 0
            if v_up == 0 and v_down == 0: break
            if v_up >= v_down:
                current_vol += v_up
                up_i += 1
            else:
                current_vol += v_down
                down_i -= 1
        
        vah, val = vp.loc[up_i, 'bin_mid'], vp.loc[down_i, 'bin_mid']

        # --- 绘图 ---
        fig = make_subplots(rows=1, cols=2, shared_yaxes=True, 
                            column_widths=[0.75, 0.25], horizontal_spacing=0.02)

        # 1. K线图 (修正时间轴以移除无交易时段空隙)
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], 
            low=df['Low'], close=df['Close'], name=f"{interval} K线"
        ), row=1, col=1)

        # POC & VA 线
        for p, c, n in [(poc_price, "Gold", "POC"), (vah, "Cyan", "VAH"), (val, "Magenta", "VAL")]:
            fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=p, y1=p, 
                          line=dict(color=c, width=1.5, dash="dash"), row=1, col=1)

        # 2. 筹码分布柱状图
        colors = ['rgba(100, 149, 237, 0.2)'] * len(vp)
        for i in range(down_i, up_i + 1): colors[i] = 'rgba(100, 149, 237, 0.6)'
        colors[poc_idx] = 'Gold'

        fig.add_trace(go.Bar(x=vp['Volume'], y=vp['bin_mid'], orientation='h', 
                             marker_color=colors, name="成交量分布"), row=1, col=2)

        # 移除 X 轴上的空时间段 (非交易时间)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), # 移除周六周日
                                      dict(bounds=[16, 9.5], pattern="hour")], # 移除美股非交易时段
                         row=1, col=1)

        fig.update_layout(template="plotly_dark", height=750, showlegend=False, 
                          xaxis_rangeslider_visible=False, margin=dict(t=30, b=30))
        
        st.plotly_chart(fig, use_container_width=True)

        # 数据面板
        m1, m2, m3 = st.columns(3)
        m1.metric("当前价格", f"${df['Close'].iloc[-1]:.2f}")
        m2.metric("POC 核心位", f"${poc_price:.2f}")
        m3.metric("价值区间 (VAH-VAL)", f"{vah:.2f} - {val:.2f}")

except Exception as e:
    st.info(f"提示: 请确保代码正确及时间跨度有效。错误详情: {e}")
