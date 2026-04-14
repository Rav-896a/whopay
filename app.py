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

# --- 2. 使用者身分識別 (Cookie 管理) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# 緩衝機制
if "cookie_ready" not in st.session_state:
    time.sleep(0.5)
    st.session_state.cookie_ready = True

saved_name = cookie_manager.get("user_nickname")

if saved_name and ("my_name" not in st.session_state or st.session_state.my_name is None):
    st.session_state.my_name = saved_name

# --- 登入畫面 ---
if "my_name" not in st.session_state or st.session_state.my_name is None:
    st.title("👋 歡迎使用聚餐帳本")
    st.write("請先報上名號：")
    user_input = st.text_input("輸入你的稱呼", key="login_input")
    
    if st.button("進入帳本"):
        if user_input:
            clean_name = user_input.strip()
            # 寫入 Cookie 與 Session
            cookie_manager.set("user_nickname", clean_name, expires_at=None)
            st.session_state.my_name = clean_name
            st.success("登入成功，正在同步數據...")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("請輸入名稱")
    st.stop()

# --- 3. 動態讀取現有成員 ---
headers = sheet.row_values(1)
if not headers or len(headers) < 4:
    base_headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(base_headers, 1)
    headers = base_headers

existing_friends = [h.strip() for h in headers[4:]]

# --- 4. 側邊欄：成員管理與身分切換 ---
with st.sidebar:
    st.header("👤 個人設定")
    st.write(f"目前身分：**{st.session_state.my_name}**")
    
    if st.button("登出 / 更換身分"):
        # 強制清除
        cookie_manager.delete("user_nickname")
        st.session_state.my_name = None
        # 使用 JavaScript 強制重新載入頁面，徹底清除狀態
        st.write('<script>window.location.reload();</script>', unsafe_allow_html=True)
        st.rerun()

    st.divider()
    st.header("👥 成員管理")
    new_friend = st.text_input("新增其他朋友名單", placeholder="輸入朋友暱稱")
    if st.button("確認新增朋友"):
        if new_friend and new_friend.strip() not in existing_friends:
            new_f = new_friend.strip()
            new_col_index = len(headers) + 1
            sheet.update_cell(1, new_col_index, new_f)
            st.success(f"已將 {new_f} 加入成員清單！")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("名稱重複或為空")

# 確保「目前使用者」一定在名單內 (防呆)
if st.session_state.my_name not in existing_friends:
    new_col_index = len(headers) + 1
    sheet.update_cell(1, new_col_index, st.session_state.my_name)
    existing_friends.append(st.session_state.my_name)
    headers.append(st.session_state.my_name)

# --- 5. 主要介面 ---
st.title("🤝 團內借貸紀錄")

tab1, tab2 = st.tabs(["📝 新增聚餐", "📊 目前餘額與清帳"])

with tab1:
    st.header("新增聚餐紀錄")
    date = st.date_input("聚餐日期")
    total_amount = st.number_input("總金額", min_value=0, value=0)
    
    # 這裡現在可以選到你剛新增的朋友了
    payer = st.selectbox("誰先墊錢？", existing_friends, index=existing_friends.index(st.session_state.my_name))
    attendees = st.multiselect("參與者", existing_friends, default=[], placeholder="請選擇本次參與的朋友")

    special_expenses = {}
    if attendees:
        with st.expander("個人額外支出 (如：加點甜點)"):
            for p in attendees:
                special_expenses[p] = st.number_input(f"{p} 的加點", min_value=0, value=0, key=f"add_{p}")

    if st.button("儲存這筆紀錄"):
        if total_amount <= 0 or not attendees:
            st.warning("請填寫金額與參與者")
        else:
            total_special = sum(special_expenses.values())
            common_pool = total_amount - total_special
            base_share = common_pool / len(attendees)
            
            # 重新抓取最即時的標題順序
            latest_headers = sheet.row_values(1)
            new_row = [str(date), payer, total_amount, ",".join(attendees)]
            
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
            st.success("紀錄已存入 Google Sheets！")
            st.balloons()

with tab2:
    st.header("目前債務狀況")
    all_data = sheet.get_all_values()
    if len(all_data) <= 1:
        st.info("尚無數據")
    else:
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        balances = {}
        # 這裡動態生成卡片
        cols = st.columns(len(existing_friends))
        for i, f in enumerate(existing_friends):
            if f in df.columns:
                val = pd.to_numeric(df[f], errors='coerce').sum()
                balances[f] = val
                cols[i].metric(f, f"{val:.0f}")

        st.divider()
        st.subheader("💡 簡化清帳建議")
        receivers = {k: v for k, v in balances.items() if v > 0.1}
        payers = {k: -v for k, v in balances.items() if v < -0.1}
        
        if not receivers and not payers:
            st.write("目前大家互不相欠！")
        else:
            for p, p_amt in list(payers.items()):
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0.1:
                        st.info(f"👉 **{p}** 應給 **{r}**： {settle:.0f} 元")
                        p_amt -= settle
                        receivers[r] -= settle
                        if p_amt <= 0.1: break
