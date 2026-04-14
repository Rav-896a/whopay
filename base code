import streamlit as st

st.title("🍴 好友聚餐分帳助手")
st.write("計算公費平分與個人加點，讓收錢不再尷尬！")

# 1. 基本設定
friends = ["A", "B", "C", "D", "E", "F", "G"]

# 2. 側邊欄輸入
with st.sidebar:
    st.header("📌 基礎資訊")
    total_amount = st.number_input("本次聚餐總金額", min_value=0, value=1580)
    payer = st.selectbox("誰先墊錢的？", friends)
    
# 3. 選擇參與者 (使用多選框)
attendees = st.multiselect("誰參與了這次聚餐？", friends, default=friends[:4])

if attendees:
    st.subheader("📝 個人特定支出 (如：甜點、飲料)")
    special_expenses = {}
    for person in attendees:
        # 為每個人建立一個輸入框
        special_expenses[person] = st.number_input(f"{person} 的額外支出", min_value=0, value=0, key=person)

    if st.button("🚀 開始計算分帳"):
        # 核心邏輯
        total_special = sum(special_expenses.values())
        common_pool = total_amount - total_special
        
        if common_pool < 0:
            st.error("錯誤：個人支出總和超過了總金額！")
        else:
            base_share = common_pool / len(attendees)
            
            st.success(f"計算完成！每人公費平分為：{base_share:.0f} 元")
            
            # 顯示結果表格
            results = []
            for name in attendees:
                final_amount = base_share + special_expenses[name]
                if name == payer:
                    results.append({"成員": name, "狀態": "墊錢人", "應收回": f"{total_amount - final_amount:.0f} 元"})
                else:
                    results.append({"成員": name, "狀態": f"應給 {payer}", "應付金額": f"{final_amount:.0f} 元"})
            
            st.table(results)
