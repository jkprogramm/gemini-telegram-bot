import os
import logging
import asyncio # Асинхрондук күтүү үчүн
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from google import genai
from google.genai.errors import APIError 

# --- КОНФИГУРАЦИЯ ---
# API ачкычтарын Environment Variables аркылуу алабыз (коопсуздук үчүн маанилүү!)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Модель
GEMINI_MODEL = "gemini-2.5-flash"

# Кайра аракет кылуу логикасы
MAX_RETRIES = 3 
RETRY_DELAY = 5 

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
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini API клиенти ийгиликтүү ишке кирди.")
    except Exception as e:
        logger.error(f"Gemini API клиентин ишке киргизүүдө ката: {e}")

# --- ТЕЛЕГРАМ ХЭНДЛЕР ФУНКЦИЯСЫ ---
SYSTEM_PROMPT = "Ар дайым кыска жана так жооп бер. Ар бир жооптун алдына ** белгисин кой. Кайсы тилде жазса ошол тилде гана жооп бергени аракет кыл"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    user_prompt = update.message.text
    if not user_prompt:
        return

    logger.info(f"Суроо келди: {user_prompt}")
    await update.message.chat.send_action("typing")

    # 1. Чекитти текшерүү
    if not user_prompt.startswith('.'):
        await update.message.reply_text("**Эскертүү:** Суроону чекит '.' белгиси менен баштаңыз. Мисалы: `.Салам кандайсын?`")
        return

    # 2. Чекитти алып салуу жана конфигурацияны түзүү
    user_prompt_clean = user_prompt[1:]
    
    config = {
        "system_instruction": SYSTEM_PROMPT 
    }
    
    # 3. Кайра аракет кылуу циклы
    for attempt in range(MAX_RETRIES):
        try:
            # Gemini API'ге суроо жөнөтүү
            response = genai_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt_clean,
                config=config # Config'ти туура колдонуу
            )
            
            # Эгер ийгиликтүү болсо, жоопту кайтарып, функцияны токтотуу
            await update.message.reply_text(response.text)
            return

        except APIError as e:
            if "UNAVAILABLE" in str(e) and attempt < MAX_RETRIES - 1:
                logger.warning(f"Gemini жеткиликсиз. {RETRY_DELAY} секунддан кийин {attempt + 2}-жолу аракет кылуу...")
                await asyncio.sleep(RETRY_DELAY) # time.sleep ордуна asyncio.sleep
                continue
            else:
                logger.error(f"Gemini API'ден жооп алууда туруктуу ката: {e}")
                await update.message.reply_text(f"**API Катасы:** Суроого жооп алууда туруктуу ката кетти.")
                return
        
        except Exception as e:
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
        logger.error("❌ TELEGRAM_BOT_TOKEN же GEMINI_API_KEY Environment Variables аркылуу коюлган эмес. Орнотууну текшериңиз.")
        return

    # Telegram Application'ды түзүү
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Render'де worker катары иштетүү үчүн run_polling колдонобуз.
    logger.info("✅ Бот ишке кирди. Суроолорду күтүп жатат...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()