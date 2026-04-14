import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# --- 1. 連結 Google Sheets 與初始化 ---
def init_sheet():
    info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(credentials)
    
    try:
        sh = client.open("聚餐記帳")
        sheet = sh.get_worksheet(0)
        
        first_row = sheet.row_values(1)
        # 資料庫欄位永遠保持 A, B, C... 確保計算邏輯不崩潰
        expected_headers = ["日期", "墊錢人", "總額", "參與者", "A", "B", "C", "D", "E", "F", "G"]
        
        if not first_row:
            sheet.insert_row(expected_headers, 1)
            st.toast("✅ 已自動初始化試算表！")
        
        return sheet
    except Exception as e:
        st.error(f"連線失敗：{e}")
        st.stop()

sheet = init_sheet()

# --- 2. 自定義暱稱系統 (Session State) ---
# 建立一個代碼與顯示名稱的對照表
db_keys = ["A", "B", "C", "D", "E", "F", "G"]

if "name_map" not in st.session_state:
    # 預設對照表
    st.session_state.name_map = {key: key for key in db_keys}

st.title("🤝 團內借貸紀錄")

# 成員設定區（放在側邊欄或摺疊選單）
with st.sidebar.expander("👤 成員暱稱設定"):
    st.write("請設定每個代號對應的暱稱：")
    updated_map = {}
    for key in db_keys:
        val = st.text_input(f"成員 {key}：", value=st.session_state.name_map[key], key=f"set_{key}")
        updated_map[key] = val
    
    if st.button("更新暱稱名單"):
        st.session_state.name_map = updated_map
        st.success("暱稱已更新！")
        st.rerun()

# 為了方便後續使用，建立一個「目前使用的暱稱清單」
current_friends = [st.session_state.name_map[k] for k in db_keys]
# 建立「暱稱轉代碼」的工具，存檔時會用到
name_to_key = {v: k for k, v in st.session_state.name_map.items()}

# --- 3. UI 分頁 ---
tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳建議"])

with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    
    # 這裡選單顯示的是「暱稱」
    payer_name = st.selectbox("誰先墊錢？", current_friends)
    attendees_names = st.multiselect("參與者", current_friends, default=current_friends)

    special_expenses = {}
    if attendees_names:
        with st.expander("點擊展開個人加點微調"):
            for name in attendees_names:
                special_expenses[name] = st.number_input(f"{name} 的額外支出", min_value=0, value=0, key=f"add_{name}")

    if st.button("儲存這筆紀錄"):
        if not attendees_names or total_amount <= 0:
            st.warning("請填寫完整資訊")
        else:
            total_special = sum(special_expenses.values())
            common_pool = total_amount - total_special
            base_share = common_pool / len(attendees_names)
            
            # 轉換為資料庫格式（轉回 A, B, C...）
            payer_key = name_to_key[payer_name]
            new_row = [str(date), payer_name, total_amount, ",".join(attendees_names)]
            
            # 依照 A-G 的順序計算淨值
            for key in db_keys:
                net = 0
                friend_name = st.session_state.name_map[key]
                if friend_name in attendees_names:
                    my_debt = base_share + special_expenses.get(friend_name, 0)
                    if key == payer_key:
                        net = total_amount - my_debt
                    else:
                        net = -my_debt
                elif key == payer_key:
                    net = total_amount
                new_row.append(net)
            
            sheet.append_row(new_row)
            st.success("紀錄已成功同步！")

with tab2:
    st.header("目前債務狀況")
    # 使用 get_all_values 避免 get_all_records 可能的標題對不上的問題
    all_values = sheet.get_all_values()
    
    if len(all_values) <= 1:
        st.info("目前尚無歷史紀錄。")
    else:
        df = pd.DataFrame(all_values[1:], columns=all_values[0])
        
        # 顯示儀表板
        cols = st.columns(len(db_keys))
        balances = {}
        for i, key in enumerate(db_keys):
            # 從 Excel 抓取數據並計算
            val = pd.to_numeric(df[key], errors='coerce').sum()
            balances[key] = val
            
            # 顯示時轉換回「暱稱」
            display_name = st.session_state.name_map[key]
            cols[i].metric(display_name, f"{val:.0f}")
            
        st.divider()
        st.subheader("💡 簡化清帳建議")
        
        # 這裡用暱稱來做清帳建議，比較好讀
        receivers = {st.session_state.name_map[k]: v for k, v in balances.items() if v > 0}
        payers = {st.session_state.name_map[k]: -v for k, v in balances.items() if v < 0}
        
        if not receivers and not payers:
            st.write("目前大家帳目兩清！")
        else:
            for p, p_amt in payers.items():
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0.1: # 避開浮點數微小誤差
                        st.info(f"👉
