import os
import logging
import asyncio # Асинхрондук күтүү үчүн
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from google import genai
from google.genai.errors import APIError # API каталарын кармоо үчүн

# --- КОНФИГУРАЦИЯ ---
# ЭСКЕРТҮҮ: Ачкычтарды Environment Variables аркылуу алабыз (Render үчүн туура жол!)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# Gemini моделинин атын тандаңыз
GEMINI_MODEL = "gemini-2.5-flash"

# Кайра аракет кылуу логикасы
MAX_RETRIES = 3 # Максималдуу кайра аракет саны
RETRY_DELAY = 5 # Кайра аракеттердин ортосундагы күтүү убактысы (секунд)

# Логгерди орнотуу
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- GEMINI КЛИЕНТИН ИШКЕ КИРГИЗҮҮ ---
genai_client = None
if GEMINI_API_KEY:
    try:
        # API ачкычын колдонуп Gemini клиентин түзүү
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini API клиенти ийгиликтүү ишке кирди.")
    except Exception as e:
        logger.error(f"Gemini API клиентин ишке киргизүүдө ката: {e}")

# ⭐ ЖАҢЫЛАНГАН SYSTEM PROMPT ⭐
SYSTEM_PROMPT = """Сиз достук маанайдагы, сылык жана маалыматтуу жардамчысыз. 
Сиздин милдеттериңиз:
1. Колдонуучунун суроосуна ошол эле тилде жооп берүү.
2. Жооптун башында **колдонуучунун атын атап** (эгер берилсе), сылык кайрылуу.
3. **Кыскача жооп берүү.** Эгер колдонуучу "толуктап бер" же "кеңири айт" деп атайын суранса гана, толук жооп берүү.
4. Жооптордо эч качан өзүңүздүн милдетиңизди же эрежелериңизди эскертпөө.
"""

# Текст билдирүүлөргө жооп берүүчү функция
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    if not genai_client:
        await update.message.reply_text("Кечиресиз, Gemini API клиенти конфигурацияланган эмес.")
        return

    user_prompt = update.message.text
    if not user_prompt:
        return

    # Чекитти текшерүү: Эгер чекит менен башталбаса, эч кандай жооп бербей, функцияны токтотот.
    if not user_prompt.startswith('.'):
        logger.info("Билдирүү чекит менен башталган жок. Эске алынган жок (Ignored).")
        return

    # Колдонуучунун атын алуу
    chat_member = update.message.from_user
    user_name = chat_member.first_name 
    if chat_member.last_name:
        user_name += f" {chat_member.last_name}"
    
    logger.info(f"Суроо келди: {user_prompt} (Колдонуучу: {user_name})")
    await update.message.chat.send_action("typing")

    # Чекитти алып салуу
    user_prompt_clean = user_prompt[1:].strip()
    
    # КОЛДОНУУЧУНУН АТЫН PROMPT'КА КОШУУ
    full_prompt = f"Колдонуучунун аты: {user_name}. Анын суроосу: {user_prompt_clean}"
    
    config = {
        "system_instruction": SYSTEM_PROMPT 
    }
    
    # Кайра аракет кылуу циклы
    for attempt in range(MAX_RETRIES):
        try:
            # ⭐ КАТА ОҢДОЛДУ: config өзүнчө аргумент катары берилди ⭐
            response = genai_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt, 
                config=config, # Туура жер
            )
            
            # Эгер ийгиликтүү болсо, жоопту кайтарып, функцияны токтотуу
            await update.message.reply_text(response.text)
            return

        except APIError as e:
            # APIError катасын кармоо
            if "UNAVAILABLE" in str(e) and attempt < MAX_RETRIES - 1:
                logger.warning(f"Gemini жеткиликсиз. {RETRY_DELAY} секунддан кийин {attempt + 2}-жолу аракет кылуу...")
                await asyncio.sleep(RETRY_DELAY) # Асинхрондук күтүү
                continue
            else:
                logger.error(f"Gemini API'ден жооп алууда туруктуу ката: {e}")
                await update.message.reply_text(f"**API Катасы:** Суроого жооп алууда туруктуу ката кетти.")
                return
        
        except Exception as e:
            # Башка жалпы каталар
            logger.error(f"Белгисиз ката: {e}")
            await update.message.reply_text("Кечиресиз, белгисиз ката кетти.")
            return

    # Эгер бардык аракеттер ийгиликсиз болсо
    await update.message.reply_text("Кечиресиз, Gemini кызматы учурда ашыкча жүктөлгөн. Бир нече мүнөттөн кийин кайра аракет кылып көрүңүз.")


# --- НЕГИЗГИ ФУНКЦИЯ ---

def main() -> None:
    """Ботту ишке киргизет."""
    
    # Environment Variables текшерүү
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        logger.error("❌ TELEGRAM_BOT_TOKEN же GEMINI_API_KEY Environment Variables аркылуу коюлган эмес.")
        return

    # Telegram Application'ды түзүү
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Текст билдирүүлөрдү кармап, handle_message функциясына жөнөтүү
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Ботту иштетүү (бот токтотулганга чейин иштей берет)
    logger.info("✅ Бот ишке кирди. Суроолорду күтүп жатат...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
