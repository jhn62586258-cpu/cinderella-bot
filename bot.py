import logging
import json
import os
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

# ====================================================
# 🔑 BOT TOKEN (Railway 환경 변수 우선 사용)
# ====================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8886513457:AAHcc2RaSWcHnCxGP1iha6Qg2TH9qZ4jlZA")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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
        logging.error(f"데이터 저장 실패: {e}")

store_orders = load_orders()

if store_orders:
    order_counter = max(store_orders.keys()) + 1
else:
    order_counter = 1

# 미디어 그룹(앨범) 묶음 처리를 위한 저장소
media_groups = defaultdict(list)
media_group_tasks = {}

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 현재 매장 현황판 보기", callback_data='view_status')],
        [InlineKeyboardButton("💬 상황별 민원/진상 응대 가이드", callback_data='menu_guide')],
        [InlineKeyboardButton("🚨 마케팅/운영 체크리스트", callback_data='menu_checklist')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👑 [신데렐라 세탁] 점장 전용 스마트 비서 봇\n\n"
        "점장님, 환영합니다! 🎉\n\n"
        "✨ 사용법 요약:\n"
        "1. 세탁물 사진(또는 여러 장 묶음)과 함께 첫 사진에 '101동 1206호'처럼 동·호수를 적어주세요.\n"
        "2. 특정 주문을 지우고 싶을 때는 '/delete 주문번호'를 입력하세요! (예: /delete 1)\n"
        "3. 메뉴가 필요할 때는 언제든 /menu를 입력하세요!\n"
    )
    await update.message.reply_text(welcome_text)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 [메인 메뉴] 원하시는 기능을 선택해 주세요:", reply_markup=get_main_keyboard())

async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global store_orders
    try:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ 삭제할 주문번호를 입력해 주세요.\n사용법: /delete 1")
            return
        
        target_id = int(args[0])
        if target_id in store_orders:
            deleted_order = store_orders.pop(target_id)
            save_orders(store_orders)
            await update.message.reply_text(f"🗑️ [주문 #{target_id}] ({deleted_order['customer']}) 내역이 성공적으로 삭제되었습니다!")
        else:
            await update.message.reply_text(f"⚠️ 주문번호 #{target_id}번을 찾을 수 없습니다.")
    except Exception:
        await update.message.reply_text("⚠️ 올바른 숫자를 입력해 주세요. 예시: /delete 1")

# ====================================================
# 📸 사진 수신 및 앨범(미디어 그룹) 통합 처리 로직
# ====================================================
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.effective_chat.id
    caption = message.caption
    media_group_id = message.media_group_id

    if 'active_sessions' not in context.bot_data:
        context.bot_data['active_sessions'] = {}
    
    if chat_id not in context.bot_data['active_sessions']:
        context.bot_data['active_sessions'][chat_id] = {
            'customer': '미입력 고객',
            'photo_count': 0,
            'selections': {}
        }

    session = context.bot_data['active_sessions'][chat_id]
    if caption:
        session['customer'] = caption

    if not media_group_id:
        session['photo_count'] += 1
        total_photos = session['photo_count']
        session['selections'][total_photos] = '일반세탁'
        await send_batch_ui(chat_id, session, context)
        return

    media_groups[media_group_id].append(message)

    if media_group_id in media_group_tasks:
        media_group_tasks[media_group_id].cancel()

    async def delayed_process():
        await asyncio.sleep(1.2)
        msgs = media_groups.pop(media_group_id, [])
        media_group_tasks.pop(media_group_id, None)
        if msgs:
            session['photo_count'] += len(msgs)
            total_photos = session['photo_count']
            for i in range(1, total_photos + 1):
                if i not in session['selections']:
                    session['selections'][i] = '일반세탁'
            await send_batch_ui(chat_id, session, context)

    media_group_tasks[media_group_id] = asyncio.create_task(delayed_process())

async def send_batch_ui(chat_id, session, context):
    total_photos = session['photo_count']
    keyboard = []
    for i in range(1, total_photos + 1):
        current_status = session['selections'].get(i, '일반세탁')
        keyboard.append([InlineKeyboardButton(f"🧥 [{i}번 의류] 선택: {current_status}", callback_data=f'noop_{i}')])
        keyboard.append([
            InlineKeyboardButton(f"{i}번 ✂️보풀", callback_data=f'set_{i}_pilling'),
            InlineKeyboardButton(f"{i}번 🍷오염", callback_data=f'set_{i}_stain'),
            InlineKeyboardButton(f"{i}번 ✅일반", callback_data=f'set_{i}_none')
        ])
    
    keyboard.append([InlineKeyboardButton("🚀 [모든 의류 접수 완료 및 안내문 생성]", callback_data='finish_batch_session')])
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📸 [신데렐라 세탁 통합 접수 중]\n"
            f"🏠 고객(동호수): {session['customer']}\n"
            f"📦 총 접수 사진: {total_photos}장\n\n"
            f"👇 각 옷마다 아래 버튼을 눌러 상태를 지정한 뒤 [접수 완료]를 누르세요!"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ====================================================
# 🔘 버튼 클릭 및 상호작용 처리
# ====================================================
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    global order_counter, store_orders

    today = datetime.now()
    delivery_date = today + timedelta(days=5)
    
    if 'active_sessions' not in context.bot_data:
        context.bot_data['active_sessions'] = {}
    
    session = context.bot_data['active_sessions'].get(chat_id, None)

    if data.startswith('noop_'):
        return

    if data.startswith('set_'):
        parts = data.split('_')
        item_idx = int(parts[1])
        c_type = parts[2]
        
        type_map = {'pilling': '보풀제거 필요', 'stain': '특수오염 있음', 'none': '일반세탁'}
        selected_text = type_map.get(c_type, '일반세탁')

        if session:
            session['selections'][item_idx] = selected_text

        total_photos = session['photo_count'] if session else 1
        keyboard = []
        for i in range(1, total_photos + 1):
            current_status = session['selections'].get(i, '일반세탁') if session else '일반세탁'
            keyboard.append([InlineKeyboardButton(f"🧥 [{i}번 의류] 선택: {current_status}", callback_data=f'noop_{i}')])
            keyboard.append([
                InlineKeyboardButton(f"{i}번 ✂️보풀", callback_data=f'set_{i}_pilling'),
                InlineKeyboardButton(f"{i}번 🍷오염", callback_data=f'set_{i}_stain'),
                InlineKeyboardButton(f"{i}번 ✅일반", callback_data=f'set_{i}_none')
            ])
        keyboard.append([InlineKeyboardButton("🚀 [모든 의류 접수 완료 및 안내문 생성]", callback_data='finish_batch_session')])

        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass

    elif data == 'finish_batch_session':
        if not session:
            await query.message.reply_text("세션 정보가 만료되었습니다. 사진을 다시 보내주세요.")
            return

        customer_name = session['customer']
        total_photos = session['photo_count']
        
        items_summary = []
        for i in range(1, total_photos + 1):
            st = session['selections'].get(i, '일반세탁')
            items_summary.append(f"({i}) {st}")

        items_formatted = "\n".join(items_summary)

        order_id = order_counter
        order_counter += 1

        store_orders[order_id] = {
            'customer': customer_name,
            'count': total_photos,
            'status': '접수완료',
            'date': today.strftime
