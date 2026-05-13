"""
Классификация поставщиков на дешёвый/средний/дорогой.
Строгая фильтрация по релевантности и аномальным ценам.
"""
import re
from typing import List
from dataclasses import dataclass, asdict
from scrapers import Listing


@dataclass
class Supplier:
    tier: str
    supplier_name: str
    supplier_address: str
    supplier_phone: str
    supplier_website: str
    price_per_unit: float
    total: float
    source: str

    def dict(self):
        return asdict(self)


def tokenize(text: str) -> set:
    """Разбить текст на слова (только кириллица/латиница длиннее 2 букв)"""
    return set(w.lower() for w in re.findall(r'[а-яёa-z]{3,}', text.lower()))


def relevance_score(listing: Listing, query: str) -> int:
    """
    Считает сколько слов запроса есть в названии объявления.
    0 = нерелевантно, >0 = релевантно.
    """
    query_words = tokenize(query)
    title_words = tokenize(listing.title)
    # Хотя бы одно ключевое слово из запроса должно быть в названии
    common = query_words & title_words
    return len(common)


def filter_anomalies(listings: List[Listing]) -> List[Listing]:
    """
    Убирает аномально высокие цены.
    Алгоритм: медиана * 10 = максимально допустимая цена.
    """
    if len(listings) < 2:
        return listings
    prices = sorted(l.price for l in listings)
    median = prices[len(prices) // 2]
    # Максимум в 10 раз выше медианы (раньше было 100 — слишком мягко)
    threshold = median * 10
    filtered = [l for l in listings if l.price <= threshold]
    return filtered if len(filtered) >= 1 else listings[:1]


def classify_suppliers(
    listings: List[Listing], qty: float, query: str = ""
) -> List[Supplier]:
    """
    Основная функция классификации.
    1. Фильтрует нерелевантные объявления по ключевым словам
    2. Убирает аномальные цены
    3. Выбирает 3 представителя: дешёвый / средний / дорогой
    """
    if not listings:
        return []

    # Шаг 1: фильтр по релевантности (строгий)
    if query:
        scored = [(relevance_score(l, query), l) for l in listings]
        # Берём только те у которых хотя бы 1 слово совпадает
        relevant = [l for score, l in scored if score > 0]
        if len(relevant) >= 1:
            listings = relevant
        # Если ничего не совпало — берём всё (лучше что-то чем ничего)

    # Шаг 2: убираем нулевые и отрицательные цены
    valid = [l for l in listings if l.price and l.price > 0]
    if not valid:
        return []

    # Шаг 3: убираем аномальные цены
    valid = filter_anomalies(valid)
    valid.sort(key=lambda x: x.price)

    n = len(valid)
    suppliers = []

    # Дешёвый — самая низкая цена
    suppliers.append(_to_supplier(valid[0], 'cheap', qty))

    if n >= 3:
        # Средний — медианный
        suppliers.append(_to_supplier(valid[n // 2], 'mid', qty))
        # Дорогой — самая высокая (после фильтрации аномалий)
        suppliers.append(_to_supplier(valid[-1], 'exp', qty))
    elif n == 2:
        suppliers.append(_to_supplier(valid[-1], 'exp', qty))

    return suppliers


def _to_supplier(l: Listing, tier: str, qty: float) -> Supplier:
    return Supplier(
        tier=tier,
        supplier_name=l.seller_name or l.source or 'Не указано',
        supplier_address=l.address or '',
        supplier_phone='',
        supplier_website=l.url or '',
        price_per_unit=round(l.price, 2),
        total=round(l.price * qty, 2),
        source=l.source,
    )
