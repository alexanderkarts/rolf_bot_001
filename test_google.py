import gspread
from oauth2client.service_account import ServiceAccountCredentials

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "google_credentials.json",
    scope
)

client = gspread.authorize(creds)

sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/10MNF8ZpOa99iep7H7x0IV2rMDwxUvcwqb2ch4Llq_cU/edit?usp=sharing").sheet1

# ✅ обновляем одну ячейку
sheet.update("A1", [["Бот подключен"]])