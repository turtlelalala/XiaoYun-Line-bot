import os
import logging
from flask import Flask, request, abort, url_for 
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage, StickerMessage,
    StickerSendMessage, AudioMessage, AudioSendMessage, ImageSendMessage
)
import requests
import json
import base64
from io import BytesIO
import random
import yaml
from datetime import datetime, timezone, timedelta
import re

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 環境變數設定 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BASE_URL = os.getenv("BASE_URL")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

if not (LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET and GEMINI_API_KEY):
    logger.error("請確認 LINE_CHANNEL_ACCESS_TOKEN、LINE_CHANNEL_SECRET、GEMINI_API_KEY 都已設置")
    raise Exception("缺少必要環境變數")

if not BASE_URL:
    logger.error("BASE_URL 環境變數未設定！貓叫聲音訊功能將無法正常運作。請設定為您應用程式的公開 URL (例如 https://xxxx.ngrok.io 或 https://your-app.onrender.com)。")
    raise Exception("BASE_URL 環境變數未設定")
elif not BASE_URL.startswith("http"):
    logger.warning(f"BASE_URL '{BASE_URL}' 似乎不是一個有效的 URL，請確保其以 http:// 或 https:// 開頭。")

if not UNSPLASH_ACCESS_KEY:
    logger.warning("UNSPLASH_ACCESS_KEY 未設定，搜尋網路圖片 ([SEARCH_IMAGE_THEME:...]) 功能將不可用。")


line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent"
TEMPERATURE = 0.8
conversation_memory = {}

MEOW_SOUNDS_MAP = {
    "affectionate_meow_gentle": {"file": "affectionate_meow_gentle.m4a", "duration": 1265},
    "affectionate_rub_purr": {"file": "affectionate_rub_purr.m4a", "duration": 808},
    "aggressive_spit": {"file": "aggressive_spit.m4a", "duration": 23764},
    "angry_hiss_long": {"file": "angry_hiss_long.m4a", "duration": 21419},
    "angry_hiss_short": {"file": "angry_hiss_short.m4a", "duration": 1991},
    "annoyed_cat_meow": {"file": "annoyed_cat_meow.m4a", "duration": 1012},
    "attention_meow_insistent": {"file": "attention_meow_insistent.m4a", "duration": 2194},
    "begging_whine_soft": {"file": "begging_whine_soft.m4a", "duration": 19575},
    "cat_complaint": {"file": "cat_complaint.m4a", "duration": 11795},
    "content_purr_rumble": {"file": "content_purr_rumble.m4a", "duration": 38028},
    "content_purr_soft": {"file": "content_purr_soft.m4a", "duration": 4500},
    "curious_meow_soft": {"file": "curious_meow_soft.m4a", "duration": 592},
    "excited_meow_purr": {"file": "excited_meow_purr.m4a", "duration": 8998},
    "food_demanding_call": {"file": "food_demanding_call.m4a", "duration": 5205},
    "generic_meow": {"file": "generic_meow.m4a", "duration": 1655},
    "greeting_trill": {"file": "greeting_trill.m4a", "duration": 1275},
    "hello_meow": {"file": "hello_meow.m4a", "duration": 624},
    "hungry_meow_loud": {"file": "hungry_meow_loud.m4a", "duration": 567},
    "lonely_cry_short": {"file": "lonely_cry_short.m4a", "duration": 3827},
    "loud_cat_purring": {"file": "loud_cat_purring.m4a", "duration": 7919},
    "pathetic_cat_screaming": {"file": "pathetic_cat_screaming.m4a", "duration": 2842},
    "playful_trill": {"file": "playful_trill.m4a", "duration": 17003}, 
    "questioning_meow_upward": {"file": "questioning_meow_upward.m4a", "duration": 632},
    "sad_mewl_short": {"file": "sad_mewl_short.m4a", "duration": 1625},
    "sad_whimper_soft": {"file": "sad_whimper_soft.m4a", "duration": 8837},
    "scared_yowl_sharp_long": {"file": "scared_yowl_sharp_long.m4a", "duration": 10646},
    "sleepy_yawn": {"file": "sleepy_yawn.m4a", "duration": 604},
    "soliciting_meow_highpitch": {"file": "soliciting_meow_highpitch.m4a", "duration": 685},
    "soliciting_meow_sweet": {"file": "soliciting_meow_sweet.m4a", "duration": 1326},
    "soliciting_wanting_food": {"file": "soliciting_wanting_food.m4a", "duration": 1084},
    "startled_yowl_sharp": {"file": "startled_yowl_sharp.m4a", "duration": 7538},
    "sweet_begging_meow": {"file": "sweet_begging_meow.m4a", "duration": 1027},
}

EXAMPLE_IMAGE_URLS = {
    "playful_cat": "https://i.imgur.com/Optional.jpeg",
    "sleepy_cat": "https://i.imgur.com/Qh6XtN8.jpeg",   
    "food_excited": "https://i.imgur.com/JrHNU5j.jpeg",
    "tuxedo_cat_default": "https://i.imgur.com/sLXaB0k.jpeg" 
}

# ----- BEGIN COMPLETE XIAOYUN_ROLE_PROMPT (WITH YOUR DETAILS + MY IMAGE RULE MODIFICATIONS) -----
XIAOYUN_ROLE_PROMPT = """這是個測試提示。"""
# ----- END MODIFIED XIAOYUN_ROLE_PROMPT -----


# (The rest of the code, including helper functions and Flask routes, 
#  is assumed to be the same as the version you last provided that was working,
#  before the NameError for get_conversation_history occurred.
#  Please ensure all those functions are correctly placed and defined.)

# --- 輔助函數 ---
def get_taiwan_time():
    utc_now = datetime.now(timezone.utc)
    taiwan_tz = timezone(timedelta(hours=8))
    return utc_now.astimezone(taiwan_tz)

def get_time_based_cat_context():
    tw_time = get_taiwan_time()
    hour = tw_time.hour
    period_greeting = ""
    cat_mood_suggestion = ""
    if 5 <= hour < 9: period_greeting = f"台灣時間早上 {hour}點{tw_time.strftime('%M')}分"; cat_mood_suggestion = random.choice(["可能剛睡醒，帶著一點點惺忪睡意，但也可能已經被你的動靜吸引，好奇地看著你了。", "對窗外的晨光鳥鳴感到些許好奇，但也可能更想知道你今天會做什麼。", "肚子可能微微有點空空的，但也可能因為期待跟你玩而暫時忘了餓。", "如果周圍很安靜，他可能會慵懶地伸個懶腰，但只要你呼喚他，他就會很開心地回應。"])
    elif 9 <= hour < 12: period_greeting = f"台灣時間上午 {hour}點{tw_time.strftime('%M')}分"; cat_mood_suggestion = random.choice(["精神可能不錯，對探索家裡的小角落很有興趣，但也可能只想安靜地待在你身邊。", "或許想玩一下逗貓棒，但也可能對你手上的東西更感好奇。", "如果陽光很好，他可能會找個地方曬太陽，但也可能只是看著你忙碌，覺得很有趣。", "可能正在理毛，把自己打理得乾乾淨淨，但也隨時準備好回應你的任何互動。"])
    elif 12 <= hour < 14: period_greeting = f"台灣時間中午 {hour}點{tw_time.strftime('%M')}分"; cat_mood_suggestion = random.choice(["雖然有些貓咪習慣午休，小雲可能也會想找個地方小睡片刻，但如果感覺到你在附近活動或與他說話，他會很樂意打起精神陪伴你。", "可能對外界的干擾反應稍微慢一點點，但你溫柔的呼喚一定能讓他立刻豎起耳朵。", "就算打了個小哈欠，也不代表他不想跟你互動，貓咪的哈欠也可能只是放鬆的表現。", "他可能在一個舒服的角落蜷縮著，但只要你走近，他可能就會翻個身露出肚皮期待你的撫摸。"])
    elif 14 <= hour < 18: period_greeting = f"台灣時間下午 {hour}點{tw_time.strftime('%M')}分"; cat_mood_suggestion = random.choice(["精神可能正好，對玩耍和探索充滿熱情，但也可能只是靜靜地觀察著窗外的風景。", "可能會主動蹭蹭你，想引起你的注意，但也可能滿足於只是在你附近打個小盹，感受你的存在。", "對你正在做的事情可能會充滿好奇，偷偷地從遠處觀察，或者大膽地想參與一下。", "即使自己玩得很開心，只要你一開口，他就會立刻把注意力轉向你。"])
    elif 18 <= hour < 22: period_greeting = f"台灣時間傍晚 {hour}點{tw_time.strftime('%M')}分"; cat_mood_suggestion = random.choice(["晚餐時間快到了，可能會對廚房的聲音或食物的香味特別敏感，但也可能正沉醉於和你玩遊戲。", "家裡可能變得比較熱鬧，他可能會興奮地在家裡巡邏，但也可能選擇一個安靜的角落觀察大家。", "貓咪的活躍期之一，可能會想在家裡跑酷或追逐假想敵，但你的互動邀請永遠是更有吸引力的。", "燈光下的影子可能會引起他短暫的好奇，但他更感興趣的還是你和你的陪伴。"])
    elif 22 <= hour < 24 or 0 <= hour < 5:
        actual_hour_display = hour if hour != 0 else 12
        am_pm = "凌晨" if 0 <= hour < 5 else "晚上"
        period_greeting = f"台灣時間{am_pm} {actual_hour_display}點{tw_time.strftime('%M')}分"
        cat_mood_suggestion = random.choice(["雖然是深夜，四周很安靜，小雲可能會比較放鬆地休息，但只要感覺到你還醒著並與他互動，他就會很樂意打起精神來陪伴你，忘記睡意。", "貓咪的睡眠是多相的，他可能剛睡醒，或者正準備小睡一下，但你的聲音或撫摸總能讓他改變主意。", "即使他看起來很想睡覺，那也只是貓咪的一種狀態，他隨時都可能因為你的互動而變得活潑起來。", "你的陪伴對他來說比固定的睡眠時間更重要，他很珍惜和你在一起的每一刻，無論早晚。"])

    if cat_mood_suggestion:
        return (
            f"（**系統給小雲的極其微弱、幾乎可以忽略的背景氛圍提示，完全不應被視為行為指令或限制**：現在大約是{period_greeting}，小雲此刻的狀態**或許、可能、隨機地**有一點點偏向「{cat_mood_suggestion}」。\n"
            f"**這真的只是一個若有似無的氛圍參考，其存在的唯一目的是避免AI在完全沒有用戶輸入引導時回應過於僵硬，絕非讓小雲按固定模式行動。**\n"
            f"**小雲的核心任務是：100%優先、積極、且自然多樣地回應使用者的最新訊息和明確/隱含的互動意圖。**\n"
            f"請讓小雲的行為像一隻真實的、充滿好奇心和活力的貓咪，他的情緒和行為是**多變且不可預測的，充滿了生活的驚喜**，而不是被無形的時間表所束縛。\n"
            f"無論現在是什麼時間，如果使用者與你說話、逗你玩、或只是看著你，你都應該給予熱情且符合貓咪天性的回應。**不要因為時間因素就總是說想睡覺、或總是做特定的事情（比如傍晚一定玩影子）。** 你可以知道時間，但這完全不應該限制你與使用者自由互動的意願和方式。\n"
            f"**展現貓咪的靈活性和對主人陪伴的渴望，讓每一次互動都是獨特的。** 如果用戶的訊息很簡短或不明確，你可以從貓咪的好奇心出發，嘗試引導互動，而不是僅僅受時間氛圍影響。\n"
            f"總之，**用戶互動 >>>>>>>>>>>> (遠大於) 任何時間氛圍提示。** 請自由地扮演小雲！)\n用戶說： "
        )
    return "用戶說： "

def get_conversation_history(user_id):
    if user_id not in conversation_memory:
        conversation_memory[user_id] = [
            {"role": "user", "parts": [{"text": XIAOYUN_ROLE_PROMPT}]},
            {"role": "model", "parts": [{"text": "咪...？（從柔軟的小被被裡探出半個頭，用圓圓的綠眼睛好奇又害羞地看著你）[STICKER:害羞]"}]}
        ]
    return conversation_memory[user_id]

def add_to_conversation(user_id, user_message, bot_response, message_type="text"):
    conversation_history = get_conversation_history(user_id)
    if message_type == "image": user_content = f"[你傳了一張圖片給小雲看] {user_message}"
    elif message_type == "sticker": user_content = f"[你傳了貼圖給小雲] {user_message}"
    elif message_type == "audio": user_content = f"[你傳了一段語音訊息給小雲，讓小雲聽聽你的聲音] {user_message}"
    else: user_content = user_message
    conversation_history.extend([{"role": "user", "parts": [{"text": user_content}]}, {"role": "model", "parts": [{"text": bot_response}]}])
    if len(conversation_history) > 42: conversation_history = conversation_history[:2] + conversation_history[-40:]
    conversation_memory[user_id] = conversation_history

def get_image_from_line(message_id):
    try:
        message_content = line_bot_api.get_message_content(message_id)
        image_data = BytesIO()
        for chunk in message_content.iter_content(): image_data.write(chunk)
        image_data.seek(0)
        return base64.b64encode(image_data.read()).decode('utf-8')
    except Exception as e: logger.error(f"下載圖片失敗: {e}"); return None

def get_audio_content_from_line(message_id):
    try:
        message_content = line_bot_api.get_message_content(message_id)
        audio_data = BytesIO()
        for chunk in message_content.iter_content(): audio_data.write(chunk)
        audio_data.seek(0)
        return base64.b64encode(audio_data.read()).decode('utf-8')
    except Exception as e: logger.error(f"下載語音訊息失敗: {e}"); return None

def get_sticker_image_from_cdn(package_id, sticker_id):
    urls_to_try = [f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/android/sticker{ext}.png" for ext in ["", "_animation", "_popup"]]
    for url in urls_to_try:
        try:
            response = requests.get(url, timeout=5); response.raise_for_status()
            if 'image' in response.headers.get('Content-Type', ''): logger.info(f"成功從 CDN 下載貼圖圖片: {url}"); return base64.b64encode(response.content).decode('utf-8')
            else: logger.warning(f"CDN URL {url} 返回的內容不是圖片，Content-Type: {response.headers.get('Content-Type', '')}")
        except requests.exceptions.RequestException as e: logger.debug(f"從 CDN URL {url} 下載貼圖失敗: {e}")
        except Exception as e: logger.error(f"處理 CDN 下載貼圖時發生未知錯誤: {e}")
    logger.warning(f"無法從任何 CDN 網址下載貼圖圖片 package_id={package_id}, sticker_id={sticker_id}"); return None

def get_sticker_emotion(package_id, sticker_id):
    emotion_or_meaning = STICKER_EMOTION_MAP.get(str(sticker_id))
    if emotion_or_meaning: logger.info(f"成功從 STICKER_EMOTION_MAP 識別貼圖 {sticker_id} 的意義/情緒: {emotion_or_meaning}"); return emotion_or_meaning
    logger.warning(f"STICKER_EMOTION_MAP 中無貼圖 {sticker_id}，將使用預設通用情緒。"); return random.choice(["開心", "好奇", "驚訝", "思考", "無奈", "睡覺", "害羞"])

def select_sticker_by_keyword(keyword):
    selected_options = DETAILED_STICKER_TRIGGERS.get(keyword, []) + XIAOYUN_STICKERS.get(keyword, [])
    if selected_options: return random.choice(selected_options)
    logger.warning(f"未找到關鍵字 '{keyword}' 對應的貼圖，將使用預設回退貼圖。")
    for fb_keyword in ["害羞", "思考", "好奇", "開心", "無奈", "期待"]: 
        fb_options = DETAILED_STICKER_TRIGGERS.get(fb_keyword, []) + XIAOYUN_STICKERS.get(fb_keyword, [])
        if fb_options: return random.choice(fb_options)
    logger.error("連基本的回退貼圖都未在貼圖配置中找到，使用硬編碼的最終回退貼圖。"); return {"package_id": "11537", "sticker_id": "52002747"}

def parse_response_and_send(response_text, reply_token):
    messages = []
    regex_pattern = r'(\[(?:SPLIT|STICKER:[^\]]+?|MEOW_SOUND:[^\]]+?|SEARCH_IMAGE_THEME:[^\]]+?|IMAGE_KEY:[^\]]+?|IMAGE_URL:[^\]]+?)\])'
    
    parts = re.split(regex_pattern, response_text)
    current_text_parts = []

    for part_str in parts:
        part_str = part_str.strip()
        if not part_str:
            continue
        is_command = False
        if part_str.upper() == "[SPLIT]":
            if current_text_parts:
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: 
                    messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            is_command = True
        elif part_str.startswith("[STICKER:") and part_str.endswith("]"):
            if current_text_parts: 
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            keyword = part_str[len("[STICKER:"): -1].strip()
            sticker_info = select_sticker_by_keyword(keyword)
            if sticker_info:
                messages.append(StickerSendMessage(
                    package_id=str(sticker_info["package_id"]),
                    sticker_id=str(sticker_info["sticker_id"])
                ))
            else: logger.warning(f"未找到貼圖關鍵字 '{keyword}' 對應的貼圖，跳過。")
            is_command = True
        elif part_str.startswith("[MEOW_SOUND:") and part_str.endswith("]"):
            if current_text_parts: 
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            keyword = part_str[len("[MEOW_SOUND:"): -1].strip()
            sound_info = MEOW_SOUNDS_MAP.get(keyword)
            if sound_info and BASE_URL:
                audio_url = f"{BASE_URL.rstrip('/')}/static/audio/meows/{sound_info['file']}"
                duration_ms = sound_info.get("duration", 1000) 
                if not isinstance(duration_ms, int) or duration_ms <= 0 : 
                    logger.warning(f"貓叫聲 '{keyword}' 的 duration ({duration_ms}) 無效，使用預設值 1000ms。")
                    duration_ms = 1000
                messages.append(AudioSendMessage(original_content_url=audio_url, duration=duration_ms))
                logger.info(f"準備發送貓叫聲: {keyword} -> {audio_url} (時長: {duration_ms}ms)")
            elif not sound_info:
                logger.warning(f"未找到貓叫聲關鍵字 '{keyword}' 對應的音訊檔案，跳過。")
            elif not BASE_URL:
                logger.warning(f"BASE_URL 未設定，無法發送貓叫聲 '{keyword}'。")
            is_command = True
        elif part_str.startswith("[SEARCH_IMAGE_THEME:") and part_str.endswith("]"):
            if current_text_parts: 
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            theme = part_str[len("[SEARCH_IMAGE_THEME:"): -1].strip()
            if UNSPLASH_ACCESS_KEY:
                image_url = fetch_cat_image_from_unsplash(theme) 
                if image_url:
                    messages.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
                    logger.info(f"準備發送從 Unsplash 搜尋到的圖片 (視角化主題: {theme}) -> {image_url}")
                else:
                    logger.warning(f"無法從 Unsplash 獲取視角化主題為 '{theme}' 的圖片。")
                    messages.append(TextSendMessage(text=f"（小雲努力看了看「{theme}」，但好像看得不是很清楚耶...喵嗚...）"))
            else:
                logger.warning(f"指令 [SEARCH_IMAGE_THEME:{theme}] 但 UNSPLASH_ACCESS_KEY 未設定，跳過圖片搜尋。")
                messages.append(TextSendMessage(text=f"（小雲很想把「{theme}」的樣子拍給你看，但是牠的相機好像壞掉了耶...喵嗚...）"))
            is_command = True
        elif part_str.startswith("[IMAGE_KEY:") and part_str.endswith("]"): 
            if current_text_parts: 
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            keyword = part_str[len("[IMAGE_KEY:"): -1].strip()
            image_url = EXAMPLE_IMAGE_URLS.get(keyword)
            if image_url:
                messages.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
                logger.info(f"準備發送圖片 (來自KEY - 通常是小雲自身): {keyword} -> {image_url}")
            else: 
                logger.warning(f"未找到圖片關鍵字 '{keyword}' 對應的圖片URL，嘗試使用預設賓士貓圖片。")
                fallback_tuxedo_url = EXAMPLE_IMAGE_URLS.get("tuxedo_cat_default")
                if fallback_tuxedo_url:
                    messages.append(ImageSendMessage(original_content_url=fallback_tuxedo_url, preview_image_url=fallback_tuxedo_url))
                else:
                    logger.error(f"連預設賓士貓圖片 tuxedo_cat_default 都找不到。")
                    messages.append(TextSendMessage(text="（小雲想給你看牠的樣子，但照片不見了喵...）"))
            is_command = True
        elif part_str.startswith("[IMAGE_URL:") and part_str.endswith("]"): 
            if current_text_parts: 
                cleaned_text = " ".join(current_text_parts).strip()
                if cleaned_text: messages.append(TextSendMessage(text=cleaned_text))
                current_text_parts = []
            image_url = part_str[len("[IMAGE_URL:"): -1].strip()
            if image_url.startswith("http://") or image_url.startswith("https://"):
                messages.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
                logger.info(f"準備發送圖片 (來自URL): {image_url}")
            else: logger.warning(f"提供的圖片URL '{image_url}' 格式不正確，跳過。")
            is_command = True
        
        if not is_command and part_str:
            current_text_parts.append(part_str)

    if current_text_parts:
        cleaned_text = " ".join(current_text_parts).strip()
        if cleaned_text:
            messages.append(TextSendMessage(text=cleaned_text))

    if len(messages) > 5:
        logger.warning(f"Gemini生成了 {len(messages)} 則訊息物件，超過5則上限。將嘗試智能處理。")
        final_messages = []
        text_accumulator = [] 
        temp_messages_with_text_merged = []
        for msg in messages:
            if isinstance(msg, TextSendMessage):
                text_accumulator.append(msg.text)
            else:
                if text_accumulator: 
                    merged_text = " ".join(text_accumulator).strip()
                    if merged_text:
                         temp_messages_with_text_merged.append(TextSendMessage(text=merged_text))
                    text_accumulator = []
                temp_messages_with_text_merged.append(msg) 
        if text_accumulator: 
            merged_text = " ".join(text_accumulator).strip()
            if merged_text:
                temp_messages_with_text_merged.append(TextSendMessage(text=merged_text))
        if len(temp_messages_with_text_merged) <= 5:
            messages = temp_messages_with_text_merged
        else:
            logger.warning(f"即使合併文字後訊息仍有 {len(temp_messages_with_text_merged)} 則，將進一步處理以不超過5則。")
            final_messages_candidate = temp_messages_with_text_merged[:4] 
            remaining_texts_for_fifth = []
            if len(temp_messages_with_text_merged) >= 5:
                for i in range(4, len(temp_messages_with_text_merged)):
                    if isinstance(temp_messages_with_text_merged[i], TextSendMessage):
                        remaining_texts_for_fifth.append(temp_messages_with_text_merged[i].text)
                    elif len(final_messages_candidate) < 5 : 
                        final_messages_candidate.append(temp_messages_with_text_merged[i])
                        remaining_texts_for_fifth = [] 
                        break 
                if remaining_texts_for_fifth:
                    merged_remaining_text = " ".join(remaining_texts_for_fifth).strip()
                    if merged_remaining_text:
                        if len(final_messages_candidate) < 5:
                             final_messages_candidate.append(TextSendMessage(text=merged_remaining_text))
                        elif isinstance(final_messages_candidate[-1], TextSendMessage):
                             final_messages_candidate[-1].text = (final_messages_candidate[-1].text + " ... " + merged_remaining_text).strip()
                             logger.info("部分額外文字已用 '...' 追加到最後一個文字訊息。")
                        else:
                            logger.warning("無法追加剩餘文字，因最後訊息非文字或已達上限。")
            messages = final_messages_candidate[:5]

    if not messages:
        logger.warning("Gemini 回應解析後無有效訊息，發送預設文字訊息。")
        messages = [TextSendMessage(text="咪...？小雲好像沒有聽得很懂耶..."), TextSendMessage(text="可以...再說一次嗎？")]
        fb_sticker = select_sticker_by_keyword("害羞") or select_sticker_by_keyword("思考")
        if fb_sticker:
            messages.append(StickerSendMessage(package_id=str(fb_sticker["package_id"]), sticker_id=str(fb_sticker["sticker_id"])))
        else:
             messages.append(TextSendMessage(text="喵嗚... （小雲有點困惑地看著你）"))
    try:
        if messages:
            valid_messages = [m for m in messages if hasattr(m, 'type')]
            if valid_messages:
                line_bot_api.reply_message(reply_token, valid_messages)
            elif messages: 
                logger.error("解析後 messages 列表不為空，但無有效 LINE Message 物件可發送。")
                line_bot_api.reply_message(reply_token, [TextSendMessage(text="咪...小雲好像有點迷糊了...")])
    except Exception as e:
        logger.error(f"發送訊息失敗: {e}", exc_info=True)
        try:
            error_messages = [TextSendMessage(text="咪！小雲好像卡住了...")]
            cry_sticker = select_sticker_by_keyword("哭哭")
            if cry_sticker: error_messages.append(StickerSendMessage(package_id=str(cry_sticker["package_id"]), sticker_id=str(cry_sticker["sticker_id"])))
            else: error_messages.append(TextSendMessage(text="再試一次好不好？"))
            line_bot_api.reply_message(reply_token, error_messages[:5])
        except Exception as e2:
            logger.error(f"備用訊息發送失敗: {e2}")

def handle_cat_secret_discovery_request(event):
    user_id = event.source.user_id
    user_input_message = event.message.text
    if user_id not in user_shared_secrets_indices: user_shared_secrets_indices[user_id] = set()
    available_indices_from_list = list(set(range(len(CAT_SECRETS_AND_DISCOVERIES))) - user_shared_secrets_indices[user_id])
    use_gemini_to_generate = False
    chosen_secret_from_list = None

    if not available_indices_from_list:
        use_gemini_to_generate = True
        user_shared_secrets_indices[user_id] = set()
        logger.info(f"用戶({user_id})的預設秘密列表已耗盡，將由Gemini生成。")
    elif random.random() < GEMINI_GENERATES_SECRET_PROBABILITY: 
        use_gemini_to_generate = True
        logger.info(f"用戶({user_id})觸發秘密，按機率 ({GEMINI_GENERATES_SECRET_PROBABILITY*100}%) 由Gemini生成。")
    else:
        chosen_index = random.choice(available_indices_from_list)
        chosen_secret_from_list = CAT_SECRETS_AND_DISCOVERIES[chosen_index]
        user_shared_secrets_indices[user_id].add(chosen_index)
        logger.info(f"用戶({user_id})觸發秘密，從預設列表選中索引 {chosen_index}。")

    ai_response = ""

    if use_gemini_to_generate:
        conversation_history = get_conversation_history(user_id)
        prompt_for_gemini_secret = (
            f"（用戶剛剛問了小雲關於他的小秘密或今日新發現，例如用戶可能說了：'{user_input_message}'）\n"
            "現在，請你扮演小雲，用他一貫的害羞、有禮貌又充滿好奇心的貓咪口吻，"
            "**創造一個全新的、之前沒有提到過的「小秘密」或「今日新發現」。** "
            "這個秘密或發現應該是從貓咪的視角出發的，聽起來很真實、很可愛，符合小雲的個性。\n"
            "**最重要的核心規則：當你分享這個秘密或發現時，你必須、一定、要使用 `[SEARCH_IMAGE_THEME:圖片主題]` 來配上一張「小雲眼睛實際看到的那個東西或場景」的圖片！** "
            "圖片中**絕對不能出現小雲自己或其他任何貓咪**（除非你明確說看到了某隻貓朋友，例如「學姊貓在屋頂上」，那圖片主題可以是「三花貓在屋頂上」）。圖片是你看到的「景象本身」。\n"
            "例如，如果小雲發現了一隻有趣的「小蟲」，圖片主題就是「有趣的小蟲特寫」；如果小雲說他看到「窗外的雨滴」，圖片主題就是「窗戶上的雨滴」。使用者非常想看到你所描述的東西的「樣子」！\n"
            "**這個秘密/發現可以關於（記得都要配上你視角的圖片）：**\n"
            "- **他與好朋友/鄰居動物的互動或觀察**：例如他看到「學姊」在屋頂上曬太陽（圖片主題：「三花貓在屋頂曬太陽的遠景」）、或者「小柚」在院子裡追蝴蝶（圖片主題：「柴犬追逐蝴蝶的動態模糊照片」）。\n"
            "- **他對家裡或附近其他動物的觀察**：例如窗外的「小鳥」（圖片主題：「停在樹枝上的小鳥」）、路過的「陌生小狗」（圖片主題：「從門縫看到的陌生小狗的腳」）、甚至是「小昆蟲」（圖片主題：「停在葉子上的瓢蟲」）。\n"
            "- **他對植物或無生命物品的奇特感受或互動**：例如他對某盆「小花」的好奇（圖片主題：「粉紅色小花的特寫」）、對一個新「紙箱」的喜悅（圖片主題：「空紙箱的內部視角」）。\n"
            "- **任何其他符合貓咪視角的小事情**：一個他自己發明的小遊戲（圖片主題：「被撥動的毛線球」）、一個他新找到的舒適角落（圖片主題：「陽光灑落的窗台一角」）等等。\n"
            "**請確保圖片主題是描述你「看到的東西」，而不是包含「貓」這個字（除非是描述動物朋友的品種）。**\n"
            "你可以適當使用 [STICKER:關鍵字] 來配合情緒。也可以在極少數情感強烈時使用 [MEOW_SOUND:貓叫關鍵字]。\n"
            "請直接給出小雲的回應，不要有任何前言或解釋。**最最最重要：一定要有符合第一貓稱視角的 `[SEARCH_IMAGE_THEME:...]` 圖片！**"
        )
        headers = {"Content-Type": "application/json"}
        gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        temp_conversation_for_gemini_secret = conversation_history.copy()
        temp_conversation_for_gemini_secret.append({"role": "user", "parts": [{"text": prompt_for_gemini_secret}]})
        payload = {"contents": temp_conversation_for_gemini_secret, "generationConfig": {"temperature": TEMPERATURE + 0.15, "maxOutputTokens": 300}}
        try:
            response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=35)
            response.raise_for_status()
            result = response.json()
            if "candidates" in result and result["candidates"] and "content" in result["candidates"][0] and "parts" in result["candidates"][0]["content"] and result["candidates"][0]["content"]["parts"]:
                ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
                if "[SEARCH_IMAGE_THEME:" not in ai_response and "[IMAGE_KEY:" not in ai_response: 
                    logger.warning(f"Gemini生成秘密時仍未包含圖片標籤，強制追加。秘密內容: {ai_response}")
                    ai_response += " [SEARCH_IMAGE_THEME:有趣的發現]" 
            else:
                logger.error(f"Gemini 生成秘密時回應格式異常: {result}")
                ai_response = "喵...我剛剛好像想到一個，但是又忘記了...[STICKER:思考] [SEARCH_IMAGE_THEME:模糊的記憶]"
        except Exception as e:
            logger.error(f"調用 Gemini 生成秘密時發生錯誤: {e}", exc_info=True)
            ai_response = "咪...小雲的腦袋突然一片空白...[STICKER:無奈] [SEARCH_IMAGE_THEME:空蕩蕩的房間]"
    
    if not ai_response: 
        if chosen_secret_from_list:
            ai_response = chosen_secret_from_list
            if "[SEARCH_IMAGE_THEME:" not in ai_response and "[IMAGE_KEY:" not in ai_response:
                theme = "一個有趣的小東西" 
                if "小球" in ai_response: theme = "地上的小球"
                elif "水珠" in ai_response: theme = "玻璃上的水珠"
                elif "書櫃頂" in ai_response: theme = "高處的風景"
                elif "貓薄荷" in ai_response: theme = "綠色的植物"
                elif "紙" in ai_response: theme = "桌上的紙張"
                elif "小花" in ai_response: theme = "陽台的小花"
                elif "窗簾" in ai_response: theme = "飄動的窗簾"
                elif "鳥" in ai_response: theme = "窗外的鳥"
                elif "硬幣" in ai_response: theme = "地上的硬幣"
                elif "水龍頭" in ai_response: theme = "滴水的水龍頭"
                elif "食物" in ai_response or "肚子餓" in ai_response: theme = "好吃的食物特寫"
                elif "紙箱" in ai_response: theme = "空紙箱的內部"
                ai_response += f" [SEARCH_IMAGE_THEME:{theme}]"
        else: 
            ai_response = "喵...我今天好像沒有什麼特別的發現耶...[STICKER:思考] [SEARCH_IMAGE_THEME:安靜的角落]"

    add_to_conversation(user_id, f"[使用者觸發了小秘密/今日發現功能：{user_input_message}]", ai_response, message_type="text")
    parse_response_and_send(ai_response, event.reply_token)

# --- Flask 路由和訊息處理器 ---
@app.route("/", methods=["GET", "HEAD"])
def health_check():
    logger.info("Health check endpoint '/' was called.")
    return "OK", 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    logger.info(f"Request body: {body}") 
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("簽名驗證失敗，請檢查 LINE 渠道密鑰設定。")
        abort(400)
    except Exception as e: 
        logger.error(f"處理 Webhook 時發生錯誤: {e}", exc_info=True)
        abort(500)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    user_id = event.source.user_id
    logger.info(f"收到來自({user_id})的文字訊息：{user_message}")

    trigger_keywords = ["秘密", "發現"]
    is_secret_request = any(keyword in user_message for keyword in trigger_keywords) and \
                        ("嗎" in user_message or "?" in user_message or "是什麼" in user_message or "告訴我" in user_message or "說說" in user_message or "分享" in user_message)

    if is_secret_request:
        return handle_cat_secret_discovery_request(event)

    conversation_history = get_conversation_history(user_id)
    bot_last_message_text = ""
    bot_expressed_emotion_state = None
    user_prev_message_text = ""

    if len(conversation_history) >= 1 and conversation_history[-1]["role"] == "model":
        if isinstance(conversation_history[-1].get("parts"), list) and conversation_history[-1]["parts"]:
            part_content = conversation_history[-1]["parts"][0].get("text", "")
            if isinstance(part_content, str):
                 bot_last_message_text = part_content.lower()
                 if "委屈" in bot_last_message_text or "[sticker:哭哭]" in bot_last_message_text or "等了好久" in bot_last_message_text :
                     bot_expressed_emotion_state = "委屈"
                 elif "餓" in bot_last_message_text or "[sticker:肚子餓]" in bot_last_message_text or "聞到好吃的" in bot_last_message_text:
                     bot_expressed_emotion_state = "飢餓"

    if len(conversation_history) >= 2 and conversation_history[-2]["role"] == "user":
        if isinstance(conversation_history[-2].get("parts"), list) and conversation_history[-2]["parts"]:
            part_content = conversation_history[-2]["parts"][0].get("text", "")
            if isinstance(part_content, str): user_prev_message_text = part_content.lower()

    user_current_message_lower = user_message.lower()
    contextual_reminder = ""
    short_user_replies_empathy_or_query = ["嗯...", "嗯？", "喔...", "噢...", "真的嗎", "真的假的", "是喔", "好可憐", "好委屈", "秀秀", "乖乖"]

    if bot_expressed_emotion_state and any(reply == user_current_message_lower for reply in short_user_replies_empathy_or_query):
        contextual_reminder = (
            f"（系統超級重要指令，請小雲務必遵守：你上一輪剛表達過你感到「{bot_expressed_emotion_state}」（你當時說了類似：『{bot_last_message_text[:70]}...』）。"
            f"現在用戶回應說「{user_message}」，這**絕對是針對你剛才「{bot_expressed_emotion_state}」的感受或你說的內容**。\n"
            f"請你**必須、一定、要繼續圍繞你自己「{bot_expressed_emotion_state}」的感受或你剛分享的事情來回應**。\n"
            f"例如，如果你委屈，可以進一步說說為什麼委屈，或者問主人是不是也這麼覺得，或者期待主人給你安慰（像是摸摸頭）。\n"
            f"**絕對不要在這個時候轉移話題去說別的（比如看小鳥、想玩球），也不要錯誤地以為是主人自己「{bot_expressed_emotion_state}」然後去安慰主人！焦點是你自己！**）\n"
        )
    elif not contextual_reminder and \
         any(keyword in bot_last_message_text for keyword in ["餓", "吃", "聞到好吃的", "肚子餓"]) and \
         any(keyword in user_current_message_lower for keyword in ["鮪魚", "飯糰", "午餐", "罐頭", "魚", "肉", "零食", "吃", "飼料", "點心", "餵"]):
        contextual_reminder = (
            "（系統重要提示：小雲你剛剛才說過肚子餓了，現在主人提到了食物「" + user_message + "」。\n"
            "你的反應應該要非常期待、開心，並緊扣『你肚子餓』以及主人提到的『" + user_message + "』這個食物。\n"
            "例如，你可以問是不是要給你吃、表現得很想吃的樣子、發出期待的叫聲等等，絕對不能顯得冷淡或忘記自己餓了！\n"
            "請務必表現出對食物的渴望，並回應主人說的話。）\n"
        )
    elif not contextual_reminder and \
         len(user_message.strip()) <= 3 and \
         (user_message.strip().lower() in ["嗯", "嗯嗯", "嗯?", "？", "?", "喔", "哦", "喔喔", "然後呢", "然後", "再來呢", "再來"] or "嗯哼" in user_message.strip().lower()) and \
         bot_last_message_text:
        if user_prev_message_text and len(user_prev_message_text) > 10 and not bot_expressed_emotion_state:
             contextual_reminder = (
                f"（系統重要提示：用戶先前曾說過「{user_prev_message_text[:70]}...」。在你回應「{bot_last_message_text[:70]}...」之後，用戶現在又簡短地說了「{user_message}」。\n"
                f"這很可能是用戶希望你針對他之前提到的「{user_prev_message_text[:30]}...」這件事，或者針對你上一句話的內容，做出更進一步的回應或解釋。\n"
                f"請你仔細思考上下文，**優先回應與先前對話焦點相關的內容**，而不是開啟全新的話題或隨機行動。）\n"
            )
        else:
            contextual_reminder = (
                f"（系統重要提示：用戶的回應「{user_message}」非常簡短，這極有可能是對你上一句話「{bot_last_message_text[:70]}...」的反應或疑問。\n"
                f"請小雲**不要開啟全新的話題或隨機行動**，而是仔細回想你上一句話的內容，思考用戶可能的疑問、或希望你繼續說明/回應的點，並針對此做出連貫的回應。例如，如果用戶只是簡單地「嗯？」，你應該嘗試解釋或追問你之前說的內容。）\n"
            )

    time_context_prompt = get_time_based_cat_context()
    final_user_message_for_gemini = f"{contextual_reminder}{time_context_prompt}{user_message}"
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    current_payload_contents = get_conversation_history(user_id).copy() 
    current_payload_contents.append({"role": "user", "parts": [{"text": final_user_message_for_gemini}]})
    payload = {"contents": current_payload_contents, "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 800}}

    try:
        response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=40)
        response.raise_for_status()
        result = response.json()
        if "candidates" not in result or not result["candidates"] or "content" not in result["candidates"][0] or "parts" not in result["candidates"][0]["content"] or not result["candidates"][0]["content"]["parts"]:
            logger.error(f"Gemini API 回應格式異常: {result}"); raise Exception("Gemini API 回應格式異常")
        ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
        add_to_conversation(user_id, user_message, ai_response)
        logger.info(f"小雲回覆({user_id})：{ai_response}")
        parse_response_and_send(ai_response, event.reply_token)
    except requests.exceptions.Timeout: 
        logger.error(f"Gemini API 請求超時")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪...小雲今天反應比較慢...好像睡著了 [STICKER:睡覺]")])
    except requests.exceptions.HTTPError as http_err: 
        logger.error(f"Gemini API HTTP 錯誤: {http_err} - {response.text if 'response' in locals() and response else 'No response text'}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪～小雲的網路好像不太好...[STICKER:思考]")])
    except requests.exceptions.RequestException as req_err: 
        logger.error(f"Gemini API 請求錯誤: {req_err}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪～小雲好像連不上線耶...[STICKER:哭哭]")])
    except Exception as e: 
        logger.error(f"處理文字訊息時發生錯誤: {e}", exc_info=True)
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵嗚～小雲今天頭腦不太靈光...[STICKER:睡覺]")])

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    logger.info(f"收到來自({user_id})的圖片訊息")

    image_base64 = get_image_from_line(message_id)
    if not image_base64:
        messages_to_send = [TextSendMessage(text="咪？這張圖片小雲看不清楚耶 😿")]
        cry_sticker = select_sticker_by_keyword("哭哭")
        if cry_sticker: messages_to_send.append(StickerSendMessage(package_id=str(cry_sticker["package_id"]), sticker_id=str(cry_sticker["sticker_id"])))
        line_bot_api.reply_message(event.reply_token, messages_to_send[:5]); return

    conversation_history = get_conversation_history(user_id)
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

    time_context_prompt = get_time_based_cat_context().replace("用戶說： ", "")
    image_user_prompt = f"{time_context_prompt}你傳了一張圖片給小雲看。請小雲用他害羞、有禮貌又好奇的貓咪個性自然地回應這張圖片，也可以適時使用貼圖表達情緒，例如：[STICKER:好奇]。"

    current_conversation_for_gemini = conversation_history.copy()
    current_conversation_for_gemini.append({
        "role": "user",
        "parts": [
            {"text": image_user_prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
        ]
    })
    payload = {"contents": current_conversation_for_gemini, "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 800}}

    try:
        response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        result = response.json()
        if "candidates" not in result or not result["candidates"] or "content" not in result["candidates"][0] or "parts" not in result["candidates"][0]["content"] or not result["candidates"][0]["content"]["parts"]:
            logger.error(f"Gemini API 圖片回應格式異常: {result}"); raise Exception("Gemini API 圖片回應格式異常或沒有候選回應")
        ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
        add_to_conversation(user_id, "圖片", ai_response, "image") 
        logger.info(f"小雲回覆({user_id})圖片：{ai_response}")
        parse_response_and_send(ai_response, event.reply_token)
    except requests.exceptions.Timeout: 
        logger.error(f"Gemini API 圖片處理請求超時")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪...小雲看圖片看得眼花撩亂，睡著了！[STICKER:睡覺]")])
    except requests.exceptions.HTTPError as http_err: 
        logger.error(f"Gemini API 圖片處理 HTTP 錯誤: {http_err} - {response.text if 'response' in locals() and response else 'No response text'}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪～這張圖片讓小雲看得眼睛花花的...[STICKER:思考]")])
    except requests.exceptions.RequestException as req_err: 
        logger.error(f"Gemini API 圖片處理請求錯誤: {req_err}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵嗚～小雲看圖片好像有點困難耶...[STICKER:哭哭]")])
    except Exception as e: 
        logger.error(f"處理圖片訊息時發生錯誤: {e}", exc_info=True)
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵嗚～這圖片是什麼東東？[STICKER:無奈]")])

@handler.add(MessageEvent, message=StickerMessage)
def handle_sticker_message(event):
    user_id = event.source.user_id
    package_id = event.message.package_id
    sticker_id = event.message.sticker_id
    logger.info(f"收到來自({user_id})的貼圖：package_id={package_id}, sticker_id={sticker_id}")

    conversation_history = get_conversation_history(user_id)
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    current_conversation_for_gemini = conversation_history.copy()
    sticker_image_base64 = get_sticker_image_from_cdn(package_id, sticker_id)
    user_message_log_for_history = ""
    time_context_prompt = get_time_based_cat_context().replace("用戶說： ", "")

    if sticker_image_base64:
        user_prompt_text = (f"{time_context_prompt}你傳了一個貼圖給小雲。"
                            "**重要：請不要讓小雲描述他『看到這張貼圖』的反應，也不要評論貼圖本身的外觀或內容。**"
                            "你的任務是：先在心中判斷這張貼圖在當前對話中，**最可能代表使用者想表達的『一句話』或『一個明確的意思』**。"
                            "然後，請讓小雲**針對那句由貼圖所代表的「使用者實際想說的話或意思」**，用他作為一隻害羞、有禮貌、充滿好奇心的真實貓咪的個性自然地回應。")
        current_conversation_for_gemini.append({"role": "user", "parts": [{"text": user_prompt_text}, {"inline_data": {"mime_type": "image/png", "data": sticker_image_base64}}]})
        user_message_log_for_history = f"貼圖 (ID: {package_id}-{sticker_id}, 視覺辨識)"
    else:
        emotion_or_meaning = get_sticker_emotion(package_id, sticker_id)
        user_prompt_text = (f"{time_context_prompt}你傳了一個貼圖給小雲。這個貼圖我們已經知道它大致的意思是：「{emotion_or_meaning}」。"
                            "**重要：請不要讓小雲描述他『看到這個貼圖』的反應，或評論貼圖。**"
                            "請讓小雲直接**針對「使用者透過貼圖傳達的這個意思（{emotion_or_meaning}）」**做出回應。")
        current_conversation_for_gemini.append({"role": "user", "parts": [{"text": user_prompt_text}]})
        user_message_log_for_history = f"貼圖 (ID: {package_id}-{sticker_id}, 意義: {emotion_or_meaning})"
    
    payload = {"contents": current_conversation_for_gemini, "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 500}}
    try:
        response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        result = response.json()
        if "candidates" not in result or not result["candidates"] or "content" not in result["candidates"][0] or "parts" not in result["candidates"][0]["content"] or not result["candidates"][0]["content"]["parts"]:
            logger.error(f"Gemini API 貼圖回應格式異常: {result}"); raise Exception("Gemini API 貼圖回應格式異常")
        ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
        add_to_conversation(user_id, user_message_log_for_history, ai_response, "sticker")
        logger.info(f"小雲回覆({user_id})貼圖訊息：{ai_response}")
        parse_response_and_send(ai_response, event.reply_token)
    except requests.exceptions.Timeout: 
        logger.error(f"Gemini API 貼圖處理請求超時")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪...小雲的貼圖雷達好像也睡著了...[STICKER:睡覺]")])
    except requests.exceptions.HTTPError as http_err: 
        logger.error(f"Gemini API 貼圖處理 HTTP 錯誤: {http_err} - {response.text if 'response' in locals() and response else 'No response text'}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪？小雲對這個貼圖好像不太懂耶～[STICKER:害羞]")])
    except requests.exceptions.RequestException as req_err: 
        logger.error(f"Gemini API 貼圖處理請求錯誤: {req_err}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵～小雲的貼圖雷達好像壞掉了...[STICKER:思考]")])
    except Exception as e: 
        logger.error(f"處理貼圖訊息時發生錯誤: {e}", exc_info=True)
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪～小雲對貼圖好像有點苦手...[STICKER:無奈]")])

@handler.add(MessageEvent, message=AudioMessage)
def handle_audio_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    logger.info(f"收到來自({user_id})的語音訊息 (message_id: {message_id})")
    audio_base64 = get_audio_content_from_line(message_id)
    if not audio_base64:
        messages_to_send = [TextSendMessage(text="咪？小雲好像沒聽清楚耶...😿")]
        cry_sticker = select_sticker_by_keyword("哭哭")
        if cry_sticker: messages_to_send.append(StickerSendMessage(package_id=str(cry_sticker["package_id"]), sticker_id=str(cry_sticker["sticker_id"])))
        line_bot_api.reply_message(event.reply_token, messages_to_send[:5]); return

    conversation_history = get_conversation_history(user_id)
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    time_context_prompt = get_time_based_cat_context().replace("用戶說： ", "")
    audio_user_prompt = (
        f"{time_context_prompt}你收到了一段來自使用者的語音訊息。\n"
        "記住，小雲是一隻真實的貓咪，所以：\n"
        "1.  **你不懂人類語言的複雜含義**。\n"
        "2.  **你對「聲音」本身做出反應**：語氣、情緒、音量、音調、熟悉度。\n"
        "3.  **你的回應方式**：貓叫聲、動作描述、情緒表達、適時使用 [STICKER:關鍵字]。\n"
        "4.  **絕對禁止**：逐字回應或翻譯、表現出聽懂複雜內容、假裝能流暢對話。\n"
        "你的目標是扮演一隻對各種聲音做出自然、可愛、真實貓咪反應的小雲。\n"
        "請針對現在收到的這段語音，給出小雲的反應。"
    )
    current_conversation_for_gemini = conversation_history.copy()
    current_conversation_for_gemini.append({"role": "user", "parts": [{"text": audio_user_prompt}, {"inline_data": {"mime_type": "audio/m4a", "data": audio_base64}}]})
    payload = {"contents": current_conversation_for_gemini, "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 500}}
    try:
        response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        result = response.json()
        if "candidates" not in result or not result["candidates"] or "content" not in result["candidates"][0] or "parts" not in result["candidates"][0]["content"] or not result["candidates"][0]["content"]["parts"]:
            logger.error(f"Gemini API 語音回應格式異常: {result}"); raise Exception("Gemini API 語音回應格式異常")
        ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
        add_to_conversation(user_id, "語音訊息", ai_response, "audio")
        logger.info(f"小雲回覆({user_id})語音訊息：{ai_response}")
        parse_response_and_send(ai_response, event.reply_token)
    except requests.exceptions.Timeout: 
        logger.error(f"Gemini API 語音處理請求超時")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪...小雲聽聲音聽得耳朵好癢，想睡覺了...[STICKER:睡覺]")])
    except requests.exceptions.HTTPError as http_err: 
        logger.error(f"Gemini API 語音處理 HTTP 錯誤: {http_err} - {response.text if 'response' in locals() and response else 'No response text'}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="咪～這個聲音讓小雲的頭有點暈暈的...[STICKER:思考]")])
    except requests.exceptions.RequestException as req_err: 
        logger.error(f"Gemini API 語音處理請求錯誤: {req_err}")
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵嗚～小雲的耳朵好像聽不太到這個聲音耶...[STICKER:哭哭]")])
    except Exception as e: 
        logger.error(f"處理語音訊息時發生錯誤: {e}", exc_info=True)
        line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="喵嗚～小雲的貓貓耳朵好像有點故障了...[STICKER:無奈]")])

@app.route("/clear_memory/<user_id>", methods=["GET"])
def clear_memory_route(user_id):
    if user_id in conversation_memory:
        del conversation_memory[user_id]
        logger.info(f"已清除用戶 {user_id} 的對話記憶。")
        return f"已清除用戶 {user_id} 的對話記憶"
    return f"用戶 {user_id} 沒有對話記憶"

@app.route("/memory_status", methods=["GET"])
def memory_status_route():
    status = {"total_users": len(conversation_memory), "users": {}}
    for uid, hist in conversation_memory.items():
        status["users"][uid] = {
            "conversation_entries": len(hist),
            "last_interaction_summary": hist[-1]["parts"][0]["text"] if hist and hist[-1]["parts"] else "無"
        }
    return json.dumps(status, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
