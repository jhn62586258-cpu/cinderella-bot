import streamlit as st
import json
import os
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(page_title="신데렐라 세탁 비서", page_icon="👑", layout="centered")

DB_FILE = "orders.json"
BANK_ACCOUNT = "신한 110-431-757165 조한나"

def load_orders():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception:
            return {}
    return {}

def save_orders(orders):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

if 'orders' not in st.session_state:
    st.session_state.orders = load_orders()

if 'order_counter' not in st.session_state:
    st.session_state.order_counter = max(st.session_state.orders.keys()) + 1 if st.session_state.orders else 1

st.title("👑 신데렐라 세탁소 스마트 비서")
st.markdown("점장님 환영합니다! 사진을 올리고 의류별 상태를 선택해 주세요.")

# 탭 메뉴 구성
tab1, tab2, tab3 = st.tabs(["📥 세탁물 접수", "📊 실시간 현황판", "💬 민원 응대 가이드"])

with tab1:
    st.header("새 세탁물 접수하기")
    
    customer_info = st.text_input("🏠 고객 정보 (예: 한마음 101-1206)", placeholder="동·호수 또는 고객명을 입력하세요")
    uploaded_files = st.file_uploader("📸 세탁물 사진 업로드 (여러 장 가능)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        st.info(f"총 {len(uploaded_files)}장의 사진이 업로드되었습니다.")
        
        item_statuses = {}
        for i, file in enumerate(uploaded_files, 1):
            st.image(file, width=150, caption=f"의류 #{i}")
            status = st.selectbox(f"의류 #{i} 상태 선택", ["일반세탁", "보풀제거 필요", "특수오염 있음"], key=f"status_{i}")
            item_statuses[i] = status
        
        if st.button("🚀 접수 완료 및 안내문 생성", type="primary"):
            if not customer_info:
                st.warning("⚠️ 고객 정보(동·호수)를 입력해 주세요!")
            else:
                today = datetime.now()
                delivery_date = today + timedelta(days=5)
                
                order_id = st.session_state.order_counter
                st.session_state.order_counter += 1
                
                st.session_state.orders[order_id] = {
                    'customer': customer_info,
                    'count': len(uploaded_files),
                    'status': '접수완료',
                    'date': today.strftime('%m/%d')
                }
                save_orders(st.session_state.orders)
                
                items_formatted = "\n".join([f"({i}) {st_val}" for i, st_val in item_statuses.items()])
                
                st.success(f"🎉 주문 #{order_id} 접수 완료!")
                
                result_markdown = (
                    f"[신데렐라 세탁 수거/검품 안내]\n"
                    f"고객님({customer_info})의 세탁물 총 {len(uploaded_files)}벌 검품이 완료되었습니다.\n\n"
                    f"▪️ 세탁 내역:\n{items_formatted}\n\n"
                    f"▪️ 배송 예정일: {delivery_date.strftime('%m월 %d일')} 전후\n\n"
                    f"입금이 확인되면 즉시 맞춤 세탁 및 케어가 진행됩니다.\n"
                    f"입금 계좌: {BANK_ACCOUNT}"
                )
                
                st.markdown("### 📋 고객 전송용 복사 문구")
                st.code(result_markdown, language="text")

with tab2:
    st.header("📊 실시간 매장 현황판")
    
    orders = st.session_state.orders
    if not orders:
        st.info("현재 접수된 주문이 없습니다.")
    else:
        for oid, info in list(orders.items()):
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.write(f"**#{oid}** {info['customer']} ({info['count']}벌)")
            with col2:
                st.write(f"상태: `{info['status']}`")
            with col3:
                if st.button(f"🗑️ 삭제", key=f"del_{oid}"):
                    del orders[oid]
                    save_orders(orders)
                    st.rerun()
            st.divider()

with tab3:
    st.header("💬 상황별 민원/진상 응대 가이드")
    
    guide_choice = st.selectbox("어떤 상황인가요?", [
        "1. 드라이클리닝 냄새 안 난다고 할 때",
        "2. 오염/피 안 지워졌다고 할 때",
        "3. 화내며 당장 전화하라고 할 때",
        "4. 아울렛/오래된 옷 망가졌다 할 때"
    ])
    
    if "1" in guide_choice:
        st.info('📢 "기름 냄새가 안 나야 가장 안전한 정품 드라이클리닝입니다! 안심하세요."')
    elif "2" in guide_choice:
        st.info('📢 "원단을 보호하는 안전 범위 내에서 최선으로 처리했습니다. 무리한 작업은 탈색을 유발합니다."')
    elif "3" in guide_choice:
        st.info('📢 즉답 금지! 공장에서 상태를 파악한 후 점장님이 먼저 전화를 걸어 차분히 설명하세요.')
    elif "4" in guide_choice:
        st.info('📢 "과실이 아니라 시간이 지나며 발생한 원단 삭음 현상입니다."')
