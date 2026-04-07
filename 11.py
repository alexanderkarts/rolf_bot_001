import logging
import pandas as pd
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN,SHEET_CSV_URL
# --- Настройки ---
TELEGRAM_TOKEN = TELEGRAM_TOKEN  # вставь свой токен
CSV_URL = SHEET_CSV_URL  # путь к CSV с полным стоком

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Колонки ---
FULL_COLUMNS = [
    "Номер ключа", "VIN", "Кол-во фото для сайта", "Модель", "Марка",
    "Место хранения", "Пробег", "Год выпуска", "Цветкузова", "Рег. номер",
    "Дней с даты поступления", "ДЦ приёма", "Цена продажи", "Цена приема",
    "Байер", "Тип сделки", "Тип кузова"
]

PHOTO_COLUMNS = [
    "Номер ключа", "VIN", "Модель", "Марка",
    "Пробег", "Год выпуска", "Цветкузова",
    "Рег. номер", "Дней с даты поступления",
    "ДЦ приёма", "Тип сделки"
]


# --- Загрузка данных ---
def load_data():
    df = pd.read_csv(CSV_URL)
    return df


# --- Фильтры ---
def full_stock(df):
    return df[FULL_COLUMNS]


def without_photo(df):
    df = df[df["Кол-во фото для сайта"] == 0]
    df = df.sort_values(by="Дней с даты поступления", ascending=False)
    return df[PHOTO_COLUMNS]


def without_storage(df):
    df = full_stock(df)
    df = df[df["Кол-во фото для сайта"] != 0]
    df = df[df["Место хранения"].isna() | (df["Место хранения"] == "")]
    df = df.sort_values(by="Дней с даты поступления", ascending=True)
    return df[FULL_COLUMNS]


# --- Создание Excel для отправки ---
def df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Лист1")
        worksheet = writer.sheets["Лист1"]
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)
    output.seek(0)
    return output


# --- Статистика по парковкам ---
def parking_stats(df):
    df = full_stock(df)
    parking_count = df.groupby("Место хранения")["Номер ключа"].count().to_dict()
    no_storage_count = df[df["Место хранения"].isna() | (df["Место хранения"] == "")]["Номер ключа"].count()
    stats = "📊 Статистика по парковкам:\n"
    for place, count in parking_count.items():
        if place != "" and not pd.isna(place):
            stats += f"{place}: {count}\n"
    stats += f"Без места хранения: {no_storage_count}"
    return stats


# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Полный сток", callback_data="full_stock")],
        [InlineKeyboardButton("Авто без фото", callback_data="without_photo")],
        [InlineKeyboardButton("Авто без места хранения", callback_data="without_storage")],
        [InlineKeyboardButton("Статистика парковок", callback_data="parking_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    df = load_data()

    if query.data == "full_stock":
        file = df_to_excel(full_stock(df))
        await query.message.reply_document(document=file, filename="full_stock.xlsx")
    elif query.data == "without_photo":
        file = df_to_excel(without_photo(df))
        await query.message.reply_document(document=file, filename="without_photo.xlsx")
    elif query.data == "without_storage":
        file = df_to_excel(without_storage(df))
        await query.message.reply_document(document=file, filename="without_storage.xlsx")
    elif query.data == "parking_stats":
        stats = parking_stats(df)
        await query.message.reply_text(stats)


# --- Главная функция ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()


if __name__ == "__main__":
    main()