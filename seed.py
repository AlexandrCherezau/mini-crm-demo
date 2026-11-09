"""Fill the DB with ~40 demo leads (all names are obviously fake).

Usage:  python seed.py            # recreate data/crm.sqlite3
        python seed.py --count 60
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from app import repo
from app.db import MANAGERS, connect, db_path, init_db

FIRST_M = ["Иван", "Пётр", "Сергей", "Алексей", "Николай", "Артём", "Михаил", "Глеб", "Роман", "Олег"]
FIRST_F = ["Анна", "Мария", "Елена", "Ольга", "Дарья", "Ксения", "Вера", "Полина", "Алиса", "Нина"]
SURNAMES = ["Тестов", "Примеров", "Образцов", "Демов", "Макетов", "Шаблонов",
            "Черновиков", "Заглушкин", "Выдумкин", "Пробников", "Фиктивнов", "Условнов"]

REQUESTS = [
    ("Кухня угловая 3,2 м, фасады эмаль", 180_000, 320_000),
    ("Шкаф-купе в прихожую, 2,4 м", 60_000, 110_000),
    ("Гардеробная под ключ", 120_000, 240_000),
    ("Детская: кровать-чердак + стол", 70_000, 130_000),
    ("Стеллаж из массива дуба", 35_000, 70_000),
    ("Тумба под раковину, влагостойкая", 18_000, 35_000),
    ("Перетяжка дивана, рогожка", 15_000, 32_000),
    ("Обеденный стол-трансформер", 40_000, 75_000),
    ("Прихожая с банкеткой", 45_000, 85_000),
    ("Мебель для кофейни: стойка + 6 столов", 210_000, 380_000),
    ("Встроенный шкаф в нишу", 50_000, 95_000),
    ("Замер и консультация по кухне", 0, 0),
]
COMMENTS = [
    "Перезвонить после 18:00, днём на работе.",
    "Отправил расчёт в мессенджер, ждём ответ.",
    "Замер назначен на субботу, 11:00.",
    "Просит рассрочку, уточнить у бухгалтерии.",
    "Сравнивает с двумя другими мастерскими.",
    "Прислала фото помещения и размеры.",
    "Согласовали эскиз, ждём предоплату 50%.",
    "Нужна доставка в область, +3 000 ₽.",
]
LOST_REASONS = ["Дорого, ушёл к конкурентам.", "Передумали, отложили ремонт.", "Не выходит на связь неделю."]
SOURCE_WEIGHTS = {"site": 0.38, "telegram": 0.27, "avito": 0.35}
WIN_RATE = {"site": 0.55, "telegram": 0.62, "avito": 0.38}


def _person(rnd: random.Random) -> str:
    surname = rnd.choice(SURNAMES)
    if rnd.random() < 0.5:
        return f"{rnd.choice(FIRST_M)} {surname}"
    return f"{rnd.choice(FIRST_F)} {surname}а"


def _amount(rnd: random.Random, lo: int, hi: int) -> int:
    return 0 if hi == 0 else round(rnd.randint(lo, hi), -3)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _seed_one(conn, rnd: random.Random, idx: int, now: datetime, age_days: float) -> None:
    source = rnd.choices(list(SOURCE_WEIGHTS), weights=list(SOURCE_WEIGHTS.values()))[0]
    request, lo, hi = rnd.choice(REQUESTS)
    created = now - timedelta(days=age_days, minutes=rnd.randint(0, 600))
    lead = repo.create_lead(
        conn,
        {
            "name": _person(rnd),
            "phone": f"+7 900 000-{idx // 100:02d}-{idx % 100:02d}",
            "email": f"demo{idx:02d}@example.com" if rnd.random() < 0.4 else "",
            "request": request,
            "source": source,
            "amount": _amount(rnd, lo, hi),
            "manager": rnd.choice(MANAGERS),
            "created_at": _iso(created),
        },
        author={"site": "Форма на сайте", "telegram": "Telegram-бот", "avito": "Авито"}[source],
        note="Заявка получена",
    )
    lead_id, manager = lead["id"], lead["manager"]
    if age_days < 7 and rnd.random() < 0.75:
        return  # fresh lead, still "Новая"

    t = created + timedelta(hours=rnd.uniform(0.3, 20))
    repo.change_status(conn, lead_id, "in_progress", manager, at=_iso(min(t, now)))
    if rnd.random() < 0.8:
        t += timedelta(hours=rnd.uniform(1, 30))
        repo.add_event(conn, lead_id, "comment", rnd.choice(COMMENTS), manager, at=_iso(min(t, now)))

    close_after = timedelta(days=rnd.uniform(2, 14))
    if created + close_after > now - timedelta(hours=6) or rnd.random() < 0.12:
        return  # still in work
    t = created + close_after
    if rnd.random() < WIN_RATE[source] and lead["amount"] > 0:
        repo.add_event(conn, lead_id, "comment", "Предоплата получена, запускаем в производство.", manager, at=_iso(t))
        repo.change_status(conn, lead_id, "paid", manager, at=_iso(t + timedelta(minutes=5)))
    else:
        repo.add_event(conn, lead_id, "comment", rnd.choice(LOST_REASONS), manager, at=_iso(t))
        repo.change_status(conn, lead_id, "lost", manager, at=_iso(t + timedelta(minutes=5)))


def seed(count: int = 40, rnd_seed: int = 7) -> None:
    path = db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            candidate.unlink()
    init_db()
    rnd = random.Random(rnd_seed)
    now = datetime.now().replace(microsecond=0)
    with connect() as conn:
        ages = sorted((rnd.uniform(0.1, 68) for _ in range(count)), reverse=True)
        for idx, age in enumerate(ages, start=1):
            _seed_one(conn, rnd, idx, now, age)
    print(f"Готово: {count} демо-заявок в {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    seed(args.count, args.seed)
