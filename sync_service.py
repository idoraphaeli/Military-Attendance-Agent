import logging
import gspread
import database
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_clean_pluga_data():
    """
    מתחברת לגיליון הפלוגתי, חותכת את רעשי הרקע בצורה דינמית
    מחזירה רשימה נקייה וחסינה של מילוני חיילים עם הלו''ז המלא שלהם.
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        # טעינת מפתח האבטחה ואימות מול שרתי גוגל
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
        client = gspread.authorize(creds)

        # מפתחות הגיליון והטאב הפלוגתי הספציפי
        sheet_id = "1YFcahcjVIRHhzE7cfg_6doUDQYxiJVLnWL88PinDp-4"
        target_gid = 2042418621

        spreadsheet = client.open_by_key(sheet_id)

        # מציאת הטאב הנכון לפי ה-GID
        worksheet = None
        for sheet in spreadsheet.worksheets():
            if sheet.id == target_gid:
                worksheet = sheet
                break

        if not worksheet:
            raise Exception(f"Worksheet with GID {target_gid} not found.")

        # משיכת כל הערכים הגולמיים מהטאב במכה אחת כדי לחסוך קריאות רשת
        raw_data = worksheet.get_all_values()

        if len(raw_data) <= 19:
            raise Exception("הגיליון ריק או ששורת הכותרות חסרה.")

        # שורת הכותרות נמצאת באינדקס 19 (שורה 20 באקסל)
        headers = raw_data[19]

        # חיתוך דינמי החל משורה 21 (אינדקס 20) ועד סוף הגיליון האמיתי כדי לתמוך בתוספת לוחמים
        soldier_rows = raw_data[20:]

        clean_soldiers = []

        for row in soldier_rows:
            # ריפוד שורות קצרות במחרוזות ריקות כדי למנוע קריסה ב-zip
            if len(row) < len(headers):
                row += [''] * (len(headers) - len(row))

            # חיבור כותרות הגיליון לערכי השורה של החייל ליצירת מילון (Key-Value)
            soldier_dict = dict(zip(headers, row))

            # חילוץ וניקוי בסיסי של שדות המפתח
            first_name = soldier_dict.get('שם פרטי', '').strip()
            last_name = soldier_dict.get('שם משפחה', '').strip()

            # סינון שורות ריקות ושורות סיכומים/טוטאלים של הגיליון בסוף הטבלה
            if first_name and last_name and not first_name.startswith('סה"כ') and not first_name.startswith('כמות'):
                # ניקוי רווחים כפולים פנימיים בשמות כדי לשמור על בסיס נתונים סטרילי
                soldier_dict['שם פרטי'] = " ".join(first_name.split())
                soldier_dict['שם משפחה'] = " ".join(last_name.split())

                clean_soldiers.append(soldier_dict)

        logger.info(f"✅ תהליך הניקוי הדינמי הסתיים בהצלחה! סונכרנו {len(clean_soldiers)} חיילים בצורה נקייה.")
        return clean_soldiers

    except Exception as e:
        logger.error(f"שגיאה בתהליך עיבוד הנתונים מגוגל שיטס: {e}")
        return None

if __name__ == "__main__":
    # בלוק הרצה ידני לבדיקות מקומיות בטרמינל
    logger.info("=== מתחיל תהליך סנכרון פלוגתי ידני ומאובטח ===")

    # 1. איתחול בסיס הנתונים המקומי
    database.init_db()

    # 2. משיכת הנתונים הנקיים מגוגל שיטס
    soldiers_data = get_clean_pluga_data()

    # 3. שמירה של כל החיילים לתוך קובץ ה-SQLite
    if soldiers_data:
        database.save_soldiers_to_db(soldiers_data)
        logger.info("=== תהליך הסנכרון הידני הסתיים בהצלחה! ===")
    else:
        logger.error("סנכרון נכשל - לא הוזרקו נתונים חדשים.")
