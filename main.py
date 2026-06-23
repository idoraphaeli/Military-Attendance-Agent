import os
import logging
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.request import HTTPXRequest
from openai import OpenAI
import sync_service 
import database

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

WAITING_FOR_ID = 0
conversation_histories = {}
MAX_HISTORY = 10

tools_specification = [
    {
        "type": "function",
        "function": {
            "name": "get_present_soldiers_by_date_and_dept",
            "description": "שליפת רשימת החיילים שנוכחים פיזית בבסיס (מסומנים ב-'1') בתאריך מסוים. יש להשתמש בזה כששואלים 'מי נמצא מחר/היום', או 'כמה חיילים יש בתאריך X' ממחלקה כלשהי.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "התאריך המבוקש בפורמט יום/חודש, למשל '1/6' או '2/6'."},
                    "department": {"type": "string", "description": "אופציונלי: שם או מספר המחלקה לסינון (למשל: 'חפק', '2', 'מטבח')."}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_soldier_by_name",
            "description": "שליפת פרטים ולו''ז מלא עבור חייל ספציפי לפי השם שלו. יש להשתמש בזה כששואלים מתי חייל מסוים יוצא הביתה או מה הלו''ז האישי שלו ברמת התאריכים הגולמיים.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "השם המלא או הפרטי של החייל."}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_soldiers_by_status_and_date",
            "description": "שליפת חיילים שנמצאים בסטטוס יציאה ספציפי בתאריך מסוים. יש להשתמש בזה כששואלים 'מי יוצא מחר חופש', 'מי באפטר היום' או 'מי קיבל גימלים'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "התאריך המבוקש בפורמט יום/חודש, למשל '1/6'."},
                    "status": {
                        "type": "string", 
                        "description": "הסטטוס לחיפוש בקוד: מחרוזת ריקה '' מסמלת חופשה בבית (תא צהוב), 'א' מסמל אפטר, 'ג' מסמל גימלים, 'חמ' מסמל חופשה מיוחדת, 'X' מסמל צו סגור."
                    }
                },
                "required": ["date", "status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_soldier_summary_stats",
            "description": "שליפת נתונים סטטיסטיים מסוכמים של חייל (סה''כ ימי חופשה, כמות ימי קו, כמות אפטרים, סוג נשק, יחס בית/מילואים). יש להשתמש בזה כשמבקשים סיכום או נתונים מצטברים על חייל.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "שם החייל לבדיקת הסטטיסטיקה."}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_commanders_status",
            "description": "שליפת סטטוס הנוכחות והיציאות של כל סגל הפיקוד בפלוגה (מ''פ, מ''מ, מפקדים) בתאריך מסוים. יש להשתמש בזה כשמפקד שואל 'איזה מפקדים נמצאים מחר' או 'מה סטטוס הסגל ב-1/6'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "התאריך המבוקש בפורמט יום/חודש, למשל '2/6'."}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_department_status_for_date",
            "description": "שליפת סטטוס שמי מלא של כלל חיילי מחלקה מסוימת (כולל מי בבית, מי נוכח, ומי יוצא/חוזר) עבור תאריך ספציפי. יש להשתמש בזה כשמבקשים 'סטטוס מחלקה', 'דו''ח נוכחות של מחלקה 2' או 'מצב מחלקה מחר'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "התאריך המבוקש בפורמט יום/חודש, למשל '1/6' או '2/6'."},
                    "department": {"type": "string", "description": "מספר או שם המחלקה, למשל '2'."}
                },
                "required": ["date", "department"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_presence_stats",
            "description": "שליפת כמויות ורשימות חיילים נוכחים בפלוגה ביום מסוים לפי פילוח תפקידים (כלל הפלוגה, לוחמים, נהגים, מ''מים, קצינים, מפקדים).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "התאריך המבוקש בפורמט יום/חודש, למשל '1/6' או '2/6'."},
                    "category": {
                        "type": "string",
                        "description": "הקטגוריה המבוקשת לספירה: 'all' (כלל הפלוגה), 'combat' (לוחמים: מפקד+לוחם+מ''מ+נהג), 'drivers' (נהגים בלבד), 'mms' (מ''מים בלבד), 'officers' (קצינים: מ''פ+מ''מ), 'commanders' (מפקדים בלבד)."
                    }
                },
                "required": ["date", "category"]
            }
        }
    }
]
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if database.is_chat_authenticated(chat_id):
        await update.message.reply_text("אתה כבר מזוהה במערכת. שאל אותי חופשי על נוכחות, חופשות, מפקדים או סטטיסטיקות חיילים.")
        return ConversationHandler.END
    await update.message.reply_text("ברוך הבא לבוט החמ\"ל הפלוגתי.\nאנא הזן את המספר האישי שלך לאימות זהות:")
    return WAITING_FOR_ID

async def handle_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    personal_id = update.message.text.strip()
    chat_id = update.effective_chat.id

    soldier = database.check_personal_id(personal_id)
    if soldier:
        database.authenticate_chat(chat_id, soldier['personal_id'], soldier['first_name'])
        await update.message.reply_text(
            f"זיהוי בוצע בהצלחה, {soldier['first_name']}!\n"
            "ברוך הבא לחמ\"ל הפלוגתי. שאל אותי חופשי על נוכחות, חופשות, מפקדים או סטטיסטיקות חיילים."
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("המספר האישי לא נמצא ברשימה המורשית. נסה שוב:")
        return WAITING_FOR_ID

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not database.is_chat_authenticated(chat_id):
        await update.message.reply_text("⛔ אין לך הרשאה. שלח /start כדי להזדהות.")
        return
    msg = await update.message.reply_text("מבצע סנכרון מגוגל שיטס...")
    run_sync_process()
    await msg.edit_text("הסנכרון הושלם בהצלחה! הנתונים עדכניים.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    user_name = update.effective_user.first_name
    chat_id = update.effective_chat.id

    if not database.is_chat_authenticated(chat_id):
        if context.user_data.get('waiting_for_id'):
            soldier = database.check_personal_id(user_text.strip())
            if soldier:
                database.authenticate_chat(chat_id, soldier['personal_id'], soldier['first_name'])
                context.user_data.pop('waiting_for_id', None)
                await update.message.reply_text(
                    f"זיהוי בוצע בהצלחה, {soldier['first_name']}!\n"
                    "ברוך הבא לחמ\"ל הפלוגתי. שאל אותי חופשי על נוכחות, חופשות, מפקדים או סטטיסטיקות חיילים."
                )
            else:
                await update.message.reply_text("המספר האישי לא נמצא ברשימה. נסה שוב:")
        else:
            context.user_data['waiting_for_id'] = True
            await update.message.reply_text(
                "שלום! כדי להשתמש בבוט יש להזדהות.\nאנא הזן את המספר האישי שלך:"
            )
        return

    logger.info(f"Received question from {user_name}: '{user_text}'")
    waiting_message = await update.message.reply_text("מעבד נתונים בחמ''ל... 🔄")
    
    try:
        now = datetime.now()
        today_str = f"{now.day}/{now.month}"
        tomorrow_str = f"{(now + timedelta(days=1)).day}/{(now + timedelta(days=1)).month}"
        hebrew_days = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']
        day_name = hebrew_days[now.weekday()]

        system_instruction = f"""
אתה עוזר חמ''ל פלוגתי חכם ואמין. תפקידך לענות על שאלות בנוגע לשבצ''ק ולו''ז היציאות.
היום יום {day_name}, {now.day}/{now.month}/{now.year}. שים לב היטב לתאריכים:
- 'היום' משמעותו {today_str}
- 'מחר' משמעותו {tomorrow_str}

--- הנחיות עבודה WITH ארגז הכלים (Tools): ---
1. בחר תמיד בכלי הממוקד והמדויק ביותר שמתאים לשאלת המשתמש.
2. אל תנחש מספרים או כמויות! כמות החיילים הנוכחים/בבית היא בדיוק אורך הרשימה שחוזרת מהפונקציה שהפעלת.
3. נסח את התשובות בעברית תקנית, מיושרת לימין, קריאה ומכבדת (סגנון צבאי פיקודי קצר ולעניין).

--- חוקי הגדרת תפקידים וקטגוריות (חשוב ביותר!): ---
4. שים לב היטב להבדל בין התפקידים: 'מ''מ' הוא קצין (מפקד מחלקה), בעוד ש'מפקד' הוא מפקד כיתה/צוות (מ''כ). אל תערבב ביניהם! אם ביקשו מ''מים, הצג אך ורק בעלי תפקיד 'מ''מ'.
5. המערכת חסינה לחלוטין לגרשיים, מרכאות ומקפים (מ''מ, ממ, חפ''ק, חפק, מ''פ, מפ וכדומה). אם המשתמש כותב 'מחלקת חפק' או 'חפ''ק', העבר לפונקציות פשוט את המילה 'חפק' כפרמטר למחלקה.

--- חוקי ספירה ופירוט שמי (פלוגה / לוחמים / נהגים / מ''מים / קצינים / מפקדים): ---
6. כשמבקשים ספירה של פלוגה/לוחמים/נהגים/קצינים/מפקדים בעזרת הכלי `get_company_presence_stats`, עליך לציין בתשובתך תחילה את הסך הכל (כמות האיברים ברשימה שחזרה), ולאחר מכן לרשום את פירוט השמות המלא של האנשים שנמצאו נוכחים (סטטוס '1') פלוס התפקיד שלהם. אל תפלוט שמות שלא מופיעים בתוצאת הכלי!

--- חוק עיצוב סטטוס מחלקתי: ---
7. כאשר מפקד מבקש סטטוס מחלקה, מצב מחלקה או דו''ח נוכחות ליום מסוים, הפעל את `get_department_status_for_date`.
עליך לעצב את התשובה בדיוק בפורמט הבא, שורה אחר שורה, בלי הקדמות מיותרות:
מחלקה [מספר מחלקה] [תאריך מבוקש]:
[שם חייל 1] - [סטטוס]
[שם חייל 2] - [סטטוס]

--- חוק חישוב ימי בית (סטטיסטיקה): ---
8. כשמשתמש מבקש סיכום ימי בית או ימי חופשה של חייל, הפונקציה `get_soldier_summary_stats` כבר מחשבת ומחזירה את סך הימים (כאשר ימים ריקים וגם ימי יציאה 'י' נספרים כימים בבית). המספר שהיא מחזירה הוא הקובע הבלעדי.

--- חוקי טיפול בשגיאות ותוצאות ריקות: ---
9. אם תוצאת כלי חזרה עם רשימה ריקה או total_count שווה 0, ציין זאת במפורש: "לא נמצאו חיילים התואמים את החיפוש."
10. אם חיפוש לפי שם החזיר תוצאה ריקה, ענה: "לא נמצא חייל בשם [שם] במערכת."
11. אל תמציא נתונים או שמות שלא הופיעו בתוצאת הכלי. אם אין מידע - אמור זאת בפירוש.
"""
        
        user_id = update.effective_user.id
        history = conversation_histories.get(user_id, [])

        messages = [{"role": "system", "content": system_instruction}] + history + [{"role": "user", "content": user_text}]

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools_specification,
            tool_choice="auto"
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            logger.info(f"AI selected {len(tool_calls)} tool(s) to execute.")
            messages = messages + [response_message]
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "get_present_soldiers_by_date_and_dept":
                    soldiers = database.get_present_soldiers_by_date_and_dept(function_args.get("date"), function_args.get("department"))
                    db_result = {"total_count": len(soldiers), "soldiers": soldiers}

                elif function_name == "get_company_presence_stats":
                    date_arg = function_args.get("date")
                    category_arg = function_args.get("category")
                    logger.info(f"Executing Presence Stats for date: {date_arg}, category: {category_arg}")
                    
                    roles_filter = None
                    if category_arg == 'combat':
                        roles_filter = ['מפקד', 'לוחם', 'מ"מ', 'נהג']
                    elif category_arg == 'drivers':
                        roles_filter = ['נהג']
                    elif category_arg == 'mms':
                        roles_filter = ['מ"מ']
                    elif category_arg == 'officers':
                        roles_filter = ['מ"פ', 'מ"מ']
                    elif category_arg == 'commanders':
                        roles_filter = ['מפקד']
                    
                    soldiers = database.count_present_soldiers_by_roles(date_arg, roles_filter)
                    db_result = {"total_count": len(soldiers), "soldiers": soldiers}
                
                elif function_name == "get_department_status_for_date":
                    date_arg = function_args.get("date")
                    dept_arg = function_args.get("department")
                    logger.info(f"Executing Department Status query for date: {date_arg}, dept: {dept_arg}")
                    db_result = database.get_department_status_for_date(date_arg, dept_arg)
                    
                elif function_name == "get_soldier_by_name":
                    db_result = database.get_soldier_by_name(function_args.get("name"))
                    
                elif function_name == "get_soldiers_by_status_and_date":
                    db_result = database.get_soldiers_by_status_and_date(function_args.get("date"), function_args.get("status"))
                    
                elif function_name == "get_soldier_summary_stats":
                    db_result = database.get_soldier_summary_stats(function_args.get("name"))
                    
                elif function_name == "get_all_commanders_status":
                    db_result = database.get_all_commanders_status(function_args.get("date"))
                else:
                    db_result = []
                
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(db_result, ensure_ascii=False)
                })
            
            second_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.0
            )
            ai_reply = second_response.choices[0].message.content
        else:
            ai_reply = response_message.content
            
        await waiting_message.edit_text(ai_reply)

        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": ai_reply})
        conversation_histories[user_id] = history[-MAX_HISTORY:]

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await waiting_message.edit_text(f"❌ שגיאה בעיבוד השאילתה: {str(e)}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"⚠️ שגיאה גלובלית: {context.error}")

def run_sync_process():
    """פונקציה מרכזית שמבצעת את כל תהליך הסנכרון מגוגל ל-DB המקומי"""
    logger.info("--- מתחיל סנכרון אוטומטי מגוגל שיטס ---")
    try:
        database.init_db()
        soldiers_data = sync_service.get_clean_pluga_data()
        if soldiers_data:
            database.save_soldiers_to_db(soldiers_data)
        else:
            logger.error("סנכרון לוח הזמנים נכשל - לא התקבלו נתונים.")

        authorized_data = sync_service.get_authorized_soldiers()
        if authorized_data:
            database.save_authorized_soldiers(authorized_data)
        else:
            logger.error("סנכרון רשימת המורשים נכשל - לא התקבלו נתונים.")

        logger.info("--- הסנכרון האוטומטי הסתיים בהצלחה! ---")
    except Exception as e:
        logger.error(f"שגיאה קריטית בריצת מנגנון הסנכרון ברקע: {e}")

def main() -> None:
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        logger.critical("מפתחות חסרים בקובץ ה-.env!")
        return

    request_config = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    application = Application.builder().token(TELEGRAM_TOKEN).request(request_config).build()
    
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id_input)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    application.add_handler(auth_handler)
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    run_sync_process()
    logger.info("🚀 הבוט מבוסס ה-Multi-Tool Agent באוויר ומאזין...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()