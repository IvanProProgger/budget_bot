from os import getenv

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Класс-конфиг для проекта"""

    telegram_bot_token = getenv("TELEGRAM_BOT_TOKEN")
    google_sheets_spreadsheet_id = getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    database_path = getenv("DATABASE_PATH")
    google_sheets_credentials_file = getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    google_sheets_categories_sheet_id = getenv("GOOGLE_SHEETS_CATEGORIES_SHEET_ID")
    google_sheets_records_sheet_id = getenv("GOOGLE_SHEETS_RECORDS_SHEET_ID")
    department_head_chat_id = list(map(int, getenv("DEPARTMENT_HEAD_CHAT_ID").split(",")))
    finance_chat_ids = list(map(int, getenv("FINANCE_CHAT_IDS").split(",")))
    payers_chat_ids = list(map(int, getenv("PAYERS_CHAT_IDS").split(",")))
    developer_chat_id = getenv("DEVELOPER_CHAT_ID")
