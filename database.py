import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

DB_NAME = "pluga_shavzak.db"

def normalize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace('"', '').replace("'", "").replace("-", "")
    return " ".join(cleaned.split()).lower()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS soldiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            department TEXT,
            role TEXT,
            schedule_data TEXT,
            UNIQUE(first_name, last_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authorized_soldiers (
            personal_id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authenticated_chats (
            chat_id INTEGER PRIMARY KEY,
            personal_id TEXT NOT NULL,
            first_name TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("בסיס הנתונים המקומי אותחל בהצלחה.")

def save_soldiers_to_db(soldiers_list):
    if not soldiers_list:
        logger.warning("רשימת החיילים ריקה, אין מה לשמור בבסיס הנתונים.")
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM soldiers")
        for soldier in soldiers_list:
            first_name = soldier.get('שם פרטי', '').strip()
            last_name = soldier.get('שם משפחה', '').strip()
            department = soldier.get('מחלקה', '').strip()
            role = soldier.get('תפקיד', '').strip()
            
            schedule_dict = soldier.copy()
            for key in ['שם פרטי', 'שם משפחה', 'מחלקה', 'תפקיד']:
                if key in schedule_dict:
                    del schedule_dict[key]
            
            schedule_json_str = json.dumps(schedule_dict, ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO soldiers (first_name, last_name, department, role, schedule_data)
                VALUES (?, ?, ?, ?, ?)
            """, (first_name, last_name, department, role, schedule_json_str))
            
        conn.commit()
        logger.info(f"✅ סונכרנו בהצלחה {len(soldiers_list)} חיילים לתוך בסיס הנתונים המקומי!")
    except Exception as e:
        logger.error(f"שגיאה במהלך שמירת החיילים ל-DB: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_soldier_by_name(name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name, department, role, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    search_name = normalize_text(name)
    results = []
    for row in rows:
        full_name_norm = normalize_text(f"{row[0]} {row[1]}")
        if search_name in full_name_norm or normalize_text(row[0]) in search_name or normalize_text(row[1]) in search_name:
            results.append({
                "name": f"{row[0]} {row[1]}",
                "department": row[2],
                "role": row[3],
                "schedule": json.loads(row[4])
            })
    return results

def get_present_soldiers_by_date_and_dept(date: str, department: str = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, role, department, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    target_dept = normalize_text(department) if department else None
    present_soldiers = []
    
    for row in rows:
        name, role, dept, schedule_json = row[0], row[1], row[2], row[3]
        schedule = json.loads(schedule_json)
        
        if schedule.get(date) in ('1', 'ח'):
            if target_dept:
                if target_dept in normalize_text(dept) or normalize_text(dept) in target_dept:
                    present_soldiers.append({"name": name, "role": role})
            else:
                present_soldiers.append({"name": name, "role": role})
                
    return present_soldiers

def get_soldiers_by_status_and_date(date: str, status: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, department, role, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        schedule = json.loads(row[3])
        current_status = schedule.get(date, '')
        if current_status == status:
            results.append({
                "name": row[0],
                "department": row[1],
                "role": row[2]
            })
    return results

def get_soldier_summary_stats(name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name, department, role, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    search_name = normalize_text(name)
    results = []
    for row in rows:
        full_name_norm = normalize_text(f"{row[0]} {row[1]}")
        if search_name in full_name_norm or normalize_text(row[0]) in search_name or normalize_text(row[1]) in search_name:
            schedule = json.loads(row[4])
            
            vacation_days_count = 0
            for date_key, status_val in schedule.items():
                if '/' in date_key:
                    if status_val == '' or status_val == 'י':
                        vacation_days_count += 1
            
            results.append({
                "name": f"{row[0]} {row[1]}",
                "department": row[2],
                "role": row[3],
                "total_vacation_days": str(vacation_days_count),
                "total_line_days": schedule.get('כמות ימי קו (ללא אלת)', '0'),
                "home_miluim_ratio": schedule.get('יחס בית/מילואים בימ"מ', '0%'),
                "total_afters": schedule.get('כמות אפטרים', '0'),
                "weapon": schedule.get('נשק', 'ללא')
            })
    return results

def get_all_commanders_status(date: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, department, role, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        name, dept, role, schedule_json = row[0], row[1], row[2], row[3]
        role_norm = normalize_text(role)
        
        if role_norm in ['מפ', 'ממ', 'מפקד']:
            schedule = json.loads(schedule_json)
            status_on_date = schedule.get(date, '1')
            
            status_text = "נוכח בבסיס"
            if status_on_date == '': status_text = "בחופשה בבית"
            elif status_on_date == 'י': status_text = "יוצא היום הביתה"
            elif status_on_date == 'ח': status_text = "חוזר היום למוצב"
            elif status_on_date == 'א': status_text = "באפטר"
            elif status_on_date == 'ג': status_text = "בגימלים"
            elif status_on_date == 'X': status_text = "אינו בימ\"מ (צו סגור)"
            
            results.append({
                "name": name,
                "department": dept,
                "role": role,
                "status": status_text
            })
    return results

def get_department_status_for_date(date: str, department: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, role, department, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    target_dept = normalize_text(department)
    status_list = []
    for row in rows:
        name, role, dept, schedule_json = row[0], row[1], row[2], row[3]
        schedule = json.loads(schedule_json)
        
        if target_dept in normalize_text(dept) or normalize_text(dept) in target_dept:
            raw_status = schedule.get(date, '')
            
            if raw_status == '1': display_status = "✅"
            elif raw_status == '': display_status = "בית"
            elif raw_status == 'י': display_status = "יוצא"
            elif raw_status == 'ח': display_status = "חוזר"
            elif raw_status == 'א': display_status = "אפטר"
            elif raw_status == 'ג': display_status = "גימלים"
            else: display_status = raw_status
                
            display_name = name
            if normalize_text(role) in ['ממ', 'מפקד']:
                display_name += " (מ)"
                
            status_list.append({
                "name": display_name,
                "status": display_status
            })
            
    return status_list

def count_present_soldiers_by_roles(date: str, roles_list: list = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, role, department, schedule_data FROM soldiers")
    rows = cursor.fetchall()
    conn.close()
    
    normalized_roles_filter = [normalize_text(r) for r in roles_list] if roles_list is not None else None
    matching_soldiers = []
    for row in rows:
        name, role, dept, schedule_json = row[0], row[1], row[2], row[3]
        schedule = json.loads(schedule_json)
        
        if schedule.get(date) in ('1', 'ח'):
            if normalized_roles_filter is not None:
                if normalize_text(role) in normalized_roles_filter:
                    matching_soldiers.append({"name": name, "role": role, "department": dept})
            else:
                matching_soldiers.append({"name": name, "role": role, "department": dept})
                
    return matching_soldiers

def save_authorized_soldiers(authorized_dict: dict):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM authorized_soldiers")
        for personal_id, info in authorized_dict.items():
            cursor.execute(
                "INSERT INTO authorized_soldiers (personal_id, first_name, last_name) VALUES (?, ?, ?)",
                (personal_id, info['first_name'], info['last_name'])
            )
        conn.commit()
        logger.info(f"נשמרו {len(authorized_dict)} חיילים מורשים בבסיס הנתונים.")
    except Exception as e:
        logger.error(f"שגיאה בשמירת רשימת המורשים: {e}")
        conn.rollback()
    finally:
        conn.close()

def check_personal_id(personal_id: str):
    """בודקת אם מספר אישי קיים ברשימה המורשית. מחזירה מידע על החייל או None."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT personal_id, first_name, last_name FROM authorized_soldiers WHERE personal_id = ?",
        (personal_id.strip(),)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"personal_id": row[0], "first_name": row[1], "last_name": row[2]}
    return None

def is_chat_authenticated(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM authenticated_chats WHERE chat_id = ?", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def authenticate_chat(chat_id: int, personal_id: str, first_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO authenticated_chats (chat_id, personal_id, first_name) VALUES (?, ?, ?)",
        (chat_id, personal_id, first_name)
    )
    conn.commit()
    conn.close()