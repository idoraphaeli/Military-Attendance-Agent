import logging
import gspread
import database
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_clean_pluga_data():
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
        client = gspread.authorize(creds)

        sheet_id = "1YFcahcjVIRHhzE7cfg_6doUDQYxiJVLnWL88PinDp-4"
        target_gid = 2042418621

        spreadsheet = client.open_by_key(sheet_id)

        worksheet = None
        for sheet in spreadsheet.worksheets():
            if sheet.id == target_gid:
                worksheet = sheet
                break

        if not worksheet:
            raise Exception(f"Worksheet with GID {target_gid} not found.")

        raw_data = worksheet.get_all_values()

        if len(raw_data) <= 10:
            raise Exception("הגיליון ריק או ששורת הכותרות חסרה.")

        headers = raw_data[19]

        soldier_rows = raw_data[20:]

        clean_soldiers = []

        for row in soldier_rows:
            if len(row) < len(headers):
                row += [''] * (len(headers) - len(row))

            soldier_dict = dict(zip(headers, row))

            first_name = soldier_dict.get('שם פרטי', '').strip()
            last_name = soldier_dict.get('שם משפחה', '').strip()

            if first_name and last_name and not first_name.startswith('סה"כ') and not first_name.startswith('כמות'):
                soldier_dict['שם פרטי'] = " ".join(first_name.split())
                soldier_dict['שם משפחה'] = " ".join(last_name.split())

                clean_soldiers.append(soldier_dict)

        logger.info(f"✅ תהליך הניקוי הדינמי הסתיים בהצלחה! סונכרנו {len(clean_soldiers)} חיילים בצורה נקייה.")
        return clean_soldiers

    except Exception as e:
        logger.error(f"שגיאה בתהליך עיבוד הנתונים מגוגל שיטס: {e}")
        return None

def get_authorized_soldiers():
   
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
        client = gspread.authorize(creds)

        sheet_id = "1YFcahcjVIRHhzE7cfg_6doUDQYxiJVLnWL88PinDp-4"
        spreadsheet = client.open_by_key(sheet_id)

        worksheet = None
        for sheet in spreadsheet.worksheets():
            normalized_title = sheet.title.replace('"', '').replace("'", '').replace('\u05f4', '').replace('\u05f3', '')
            if 'סטאטוס כא' in normalized_title or 'סטטוס כא' in normalized_title:
                worksheet = sheet
                break

        if not worksheet:
            raise Exception("גיליון 'סטאטוס כ\"א' לא נמצא.")

        raw_data = worksheet.get_all_values()
        if len(raw_data) <= 1:
            raise Exception("גיליון 'סטאטוס כ\"א' ריק.")

        headers = raw_data[0]
        authorized = {}

        for row in raw_data[1:]:
            if len(row) < len(headers):
                row += [''] * (len(headers) - len(row))
            row_dict = dict(zip(headers, row))
            personal_id = row_dict.get('מספר אישי', '').strip()
            first_name = row_dict.get('שם פרטי', '').strip()
            last_name = row_dict.get('שם משפחה', '').strip()

            if personal_id and first_name:
                authorized[personal_id] = {"first_name": first_name, "last_name": last_name}

        logger.info(f"נטענו {len(authorized)} חיילים מורשים מגיליון כ\"א.")
        return authorized

    except Exception as e:
        logger.error(f"שגיאה בטעינת רשימת המורשים: {e}")
        return None


if __name__ == "__main__":
    logger.info("=== מתחיל תהליך סנכרון פלוגתי ידני ומאובטח ===")

    database.init_db()

    soldiers_data = get_clean_pluga_data()

    if soldiers_data:
        database.save_soldiers_to_db(soldiers_data)
        logger.info("=== תהליך הסנכרון הידני הסתיים בהצלחה! ===")
    else:
        logger.error("סנכרון נכשל - לא הוזרקו נתונים חדשים.")
