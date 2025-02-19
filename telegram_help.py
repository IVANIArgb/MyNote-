import telebot
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
API_TOKEN = "API ТОКЕН"

# Создание бота
bot = telebot.TeleBot(API_TOKEN)

# Глобальные переменные
current_mode = None
problems_count = {}

# Создание клавиатур
def get_main_keyboard():
    """Создание главной клавиатуры"""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Описать проблему')
    markup.row('Предложения по проекту')
    return markup

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_handler(message):
    global current_mode
    current_mode = None
    bot.send_message(
        message.chat.id,
        "Добро пожаловать! Выберите действие:",
        reply_markup=get_main_keyboard()
    )


# Обработчик описания проблемы
@bot.message_handler(func=lambda message: message.text == "Описать проблему")
def describe_problem_handler(message):
    global current_mode
    current_mode = 'problem'
    bot.send_message(
        message.chat.id,
        "Пожалуйста, опишите вашу проблему:",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )


# Обработчик предложений по проекту
@bot.message_handler(func=lambda message: message.text == "Предложения по проекту")
def project_suggestions_handler(message):
    global current_mode
    current_mode = 'suggestion'
    bot.send_message(
        message.chat.id,
        "Пожалуйста, напишите ваше предложение по дополнению проекта:",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )

# Обработчик пользовательского ввода
@bot.message_handler(func=lambda message: True)
def handle_input(message):
    global current_mode

    if current_mode == 'problem':
        with open('described_problems.txt', 'a', encoding='utf-8') as f:
            f.write(f"{message.text}\n")
        bot.send_message(
            message.chat.id,
            "Ваша проблема записана. Спасибо!",
            reply_markup=get_main_keyboard()
        )
        current_mode = None

    elif current_mode == 'suggestion':
        with open('project_suggestions.txt', 'a', encoding='utf-8') as f:
            f.write(f"{message.text}\n")
        bot.send_message(
            message.chat.id,
            "Спасибо за ваше предложение!",
            reply_markup=get_main_keyboard()
        )
        current_mode = None


def main():
    # Запуск бота
    bot.polling(none_stop=True)


if __name__ == '__main__':
    main()
