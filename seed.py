#!/usr/bin/env python3
"""
Seed script — creates demo tickets for testing the dashboard.
Run: python seed.py
"""
import sqlite3
from datetime import datetime, timedelta
import random

DB_PATH = "tickets.db"

SAMPLES = [
    ("Алия Бекова",    "aliya@mail.kz",  "+7 701 111 2233", "Не могу войти в личный кабинет",
     "После обновления приложения перестал работать вход. Вводю правильный пароль — пишет 'неверные данные'. Срочно нужен доступ, завтра важная презентация.",
     "техническая проблема", "критический"),
    ("Дмитрий Ли",     "dima@corp.kz",   "",                "Вопрос по счёту за февраль",
     "В счёте за февраль указана сумма 45 000 тг, но по договору у нас тариф 38 000 тг. Прошу пересчитать и выставить корректный счёт.",
     "вопрос по оплате", "высокий"),
    ("Марина Сейткали","marina@test.kz", "+7 705 987 6543", "Как настроить интеграцию с 1С?",
     "Хотим подключить 1С:Бухгалтерия к вашей системе. Есть ли документация? Какие требования к версии 1С?",
     "консультация", "средний"),
    ("Нурлан Ахметов", "nurlan@biz.kz",  "",                "Сайт не загружается 3-й день",
     "Начиная с понедельника сайт не открывается. Проверял с разных устройств и интернетов — везде одно и то же. Теряем клиентов каждый день!",
     "техническая проблема", "критический"),
    ("Зарина Омарова", "zarina@ok.kz",   "+7 777 222 3344", "Предложение по улучшению отчётов",
     "Было бы здорово добавить экспорт отчётов в Excel. Сейчас приходится вручную копировать данные.",
     "запрос функции", "низкий"),
    ("Сергей Попов",   "sergey@pop.kz",  "",                "Жалоба на качество обслуживания",
     "Три раза обращался в поддержку по одному вопросу. Каждый раз разные операторы давали противоречивые ответы. Очень недоволен.",
     "жалоба", "высокий"),
    ("Айгерим Джакупова","aig@test.kz",  "+7 712 555 6677", "Нужна консультация по тарифам",
     "Рассматриваем переход на более дорогой тариф. Хотим понять, какие дополнительные возможности мы получим.",
     "консультация", "средний"),
    ("Тимур Сериков",  "timur@ser.kz",   "",                "Ошибка при загрузке файлов",
     "При попытке загрузить файл больше 10 МБ система выдаёт ошибку 500. Нужно загрузить презентацию 25 МБ.",
     "техническая проблема", "высокий"),
]

STATUS_OPTIONS = ["new", "new", "new", "processing", "done", "closed"]

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, phone TEXT,
            subject TEXT, message TEXT,
            category TEXT, priority TEXT, reasoning TEXT, summary TEXT,
            status TEXT DEFAULT 'new', created_at TEXT
        )
    """)

    for i, (name, email, phone, subject, message, category, priority) in enumerate(SAMPLES):
        dt = datetime.now() - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
        conn.execute(
            "INSERT INTO tickets (name,email,phone,subject,message,category,priority,reasoning,summary,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, email, phone, subject, message, category, priority,
             f"Заявка определена как «{category}» с приоритетом «{priority}» на основании содержания обращения.",
             subject[:80],
             random.choice(STATUS_OPTIONS),
             dt.strftime("%Y-%m-%d %H:%M:%S"))
        )

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    conn.close()
    print(f"✅ Добавлено демо-заявок. Всего в БД: {count}")

if __name__ == "__main__":
    seed()
