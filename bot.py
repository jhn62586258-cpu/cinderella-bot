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
            'date': today.strftime('%m/%d')
        }
        save_orders(store_orders)

        if chat_id in context.bot_data['active_sessions']:
            del context.bot_data['active_sessions'][chat_id]

        result_text = (
            f"📋 [신데렐라 세탁 - 접수 완료 (주문번호 #{order_id})]\n\n"
            f"🏠 고객(동호수): {customer_name}\n"
            f"📅 접수일: {today.strftime('%Y-%m-%d')}\n"
            f"📦 총 수량: {total_photos}벌\n"
            f"🚚 배송 예정일: {delivery_date.strftime('%Y-%m-%d')} (4~5일 소요)\n\n"
            f"-----------------------------------\n"
            f"💬 [고객 전송용 안내 문구 (터치하여 복사하세요)]\n"
            f"```\n"
            f"[신데렐라 세탁 수거/검품 안내]\n"
            f"고객님({customer_name})의 세탁물 총 {total_photos}벌 검품이 완료되었습니다.\n\n"
            f"▪️ 세탁 내역:\n{items_formatted}\n\n"
            f"▪️ 배송 예정일: {delivery_date.strftime('%m월 %d일')} 전후\n\n"
            f"입금이 확인되면 즉시 맞춤 세탁 및 케어가 진행됩니다.\n"
            f"입금 계좌: {BANK_ACCOUNT}\n"
            f"```\n\n"
            f"👇 아래 버튼을 눌러 공장으로 넘기세요!"
        )
        
        try:
            await query.message.delete()
        except Exception:
            pass

        inline_kb = [
            [InlineKeyboardButton(f"🏭 [주문 #{order_id}] 공장에 맡기기", callback_data=f'to_factory_{order_id}')]
        ]
        await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_kb))

    elif data.startswith('to_factory_'):
        o_id = int(data.split('_')[2])
        if o_id in store_orders:
            store_orders[o_id]['status'] = '공장중'
            save_orders(store_orders)
            cust = store_orders[o_id]['customer']
            
            factory_text = (
                f"🏭 [주문 #{o_id} - 공장 진행 중]\n"
                f"🏠 고객: {cust}\n"
                f"세탁물이 공장으로 전달되어 작업 중입니다. 완료되면 아래 [고객 전달 완료]를 눌러주세요!"
            )
            
            try:
                await query.message.delete()
            except Exception:
                pass

            inline_kb = [
                [InlineKeyboardButton(f"🚚 [주문 #{o_id}] 고객 전달 완료", callback_data=f'to_done_{o_id}')]
            ]
            await context.bot.send_message(chat_id=chat_id, text=factory_text, reply_markup=InlineKeyboardMarkup(inline_kb))

    elif data.startswith('to_done_'):
        o_id = int(data.split('_')[2])
        if o_id in store_orders:
            store_orders[o_id]['status'] = '고객전달'
            save_orders(store_orders)
            cust = store_orders[o_id]['customer']
            
            done_text = (
                f"✅ [주문 #{o_id} - 고객 전달 완료]\n"
                f"🏠 고객: {cust}\n"
                f"깔끔하게 세탁되어 고객님께 전달 완료되었습니다! 수고하셨습니다. 🎉"
            )
            
            try:
                await query.message.delete()
            except Exception:
                pass

            await context.bot.send_message(chat_id=chat_id, text=done_text)

    elif data == 'view_status':
        recieved = [f"#{oid} {info['customer']} ({info['count']}벌)" for oid, info in store_orders.items() if info['status'] == '접수완료']
        factory = [f"#{oid} {info['customer']} ({info['count']}벌)" for oid, info in store_orders.items() if info['status'] == '공장중']
        done = [f"#{oid} {info['customer']} ({info['count']}벌)" for oid, info in store_orders.items() if info['status'] == '고객전달']

        status_text = (
            f"📊 [신데렐라 세탁 실시간 현황판]\n\n"
            f"📥 [접수 완료] ({len(recieved)}건)\n" + (("\n".join(f"- {x}" for x in recieved)) if recieved else "- 없음") + "\n\n"
            f"🏭 [공장 진행 중] ({len(factory)}건)\n" + (("\n".join(f"- {x}" for x in factory)) if factory else "- 없음") + "\n\n"
            f"✅ [고객 전달 완료] ({len(done)}건)\n" + (("\n".join(f"- {x}" for x in done)) if done else "- 없음") + "\n\n"
            f"💡 팁: 특정 주문을 삭제하려면 그룹방에 `/delete 주문번호`를 입력하세요! (예: /delete 1)"
        )
        
        status_kb = [
            [InlineKeyboardButton("⬅️ 메인 메뉴로", callback_data='menu_main')]
        ]
        try:
            await query.message.edit_text(status_text, reply_markup=InlineKeyboardMarkup(status_kb))
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=status_text, reply_markup=InlineKeyboardMarkup(status_kb))

    elif data == 'menu_guide':
        keyboard = [
            [InlineKeyboardButton("1. 드라이 냄새 안 난다고 할 때", callback_data='guide_1')],
            [InlineKeyboardButton("2. 오염/피 안 지워졌다고 할 때", callback_data='guide_2')],
            [InlineKeyboardButton("3. 화내며 당장 전화하라고 할 때", callback_data='guide_3')],
            [InlineKeyboardButton("4. 아울렛/오래된 옷 망가졌다 할 때", callback_data='guide_4')],
            [InlineKeyboardButton("⬅️ 메인 메뉴로", callback_data='menu_main')]
        ]
        await query.message.edit_text("💬 [상황별 민원/진상 응대 가이드]\n상황을 선택하세요:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == 'menu_main':
        await query.message.edit_text("📋 [메인 메뉴] 원하시는 기능을 선택해 주세요:", reply_markup=get_main_keyboard())

    elif data == 'menu_checklist':
        text = (
            "🚨 [점장 핵심 운영 체크리스트]\n\n"
            "1️⃣ 오염 & 수선비 분리: 단순 세탁비만 받지 말고 오염/수선비 따로 받기!\n"
            "2️⃣ 선결제 원칙: '입금이 확인되면 세탁이 진행됩니다' 멘트로 후결제 민원 차단!\n"
            "3️⃣ 자연건조 품목 (4~5일+): 패딩, 카시트, 유모차, 운동화는 자연건조 1일 추가!\n"
            "4️⃣ 금요일 자석 전단지: 매주 금요일 오후 4시, 현관문 눈높이 정중앙 부착 (7주 반복)!"
        )
        menu_kb = [[InlineKeyboardButton("⬅️ 메인 메뉴로", callback_data='menu_main')]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(menu_kb))

    elif data.startswith('guide_'):
        guide_dict = {
            'guide_1': "💡 [드라이클리닝 냄새 오해 응대]\n\n📢 \"기름 냄새가 안 나는 것이 가장 안전한 정품 드라이클리닝입니다! 안심하세요.\"",
            'guide_2': "💡 [오염/피 안 지워짐 응대]\n\n📢 \"원단을 보호하는 안전 범위 내에서 최선으로 처리했습니다. 무리한 작업은 탈색을 유발합니다.\"",
            'guide_3': "💡 [화내며 당장 전화하라고 할 때]\n\n📢 즉답 금지! 공장에서 상태를 파악한 후 점장님이 먼저 전화를 걸어 차분히 설명하세요.",
            'guide_4': "💡 [아울렛/오래된 옷 손상 응대]\n\n📢 \"과실이 아니라 시간이 지나며 발생한 원단 삭음 현상입니다.\""
        }
        back_kb = [[InlineKeyboardButton("⬅️ 메인 메뉴로", callback_data='menu_main')]]
        await query.message.edit_text(guide_dict.get(data, "준비 중입니다."), reply_markup=InlineKeyboardMarkup(back_kb))

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("delete", delete_order))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photos))
    
    print("🤖 신데렐라 세탁 점장 비서 봇 정상 가동 시작!")
    app.run_polling()
