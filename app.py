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
def get_gspread_client():
    info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(credentials)

def init_sheet():
    client = get_gspread_client()
    sh = client.open("聚餐記帳")
    return sh, sh.get_worksheet(0)

sh, sheet = init_sheet()

# --- 2. 使用者身分識別 ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

if "cookie_ready" not in st.session_state:
    time.sleep(0.5)
    st.session_state.cookie_ready = True

saved_name = cookie_manager.get("user_nickname")
if saved_name and ("my_name" not in st.session_state or st.session_state.my_name is None):
    st.session_state.my_name = saved_name

if "my_name" not in st.session_state or st.session_state.my_name is None:
    st.title("👋 歡迎使用聚餐帳本")
    user_input = st.text_input("輸入你的稱呼", key="login_input")
    if st.button("進入帳本"):
        if user_input:
            clean_name = user_input.strip()
            cookie_manager.set("user_nickname", clean_name, expires_at=None)
            st.session_state.my_name = clean_name
            st.rerun()
    st.stop()

# --- 3. 讀取標題與成員 ---
headers = sheet.row_values(1)
if not headers or len(headers) < 4:
    headers = ["日期", "墊錢人", "總額", "參與者"]
    sheet.insert_row(headers, 1)

existing_friends = [h.strip() for h in headers[4:]]

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("👤 個人設定")
    st.write(f"目前身分：**{st.session_state.my_name}**")
    if st.button("登出 / 更換身分"):
        past_date = datetime.now() - timedelta(days=1)
        cookie_manager.set("user_nickname", "", expires_at=past_date)
        cookie_manager.delete("user_nickname")
        st.session_state.my_name = None
        st.write('<script>window.location.href = window.location.href.split("?")[0];</script>', unsafe_allow_html=True)
        st.rerun()

    st.divider()
    st.header("👥 成員管理")
    new_friend = st.text_input("新增朋友到名單", key="new_friend_input")
    if st.button("確認新增"):
        if new_friend and new_friend.strip() not in existing_friends:
            new_f = new_friend.strip()
            sheet.update_cell(1, len(headers) + 1, new_f)
            st.success(f"已將 {new_f} 加入！")
            time.sleep(1)
            st.rerun()

if st.session_state.my_name not in existing_friends:
    sheet.update_cell(1, len(headers) + 1, st.session_state.my_name)
    st.rerun()

# --- 5. 主要介面 ---
st.title("🤝 團內借貸紀錄")
tab1, tab2 = st.tabs(["📝 新增紀錄", "📊 目前餘額與清帳"])

with tab1:
    mode = st.radio("選擇類型", ["🍽️ 聚餐支出", "💸 私下還款/調帳"], horizontal=True)
    if mode == "🍽️ 聚餐支出":
        st.header("新增聚餐紀錄")
        date = st.date_input("聚餐日期")
        location = st.text_input("吃了哪間店？ (選填)", placeholder="例如：鼎泰豐、麥當勞")
        total_amount = st.number_input("總金額", min_value=0, value=0)
        
        payers = st.multiselect("誰付了錢？", existing_friends, default=[st.session_state.my_name])
        
        pay_details = {}
        if len(payers) > 1:
            st.info("💡 分配每人墊付金額：")
            pay_cols = st.columns(len(payers))
            for i, p in enumerate(payers):
                with pay_cols[i]:
                    pay_details[p] = st.number_input(f"{p} 墊了", min_value=0, value=0, key=f"pay_{p}")
        elif len(payers) == 1:
            pay_details[payers[0]] = total_amount

        attendees = st.multiselect("參與者", existing_friends, default=[], placeholder="勾選參與者")
        special_expenses = {}
        if attendees:
            with st.expander("個人額外支出 (平分則不填)"):
                for p in attendees:
                    special_expenses[p] = st.number_input(f"{p} 的加點", min_value=0, value=0, key=f"add_{p}")

        if st.button("儲存聚餐紀錄"):
            if total_amount <= 0 or not attendees or not payers:
                st.warning("請填寫完整資訊")
            elif len(payers) > 1 and sum(pay_details.values()) != total_amount:
                st.error("金額總和不符！")
            else:
                total_special = sum(special_expenses.values())
                base_share = (total_amount - total_special) / len(attendees)
                loc_str = f"[{location}] " if location else ""
                note = f"{loc_str}聚餐: {','.join(attendees)}"
                
                new_row = [str(date), ",".join(payers), total_amount, note]
                for h in headers[4:]:
                    friend = h.strip()
                    debt = (base_share + special_expenses.get(friend, 0)) if friend in attendees else 0
                    new_row.append(pay_details.get(friend, 0) - debt)
                
                sheet.append_row(new_row)
                st.success("紀錄已同步！")
                st.balloons()
                # --- 重製邏輯：等待動畫後自動重整 ---
                time.sleep(2)
                st.rerun()

    else:
        st.header("💸 私下還款 / 調帳")
        date = st.date_input("調帳日期")
        from_p = st.selectbox("付款人", existing_friends, index=existing_friends.index(st.session_state.my_name))
        to_p = st.selectbox("收款人", [f for f in existing_friends if f != from_p])
        amount = st.number_input("轉帳金額", min_value=1, value=1)
        
        if st.button("儲存調帳"):
            new_row = [str(date), from_p, 0, f"還款: {from_p} ➡️ {to_p}"]
            for h in headers[4:]:
                friend = h.strip()
                net = amount if friend == from_p else (-amount if friend == to_p else 0)
                new_row.append(net)
            
            sheet.append_row(new_row)
            st.success("還款已記錄！")
            st.balloons()
            # --- 重製邏輯：等待動畫後自動重整 ---
            time.sleep(2)
            st.rerun()

with tab2:
    # (餘額與歸檔邏輯保持不變)
    st.header("目前債務狀況")
    all_data = sheet.get_all_values()
    if len(all_data) <= 1:
        st.info("目前無待結帳項目")
    else:
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        balances = {f: pd.to_numeric(df[f], errors='coerce').sum() for f in existing_friends}
        
        cols = st.columns(len(existing_friends))
        for i, f in enumerate(existing_friends):
            cols[i].metric(f, f"{balances[f]:.0f}")

        st.divider()
        st.subheader("💡 簡化清帳建議")
        receivers = {k: v for k, v in balances.items() if v > 0.1}
        payers_map = {k: -v for k, v in balances.items() if v < -0.1}
        
        if not receivers and not payers_map:
            st.write("目前大家互不相欠！")
        else:
            for p, p_amt in list(payers_map.items()):
                for r, r_amt in list(receivers.items()):
                    settle = min(p_amt, r_amt)
                    if settle > 0.1:
                        st.info(f"👉 **{p}** 應給 **{r}**： {settle:.0f} 元")
                        p_amt -= settle
                        receivers[r] -= settle
                        if p_amt <= 0.1: break

        st.divider()
        st.warning("⚠️ 注意：點擊下方按鈕後，目前的紀錄將會歸檔，並開啟新一輪的空白帳本。")
        if st.button("🔥 本輪結帳完畢，開始新紀錄"):
            archive_name = f"{datetime.now().strftime('%Y-%m-%d-%H%M')}-歸檔"
            sheet.update_title(archive_name)
            new_sheet = sh.add_worksheet(title="當前紀錄", rows=100, cols=20, index=0)
            new_sheet.insert_row(headers, 1)
            st.success("✅ 舊帳已成功歸檔，新帳本已開啟！")
            time.sleep(2)
            st.rerun()
