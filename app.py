import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import extra_streamlit_components as stx
import time

# 設定頁面配置
st.set_page_config(page_title="團內借貸紀錄", layout="wide")

# --- 1. 核心連線與初始化 ---
@st.cache_resource
def init_sheet():
    info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(credentials)
    try:
        sh = client.open("聚餐記帳")
        return sh.get_worksheet(0)
    except Exception as e:
        st.error(f"連線失敗：{e}")
        st.stop()

sheet = init_sheet()

# --- 2. 使用者身分識別 (解決 Cookie 延遲與重複問題) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# 延遲機制：給 Cookie Manager 一點點時間讀取瀏覽器資料
if "cookie_ready" not in st.session_state:
    time.sleep(0.5)  # 給予 0.5 秒緩衝
    st.session_state.cookie_ready = True

# 嘗試從 Cookie 讀取名字
saved_name = cookie_manager.get("user_nickname")

# 如果 session_state 裡沒名字，但 Cookie 裡有，就同步過去
if saved_name and ("my_name" not in st.session_state or st.session_state.my_name is None):
    st.session_state.my_name = saved_name

# --- 登入畫面 ---
if "my_name" not in st.session_state or st.session_state.my_name is None:
    st.title("👋 歡迎使用聚餐帳本")
    st.write("這是你們專屬的互助空間，請先告訴我你的稱呼：")
    user_input = st.text_input("輸入暱稱", placeholder="這將作為你在帳本中的身分")
    
    if st.button("進入帳本"):
        if user_input:
            clean_name = user_input.strip()
            # 先寫入 Cookie
            cookie_manager.set("user_nickname", clean_name, expires_at=None)
            # 再寫入 Session
            st.session_state.my_name = clean_name
            st.success(f"歡迎 {clean_name}！正在準備帳本...")
            time.sleep(1) # 強制等待，確保 Cookie 寫入成功
            st.rerun()
        else:
            st.warning("請輸入名稱以繼續")
    st.stop()

# --- 3. 動態讀取現有成員 (極嚴格防重複檢查) ---

# 每次進入主介面時，強制抓取最準確的第一列標題
headers = sheet.row_values(1)

if not headers or len(headers) < 4:
    base_headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(base_headers, 1)
    headers = base_headers

# 清洗標題數據，避免因為空白導致判斷失誤
current_user = st.session_state.my_name.strip()
existing_friends = [h.strip() for h in headers[4:]]

# 核心邏輯：只有在完全沒對到名字時才新增
if current_user not in existing_friends:
    # 新增前最後一次確認 Google Sheet 的即時狀況
    fresh_headers = sheet.row_values(1)
    fresh_friends = [h.strip() for h in fresh_headers[4:]]
    
    if current_user not in fresh_friends:
        new_col_index = len(fresh_headers) + 1
        sheet.update_cell(1, new_col_index, current_user)
        # 更新本地變數
        existing_friends.append(current_user)
        headers = fresh_headers + [current_user]
        st.toast(f"✨ 歡迎新朋友 {current_user} 加入帳本！")

# --- 4. 主要介面 ---
st.title("🤝 團內借貸紀錄")
st.caption(f"當前使用者：{st.session_state.my_name}")

with st.sidebar:
    st.write(f"Hi, **{st.session_state.my_name}**")
    if st.button("登出 / 更換暱稱"):
        cookie_manager.delete("user_nickname")
        st.session_state.my_name = None
        st.rerun()

tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳"])

# --- Tab 1: 新增紀錄 (沿用原邏輯但優化穩定性) ---
with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    
    try:
        default_payer_idx = existing_friends.index(st.session_state.my_name)
    except ValueError:
        default_payer_idx = 0
        
    payer = st.selectbox("誰先墊錢？", existing_friends, index=default_payer_idx)
    attendees = st.multiselect("參與者", existing_friends, default=existing_friends)

    special_expenses = {}
    if attendees:
        with st.expander("個人額外支出 (如加點甜點)"):
            for p in attendees:
                special_expenses[p] = st.number_input(f"{p} 的加點", min_value=0, value=0, key=f"add_{p}")

    if st.button("儲存紀錄"):
        if total_amount <= 0 or not attendees:
            st.warning("資訊不完整")
        else:
            total_special = sum(special_expenses.values())
            common_pool = total_amount - total_special
            base_share = common_pool / len(attendees)
            
            # 使用最新的 headers 來對位
            latest_headers = sheet.row_values(1)
            new_row = [str(date), payer, total_amount, ",".join(attendees)]
            
            # 根據標題順序填入每個人的淨值
            for h in latest_headers[4:]:
                net = 0
                friend = h.strip()
                if friend in attendees:
                    debt = base_share + special_expenses.get(friend, 0)
                    net = (total_amount - debt) if friend == payer else -debt
                elif friend == payer:
                    net = total_amount
                new_row.append(net)
            
            sheet.append_row(new_row)
            st.success("紀錄已同步！")
            st.balloons()

# --- Tab 2: 餘額與清帳 ---
with tab2:
    st.header("目前債務狀況")
    all_data = sheet.get_all_values()
    if len(all_data) <= 1:
        st.info("尚無數據")
    else:
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        balances = {}
        cols = st.columns(len(existing_friends))
        
        for i, f in enumerate(existing_friends):
            # 確保欄位名稱正確
            if f in df.columns:
                val = pd.to_numeric(df[f], errors='coerce').sum()
                balances[f] = val
                cols[i].metric(f, f"{val:.0f}")
        
        st.divider()
        st.subheader("💡 簡化清帳建議")
        
        receivers = {k: v for k, v in balances.items() if v > 0.1}
        payers = {k: -v for k, v in balances.items() if v < -0.1}
        
        if not receivers and not payers:
            st.write("目前大家帳目兩清，太棒了！")
        else:
            for p, p_amt in list(payers.items()):
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0.1:
                        st.info(f"👉 **{p}** 應給 **{r}**： {settle:.0f} 元")
                        p_amt -= settle
                        receivers[r] -= settle
                        if p_amt <= 0.1: break
