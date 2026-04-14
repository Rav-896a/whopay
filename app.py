import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import extra_streamlit_components as stx
import time
from datetime import datetime, timedelta

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

# --- 2. 使用者身分識別 (Cookie 記憶與登入) ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

if "cookie_ready" not in st.session_state:
    time.sleep(0.5)
    st.session_state.cookie_ready = True

saved_name = cookie_manager.get("user_nickname")

if saved_name and ("my_name" not in st.session_state or st.session_state.my_name is None):
    st.session_state.my_name = saved_name

# --- 登入畫面 ---
if "my_name" not in st.session_state or st.session_state.my_name is None:
    st.title("👋 歡迎使用聚餐帳本")
    st.write("這是你們專屬的互助空間，請先報上名號：")
    user_input = st.text_input("輸入你的稱呼", key="login_input", placeholder="例如：歐布拉克")
    
    if st.button("進入帳本"):
        if user_input:
            clean_name = user_input.strip()
            cookie_manager.set("user_nickname", clean_name, expires_at=None)
            st.session_state.my_name = clean_name
            st.success("登入成功，正在同步數據...")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("請輸入名稱以繼續")
    st.stop()

# --- 3. 動態讀取與成員管理 ---
headers = sheet.row_values(1)
if not headers or len(headers) < 4:
    base_headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(base_headers, 1)
    headers = base_headers

existing_friends = [h.strip() for h in headers[4:]]

# --- 4. 側邊欄：功能選單 ---
with st.sidebar:
    st.header("👤 個人設定")
    st.write(f"目前身分：**{st.session_state.my_name}**")
    
    if st.button("登出 / 更換身分"):
        past_date = datetime.now() - timedelta(days=1)
        cookie_manager.set("user_nickname", "", expires_at=past_date)
        cookie_manager.delete("user_nickname")
        st.session_state.my_name = None
        st.write('<script>window.location.href = window.location.href.split("?")[0];</script>', unsafe_allow_html=True)
        st.success("安全登出中...")
        time.sleep(0.5)
        st.rerun()

    st.divider()
    st.header("👥 成員管理")
    new_friend = st.text_input("新增朋友到名單", placeholder="輸入朋友暱稱")
    if st.button("確認新增"):
        if new_friend and new_friend.strip() not in existing_friends:
            new_f = new_friend.strip()
            new_col_index = len(headers) + 1
            sheet.update_cell(1, new_col_index, new_f)
            st.success(f"已將 {new_f} 加入清單！")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("名稱重複或為空")

# 防呆：確保當前使用者在名單內
if st.session_state.my_name not in existing_friends:
    new_col_index = len(headers) + 1
    sheet.update_cell(1, new_col_index, st.session_state.my_name)
    existing_friends.append(st.session_state.my_name)
    headers.append(st.session_state.my_name)

# --- 5. 主要介面 ---
st.title("🤝 團內借貸紀錄")

tab1, tab2 = st.tabs(["📝 新增紀錄", "📊 目前餘額與清帳"])

with tab1:
    mode = st.radio("選擇類型", ["🍽️ 聚餐支出", "💸 私下還款/調帳"], horizontal=True)
    
    if mode == "🍽️ 聚餐支出":
        st.header("新增聚餐紀錄")
        date = st.date_input("聚餐日期")
        total_amount = st.number_input("總金額", min_value=0, value=0)
        
        # --- 多人墊錢優化邏輯 ---
        payers = st.multiselect(
            "誰付了錢？", 
            existing_friends, 
            default=[st.session_state.my_name],
            placeholder="請勾選墊錢的人"
        )
        
        pay_details = {}
        if len(payers) > 1:
            st.info("💡 偵測到多人墊錢，請分配每人墊付金額：")
            pay_cols = st.columns(len(payers))
            temp_total = 0
            for i, p in enumerate(payers):
                with pay_cols[i]:
                    amt = st.number_input(f"{p} 墊了", min_value=0, value=0, key=f"pay_val_{p}")
                    pay_details[p] = amt
                    temp_total += amt
            
            if temp_total != total_amount and temp_total > 0:
                st.warning(f"目前填寫總和 ({temp_total}) 與上方總金額 ({total_amount}) 不符！")
        
        elif len(payers) == 1:
            # 單人墊錢直接自動帶入總額
            pay_details[payers[0]] = total_amount
            st.caption(f"✅ 系統自動設定由 **{payers[0]}** 支付全額 {total_amount} 元")

        # 參與者選單
        attendees = st.multiselect("參與者", existing_friends, default=[], placeholder="請勾選參與的朋友")

        special_expenses = {}
        if attendees:
            with st.expander("個人額外支出 (平分則不填)"):
                for p in attendees:
                    special_expenses[p] = st.number_input(f"{p} 的加點", min_value=0, value=0, key=f"add_{p}")

        if st.button("儲存聚餐紀錄"):
            if total_amount <= 0 or not attendees or not payers:
                st.warning("請完整填寫金額、付款者與參與者")
            elif len(payers) > 1 and sum(pay_details.values()) != total_amount:
                st.error("各人墊付總和必須等於總金額！")
            else:
                total_special = sum(special_expenses.values())
                common_pool = total_amount - total_special
                base_share = common_pool / len(attendees)
                
                latest_headers = sheet.row_values(1)
                payers_str = ",".join(payers)
                new_row = [str(date), payers_str, total_amount, f"聚餐: {','.join(attendees)}"]
                
                for h in latest_headers[4:]:
                    friend = h.strip()
                    debt = 0
                    if friend in attendees:
                        debt = base_share + special_expenses.get(friend, 0)
                    
                    paid = pay_details.get(friend, 0)
                    net = paid - debt
                    new_row.append(net)
                
                sheet.append_row(new_row)
                st.success(f"紀錄已成功同步！由 {payers_str} 共同墊付。")
                st.balloons()

    else:
        st.header("💸 私下還款 / 調帳")
        date = st.date_input("調帳日期")
        from_person = st.selectbox("付款人", existing_friends, index=existing_friends.index(st.session_state.my_name))
        to_person = st.selectbox("收款人", [f for f in existing_friends if f != from_person])
        transfer_amount = st.number_input("轉帳金額", min_value=1, value=1)

        if st.button("儲存調帳紀錄"):
            latest_headers = sheet.row_values(1)
            new_row = [str(date), from_person, 0, f"還款: {from_person} ➡️ {to_person}"]
            
            for h in latest_headers[4:]:
                net, friend = 0, h.strip()
                if friend == from_person:
                    net = transfer_amount
                elif friend == to_person:
                    net = -transfer_amount
                new_row.append(net)
            
            sheet.append_row(new_row)
            st.success(f"已記錄還款：{from_person} ➡️ {to_person}")
            st.balloons()

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
