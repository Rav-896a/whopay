import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

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

# --- 2. 使用者身分識別 (第一次開啟強制輸入) ---
if "my_name" not in st.session_state:
    st.session_state.my_name = None

if not st.session_state.my_name:
    st.title("👋 歡迎使用聚餐帳本")
    st.write("這是你們專屬的互助空間，請先告訴我你的稱呼：")
    user_input = st.text_input("輸入暱稱 (例如：泰智, 小明...)", placeholder="這將作為你在帳本中的身分")
    if st.button("進入帳本"):
        if user_input:
            st.session_state.my_name = user_input.strip()
            st.rerun()
        else:
            st.warning("請輸入名稱以繼續")
    st.stop() # 沒輸入名字前，後面的代碼都不會執行

# --- 3. 動態讀取現有成員 ---
# 從試算表第一列讀取目前有哪些成員
all_values = sheet.get_all_values()
if not all_values:
    # 如果是空表，初始化基本欄位
    base_headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(base_headers, 1)
    all_values = [base_headers]

headers = all_values[0]
existing_friends = headers[4:] # 前四欄是固定的資訊

# 如果目前使用者不在清單中，自動在 Google Sheets 新增一欄
if st.session_state.my_name not in existing_friends:
    # 找到最後一欄並新增標題
    new_col_index = len(headers) + 1
    sheet.update_cell(1, new_col_index, st.session_state.my_name)
    existing_friends.append(st.session_state.my_name)
    st.toast(f"✨ 歡迎新朋友 {st.session_state.my_name} 加入帳本！")

# --- 4. 主要介面 ---
st.title("🤝 團內借貸紀錄")
st.caption(f"當前使用者：{st.session_state.my_name}")

tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳"])

with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    
    # 墊錢人預設為當前使用者，增加便利性
    payer = st.selectbox("誰先墊錢？", existing_friends, index=existing_friends.index(st.session_state.my_name))
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
            
            # 建立這一列的資料
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
            
            # 轉換為 list 並填入
            row_to_append = [new_row_dict.get(h, 0) for h in headers]
            sheet.append_row(row_to_append)
            st.success("紀錄已同步！")

with tab2:
    st.header("目前債務狀況")
    df = pd.DataFrame(all_values[1:], columns=all_values[0])
    if df.empty:
        st.info("尚無數據")
    else:
        # 計算餘額
        balances = {}
        cols = st.columns(len(existing_friends))
        for i, f in enumerate(existing_friends):
            val = pd.to_numeric(df[f], errors='coerce').sum()
            balances[f] = val
            cols[i].metric(f, f"{val:.0f}")
        
        # 清帳邏輯 (同前，略...)
