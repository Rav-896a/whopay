import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# 1. 連結 Google Sheets
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
        
        # --- 自動初始化邏輯開始 ---
        # 檢查第一列是否有標題
        first_row = sheet.row_values(1)
        expected_headers = ["日期", "墊錢人", "總額", "參與者", "A", "B", "C", "D", "E", "F", "G"]
        
        if not first_row:
            # 如果第一列完全空白，自動寫入標題
            sheet.insert_row(expected_headers, 1)
            st.toast("✅ 已自動為您初始化試算表標題列！")
        # --- 自動初始化邏輯結束 ---
        
        return sheet
    except Exception as e:
        st.error(f"連線失敗：{e}")
        st.stop()

# 呼叫函式
sheet = init_sheet()

# 2. 基礎設定
friends = ["A", "B", "C", "D", "E", "F", "G"]

st.title("🤝 好友長期互助帳本")

# 分成兩個分頁：記帳、查看餘額
tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳建議"])

with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    payer = st.selectbox("誰先墊錢？", friends)
    attendees = st.multiselect("參與者", friends, default=friends)

    # 個人加點微調
    special_expenses = {}
    if attendees:
        with st.expander("點擊展開個人加點微調"):
            for p in attendees:
                special_expenses[p] = st.number_input(f"{p} 的額外支出", min_value=0, value=0, key=f"add_{p}")

    if st.button("儲存這筆紀錄"):
        if not attendees or total_amount <= 0:
            st.warning("請填寫完整資訊")
        else:
            # 計算邏輯
            total_special = sum(special_expenses.values())
            common_pool = total_amount - total_special
            base_share = common_pool / len(attendees)
            
            # 準備存入 Google Sheets 的資料 (一列代表一筆紀錄)
            # 格式：日期, 墊錢人, 總額, 參與者(字串), 每人應付細節(JSON字串或簡述)
            new_row = [str(date), payer, total_amount, ",".join(attendees)]
            
            # 為了方便計算餘額，我們把每個人在這筆帳中「對應的淨值」算出來
            # 墊錢人是 + (總額 - 應付)，其他人是 - (應付)
            for f in friends:
                net = 0
                if f in attendees:
                    my_debt = base_share + special_expenses.get(f, 0)
                    if f == payer:
                        net = total_amount - my_debt
                    else:
                        net = -my_debt
                elif f == payer: # 沒吃但墊錢的情況
                    net = total_amount
                new_row.append(net)
            
            sheet.append_row(new_row)
            st.success("紀錄已成功同步至 Google Sheets！")

with tab2:
    st.header("目前債務狀況")
    # 從 Google Sheets 讀取歷史資料
    data = sheet.get_all_records()
    if not data:
        st.info("目前尚無歷史紀錄。")
    else:
        df = pd.DataFrame(data)
        # 計算每個人的總和 (從第 5 欄開始是每個人的名字)
        balances = {f: df[f].sum() for f in friends}
        
        # 顯示儀表板
        cols = st.columns(len(friends))
        for i, f in enumerate(friends):
            bal = balances[f]
            color = "green" if bal >= 0 else "red"
            cols[i].metric(f, f"{bal:.0f}", delta=None)
            
        st.divider()
        st.subheader("💡 簡化清帳建議")
        # 這裡可以加入更複雜的債務抵銷演算法
        # 簡易版：顯示誰該拿錢，誰該吐錢
        receivers = {k: v for k, v in balances.items() if v > 0}
        payers = {k: -v for k, v in balances.items() if v < 0}
        
        if not receivers and not payers:
            st.write("目前大家帳目兩清，太棒了！")
        else:
            st.write("若現在要結清：")
            for p, p_amt in payers.items():
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0:
                        st.info(f"👉 **{p}** 應給 **{r}**： {settle:.0f} 元")
                        p_amt -= settle
                        receivers[r] -= settle
