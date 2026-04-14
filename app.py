import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import extra_streamlit_components as stx  # 新增 Cookie 套件

# --- 1. 核心連線與初始化 ---
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

# --- 2. 使用者身分識別 (使用 Cookie 記憶) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# 嘗試從 Cookie 讀取名字
if "my_name" not in st.session_state:
    # 這裡會從瀏覽器抓取名為 "user_nickname" 的 Cookie
    saved_name = cookie_manager.get("user_nickname")
    st.session_state.my_name = saved_name

# 如果 Cookie 沒資料，顯示登入畫面
if not st.session_state.my_name:
    st.title("👋 歡迎使用聚餐帳本")
    st.write("這是你們專屬的互助空間，請先告訴我你的稱呼：")
    user_input = st.text_input("輸入暱稱 (例如：歐布拉克, 豬魔大長老...)", placeholder="這將作為你在帳本中的身分")
    if st.button("進入帳本"):
        if user_input:
            name = user_input.strip()
            st.session_state.my_name = name
            # 寫入 Cookie，有效期設為 365 天
            cookie_manager.set("user_nickname", name, expires_at=None)
            st.rerun()
        else:
            st.warning("請輸入名稱以繼續")
    st.stop()

# --- 3. 動態讀取現有成員 ---
all_values = sheet.get_all_values()
if not all_values:
    base_headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(base_headers, 1)
    all_values = [base_headers]

headers = all_values[0]
existing_friends = headers[4:]

# 如果目前使用者不在清單中，自動在 Google Sheets 新增一欄
if st.session_state.my_name not in existing_friends:
    new_col_index = len(headers) + 1
    sheet.update_cell(1, new_col_index, st.session_state.my_name)
    existing_friends.append(st.session_state.my_name)
    st.toast(f"✨ 歡迎新朋友 {st.session_state.my_name} 加入帳本！")

# --- 4. 主要介面 ---
st.title("🤝 團內借貸紀錄")
st.caption(f"當前使用者：{st.session_state.my_name}")

# 側邊欄提供登出選項
with st.sidebar:
    st.write(f"Hi, **{st.session_state.my_name}**")
    if st.button("登出 / 更換暱稱"):
        cookie_manager.delete("user_nickname")
        st.session_state.my_name = None
        st.rerun()

tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳"])

with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    
    # 墊錢人預設為當前使用者
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
            
            new_row_dict = {h: 0 for h in headers}
            new_row_dict["日期"] = str(date)
            new_row_dict["墊錢人"] = payer
            new_row_dict["總額"] = total_amount
            new_row_dict["參與者"] = ",".join(attendees)
            
            for f in existing_friends:
                net = 0
                if f in attendees:
                    debt = base_share + special_expenses.get(f, 0)
                    net = (total_amount - debt) if f == payer else -debt
                elif f == payer:
                    net = total_amount
                new_row_dict[f] = net
            
            row_to_append = [new_row_dict.get(h, 0) for h in headers]
            sheet.append_row(row_to_append)
            st.success("紀錄已同步！")
            st.balloons() # 儲存成功噴個氣球增加趣味感

with tab2:
    st.header("目前債務狀況")
    # 重新讀取資料以確保顯示最新狀態
    all_values_refresh = sheet.get_all_values()
    df = pd.DataFrame(all_values_refresh[1:], columns=all_values_refresh[0])
    
    if df.empty:
        st.info("尚無數據")
    else:
        balances = {}
        cols = st.columns(len(existing_friends))
        for i, f in enumerate(existing_friends):
            val = pd.to_numeric(df[f], errors='coerce').sum()
            balances[f] = val
            cols[i].metric(f, f"{val:.0f}")
        
        st.divider()
        st.subheader("💡 簡化清帳建議")
        
        receivers = {k: v for k, v in balances.items() if v > 0}
        payers = {k: -v for k, v in balances.items() if v < 0}
        
        if not receivers and not payers:
            st.write("目前大家帳目兩清，太棒了！")
        else:
            for p, p_amt in payers.items():
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0.1:
                        st.info(f"👉 **{p}** 應給 **{r}**： {settle:.0f} 元")
                        p_amt -= settle
                        receivers[r] -= settle
