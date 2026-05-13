"""
Классификация поставщиков: дешёвый / средний / дорогой
с умной фильтрацией аномалий и нерелевантных результатов
"""
import re, sys
from typing import List
from dataclasses import dataclass, asdict
from scrapers import Listing


@dataclass
class Supplier:
    tier:             str
    supplier_name:    str
    supplier_address: str
    supplier_phone:   str
    supplier_website: str
    price_per_unit:   float
    total:            float
    source:           str

    def dict(self):
        return asdict(self)


def tokenize(text: str) -> set:
    return set(w.lower() for w in re.findall(r'[а-яёa-z0-9]{2,}', text.lower()))


def relevance_score(listing: Listing, query: str) -> int:
    query_words = tokenize(query)
    title_words = tokenize(listing.title + " " + listing.address)
    return len(query_words & title_words)


def filter_anomalies(listings: List[Listing]) -> List[Listing]:
    """Убирает цены-выбросы (> медианы × 10)"""
    if len(listings) < 2:
        return listings
    prices = sorted(l.price for l in listings)
    median = prices[len(prices) // 2]
    threshold = median * 10
    filtered = [l for l in listings if l.price <= threshold]
    return filtered if filtered else listings


def classify_suppliers(
    listings: List[Listing], qty: float, query: str = ""
) -> List[Supplier]:
    if not listings:
        return []

    # Фильтр по релевантности
    if query:
        scored = [(relevance_score(l, query), l) for l in listings]
        scored.sort(key=lambda x: -x[0])
        # Берём только релевантные (score > 0), иначе всё
        relevant = [l for s, l in scored if s > 0]
        if len(relevant) >= 1:
            listings = relevant
        else:
            # Ничего не совпало — берём всё что есть
            listings = [l for _, l in scored]

    # Фильтр нулевых цен
    valid = [l for l in listings if l.price and l.price > 0]
    if not valid:
        return []

    # Убираем аномалии
    valid = filter_anomalies(valid)
    valid.sort(key=lambda x: x.price)

    n = len(valid)
    suppliers = []

    suppliers.append(_make(valid[0], "cheap", qty))
    if n >= 3:
        suppliers.append(_make(valid[n // 2], "mid", qty))
        suppliers.append(_make(valid[-1], "exp", qty))
    elif n == 2:
        suppliers.append(_make(valid[-1], "exp", qty))

    print(f"Классифицировано: {len(suppliers)} поставщиков из {n} объявлений", file=sys.stderr)
    return suppliers


def _make(l: Listing, tier: str, qty: float) -> Supplier:
    return Supplier(
        tier=tier,
        supplier_name=l.seller_name or l.source or "Не указано",
        supplier_address=l.address or "",
        supplier_phone="",
        supplier_website=l.url or "",
        price_per_unit=round(l.price, 2),
        total=round(l.price * qty, 2),
        source=l.source,
    )
