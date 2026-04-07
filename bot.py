import logging
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import TELEGRAM_TOKEN, SHEET_URL, GOOGLE_CREDENTIALS_JSON, GOOGLE_SHEET_URL
from utils import full_stock, PHOTO_COLUMNS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_KEY = {}

# ===== Reply кнопки =====
reply_keyboard = [
    ["Статистика"],
    ["Полный сток", "Авто без фото"],
    ["Авто без места хранения"],
    ["Поиск ключа"]
]
markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

# ===== Google Sheets =====
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_JSON, scope)
client = gspread.authorize(creds)
gs_sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1


# ===== Загрузка данных =====
def load_data() -> pd.DataFrame:
    try:
        df = pd.read_csv(SHEET_URL)
        logger.info("Данные загружены")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()


# ===== Форматирование Excel =====
def format_excel(file_path: str):
    wb = load_workbook(file_path)
    ws = wb.active

    # Центрирование всех ячеек
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Автоширина колонок
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                value = str(cell.value)
                if len(value) > max_length:
                    max_length = len(value)
            except:
                pass
        ws.column_dimensions[column].width = max_length + 2

    wb.save(file_path)


# ===== Запись DataFrame в Google Sheets =====
def write_df_to_sheet(sheet, df: pd.DataFrame):
    df_clean = df.fillna("")  # заменяем NaN на пустые строки
    values = [df_clean.columns.tolist()] + df_clean.values.tolist()
    sheet.update(range_name="A1", values=values)


# ===== Команды =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=markup)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    df = load_data()

    if df.empty:
        await update.message.reply_text("Ошибка: нет данных для отображения.")
        return

    if text == "Полный сток":
        df_full = full_stock(df)
        file_path = "full_stock.xlsx"
        df_full.to_excel(file_path, index=False)
        format_excel(file_path)
        write_df_to_sheet(gs_sheet, df_full)
        total = len(df_full)
        await update.message.reply_text(f"Полный сток готов. Всего машин: {total}")
        await update.message.reply_document(open(file_path, "rb"))
        logger.info(f"Отправлен полный сток ({total} машин)")

    elif text == "Авто без фото":
        df_photo = df[df["Кол-во фото для сайта"] == 0]
        df_photo = df_photo.sort_values(by="Дней с даты поступления", ascending=False)
        df_photo = df_photo[PHOTO_COLUMNS]
        file_path = "auto_without_photo.xlsx"
        df_photo.to_excel(file_path, index=False)
        format_excel(file_path)
        write_df_to_sheet(gs_sheet, df_photo)
        total = len(df_photo)
        await update.message.reply_text(f"Авто без фото готово. Всего машин: {total}")
        await update.message.reply_document(open(file_path, "rb"))
        logger.info(f"Отправлен список авто без фото ({total} машин)")

    elif text == "Авто без места хранения":
        df_full = full_stock(df)
        df_no_storage = df_full[
            (df_full["Место хранения"].isna() | (df_full["Место хранения"] == "")) &
            (df_full["Кол-во фото для сайта"] != 0)
        ]
        df_no_storage = df_no_storage.sort_values(by="Дней с даты поступления", ascending=True)
        file_path = "Авто_без_места.xlsx"
        df_no_storage.to_excel(file_path, index=False)
        format_excel(file_path)
        write_df_to_sheet(gs_sheet, df_no_storage)
        message = f"Авто без места хранения: {len(df_no_storage)} машин"
        await update.message.reply_document(open(file_path, "rb"), caption=message)
        logger.info(f"Отправлен список авто без места хранения ({len(df_no_storage)} машин)")

    elif text == "Статистика":
        df_full = full_stock(df)
        total_stock = len(df_full)
        no_photo = len(df_full[df_full["Кол-во фото для сайта"] == 0])
        no_storage = len(df_full[
            (df_full["Место хранения"].isna() | (df_full["Место хранения"] == "")) &
            (df_full["Кол-во фото для сайта"] != 0)
        ])
        parking_counts = df_full["Место хранения"].fillna("Без места").value_counts()

        message = (
            f"📊 Статистика\n\n"
            f"Полный сток: {total_stock}\n"
            f"Авто без фото: {no_photo}\n"
            f"Авто без места хранения: {no_storage}\n\n"
            f"Парковки:\n"
        )
        for parking, count in parking_counts.items():
            message += f"{parking}: {count}\n"

        await update.message.reply_text(message)
        logger.info("Отправлена статистика")

    elif text == "Поиск ключа":
        WAITING_KEY[update.message.chat_id] = True
        await update.message.reply_text("Введите номер ключа")

    elif WAITING_KEY.get(update.message.chat_id):
        WAITING_KEY.pop(update.message.chat_id)
        if not text.isdigit():
            await update.message.reply_text("Номер ключа должен быть числом")
            return
        key_number = int(text)
        df_full = full_stock(df)
        car = df_full[df_full["Номер ключа"] == key_number]
        if car.empty:
            await update.message.reply_text("Машина не найдена")
            return
        car = car.iloc[0]
        message = (
            f"🚗 Автомобиль найден\n\n"
            f"Номер ключа: {car['Номер ключа']}\n"
            f"Марка: {car['Марка']}\n"
            f"Модель: {car['Модель']}\n"
            f"VIN: {car['VIN']}\n"
            f"Год выпуска: {car['Год выпуска']}\n"
            f"Пробег: {car['Пробег']}\n"
            f"Цвет: {car['Цветкузова']}\n"
            f"Рег. номер: {car['Рег. номер']}\n"
            f"Парковка: {car['Место хранения']}\n"
            f"Дней в стоке: {car['Дней с даты поступления']}\n"
            f"Цена продажи: {car['Цена продажи']}\n"
            f"Байер: {car['Байер']}\n"
            f"Тип сделки: {car['Тип сделки']}"
        )
        await update.message.reply_text(message)

    else:
        await update.message.reply_text("Неизвестная команда. Попробуйте ещё раз.")


# ===== Основной запуск =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Бот запущен")
    app.run_polling()