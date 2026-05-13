"""
Поиск поставщиков через специализированные B2B-сайты и веб-поиск.
Основной принцип: ищем конкретный товар на специализированных площадках,
а не на OLX где продают всё подряд.
"""
import asyncio
import httpx
import re
from urllib.parse import quote_plus, urlparse
from typing import List, Optional
from dataclasses import dataclass
from selectolax.parser import HTMLParser


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,uz;q=0.8,en;q=0.7",
}

TIMEOUT = 15


@dataclass
class Listing:
    title: str
    price: float
    currency: str
    seller_name: str = ""
    address: str = ""
    url: str = ""
    source: str = ""


def clean_price(s: str) -> Optional[float]:
    if not s:
        return None
    cleaned = re.sub(r'[^\d.,]', '', s).replace(',', '.')
    if cleaned.count('.') > 1:
        parts = cleaned.split('.')
        cleaned = ''.join(parts[:-1]) + '.' + parts[-1]
    try:
        v = float(cleaned)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def clean_text(t: Optional[str]) -> str:
    return ' '.join(t.split()) if t else ''


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace('www.', '')
    except Exception:
        return 'unknown'


async def fetch(url: str, params: dict = None) -> Optional[str]:
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True,
            headers=HEADERS, verify=False
        ) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.text
    except Exception as e:
        print(f'⚠ fetch {url}: {e}')
    return None


# ═══════════════════════════════════════════════════════════════
# GLOTR.UZ — B2B каталог поставщиков Узбекистана
# ═══════════════════════════════════════════════════════════════
async def scrape_glotr(query: str) -> List[Listing]:
    html = await fetch('https://glotr.uz/search/', params={'q': query})
    if not html:
        return []
    tree = HTMLParser(html)
    results = []
    for card in tree.css('.b-product-list__item, .product-card, [class*="product-item"]')[:20]:
        try:
            t = card.css_first('a.title, .product-title, h3 a, .name a, a[class*="title"]')
            title = clean_text(t.text()) if t else ''
            if not title or len(title) < 3:
                continue
            p = card.css_first('[class*="price"]')
            price = clean_price(p.text()) if p else None
            if not price or price < 100:
                continue
            link = card.css_first('a')
            href = link.attributes.get('href', '') if link else ''
            url = href if href.startswith('http') else f'https://glotr.uz{href}'
            seller = card.css_first('.company-name, .seller, .b-company-info')
            results.append(Listing(
                title=title, price=price, currency='UZS',
                seller_name=clean_text(seller.text()) if seller else 'glotr.uz',
                url=url, source='glotr.uz'
            ))
        except Exception:
            continue
    return results


# ═══════════════════════════════════════════════════════════════
# PROM.UZ — промышленный каталог
# ═══════════════════════════════════════════════════════════════
async def scrape_prom_uz(query: str) -> List[Listing]:
    html = await fetch(f'https://prom.uz/search/?search_term={quote_plus(query)}')
    if not html:
        return []
    tree = HTMLParser(html)
    results = []
    for card in tree.css('[data-qaid="product_block"], .js-productad, [class*="product"]')[:20]:
        try:
            t = card.css_first('[data-qaid="product_name"], a[class*="name"], h3 a')
            title = clean_text(t.text()) if t else ''
            if not title or len(title) < 3:
                continue
            p = card.css_first('[data-qaid="price"], [class*="price"]')
            price = clean_price(p.text()) if p else None
            if not price or price < 100:
                continue
            link = card.css_first('a')
            href = link.attributes.get('href', '') if link else ''
            url = href if href.startswith('http') else f'https://prom.uz{href}'
            seller = card.css_first('[data-qaid="company_name"], .company-name')
            results.append(Listing(
                title=title, price=price, currency='UZS',
                seller_name=clean_text(seller.text()) if seller else 'prom.uz',
                url=url, source='prom.uz'
            ))
        except Exception:
            continue
    return results


# ═══════════════════════════════════════════════════════════════
# OLX.UZ — с жёсткой фильтрацией по категории
# (используем только категорию "стройматериалы")
# ═══════════════════════════════════════════════════════════════
async def scrape_olx_uz_category(query: str) -> List[Listing]:
    """OLX только в категории stroymaterialy"""
    url = f'https://www.olx.uz/stroymaterialy/q-{quote_plus(query)}/'
    html = await fetch(url)
    if not html:
        # Fallback: общий поиск OLX но только бизнес-объявления
        url = f'https://www.olx.uz/list/q-{quote_plus(query)}/?search[filter_enum_type][0]=business'
        html = await fetch(url)
    if not html:
        return []

    tree = HTMLParser(html)
    results = []
    for card in tree.css('div[data-cy="l-card"]')[:25]:
        try:
            t = card.css_first('h4, h6, [data-cy="ad-card-title"]')
            title = clean_text(t.text()) if t else ''
            if not title or len(title) < 3:
                continue

            p = card.css_first('p[data-testid="ad-price"], [data-cy="ad-price"]')
            price_text = p.text() if p else ''
            price = clean_price(price_text)
            if not price or price < 1000:  # минимум 1000 сум — отсекаем явный мусор
                continue

            link = card.css_first('a')
            href = link.attributes.get('href', '') if link else ''
            full_url = href if href.startswith('http') else f'https://www.olx.uz{href}'

            loc = card.css_first('p[data-testid="location-date"]')
            location = clean_text(loc.text()) if loc else ''

            results.append(Listing(
                title=title, price=price,
                currency='USD' if '$' in price_text else 'UZS',
                address=location, url=full_url, source='olx.uz'
            ))
        except Exception:
            continue
    return results


# ═══════════════════════════════════════════════════════════════
# UNIVERSAL WEB SEARCH — ищем по специализированным сайтам
# ═══════════════════════════════════════════════════════════════

# Специализированные сайты по странам
SUPPLIER_SITES = {
    'UZ': [
        'glotr.uz', 'prom.uz', 'stroyka.uz', 'pulscen.uz',
        'uzbuilding.uz', 'tmsearch.uz', 'uztrade.uz'
    ],
    'AZ': ['tap.az', 'lalafo.az', 'azexport.az', 'made-in-azerbaijan.com'],
    'KZ': ['satu.kz', 'olx.kz', 'kaspi.kz', 'pulscen.kz'],
    'KG': ['lalafo.kg', 'sargalama.kg'],
    'RU': ['avito.ru', 'pulscen.ru', 'tiu.ru', 'satu.kz'],
    'TR': ['sahibinden.com', 'hepsiburada.com'],
}

COUNTRY_CURRENCY = {
    'UZ': 'UZS', 'AZ': 'AZN', 'KZ': 'KZT', 'KG': 'KGS',
    'TJ': 'TJS', 'TM': 'TMT', 'RU': 'RUB', 'TR': 'TRY',
    'CN': 'CNY', 'DE': 'EUR', 'US': 'USD', 'AE': 'AED',
    'GB': 'GBP', 'PL': 'PLN', 'GE': 'GEL', 'AM': 'AMD',
}

COUNTRY_HINT = {
    'UZ': 'Узбекистан купить цена сум оптом',
    'AZ': 'Azərbaycan qiymət almaq',
    'KZ': 'Казахстан купить цена тенге',
    'KG': 'Кыргызстан купить цена сом',
    'TJ': 'Таджикистан купить цена',
    'TM': 'Туркменистан купить цена',
    'RU': 'Россия купить цена оптом рубль',
    'TR': 'Türkiye satın al fiyat',
    'CN': 'China supplier price buy',
    'DE': 'Deutschland kaufen Preis',
    'US': 'USA buy price supplier',
    'AE': 'UAE Dubai buy price',
    'GB': 'UK buy supplier price',
    'PL': 'Polska kupić cena',
    'GE': 'Georgia buy price supplier',
    'AM': 'Armenia buy price supplier',
}


async def search_web(query: str, country: str, region: str) -> List[Listing]:
    """
    Поиск через DuckDuckGo с фокусом на специализированных поставщиков.
    Ищет по конкретным сайтам-поставщикам.
    """
    sites = SUPPLIER_SITES.get(country, [])
    default_cur = COUNTRY_CURRENCY.get(country, 'USD')
    hint = COUNTRY_HINT.get(country, '')
    region_hint = region if region else ''

    results = []

    # Запрос 1: поиск по специализированным сайтам
    if sites:
        site_filter = ' OR '.join(f'site:{s}' for s in sites[:4])
        full_query = f'{query} {region_hint} ({site_filter})'
        r = await _ddg_search(full_query, default_cur)
        results.extend(r)

    # Запрос 2: общий поиск с контекстом страны
    if len(results) < 3:
        full_query = f'{query} поставщик {region_hint} {hint} цена'
        r = await _ddg_search(full_query, default_cur)
        results.extend(r)

    return results


async def _ddg_search(query: str, default_cur: str) -> List[Listing]:
    """Внутренний поиск через DuckDuckGo HTML"""
    html = await fetch('https://html.duckduckgo.com/html', params={'q': query})
    if not html:
        return []

    tree = HTMLParser(html)
    results = []

    for r in tree.css('.result__body')[:15]:
        try:
            t = r.css_first('.result__title a')
            if not t:
                continue
            title = clean_text(t.text())
            href = t.attributes.get('href', '')
            if not title or not href:
                continue

            sn = r.css_first('.result__snippet')
            snippet = clean_text(sn.text()) if sn else ''

            # Ищем цену в сниппете
            price = _extract_price(snippet, default_cur)
            if not price:
                continue

            domain = extract_domain(href)
            results.append(Listing(
                title=title, price=price,
                currency=_detect_currency(snippet, default_cur),
                seller_name=domain,
                address=snippet[:150],
                url=href,
                source=f'web ({domain})'
            ))
        except Exception:
            continue

    return results


def _extract_price(text: str, currency: str) -> Optional[float]:
    """Извлекает цену из текста, учитывая масштаб валюты"""
    # Паттерны цен: 45 000, 45.000, 45,000 и т.д.
    patterns = [
        r'(\d[\d\s]{1,12}\d)\s*(?:сум|sum|uzs|so\'m)',
        r'(\d[\d\s]{1,12}\d)\s*(?:тенге|kzt|₸)',
        r'(\d[\d\s]{1,12}\d)\s*(?:руб|rub|₽)',
        r'(\d[\d\s]{1,12}\d)\s*(?:azn|ман|manat|₼)',
        r'(\d+[.,]\d+)\s*(?:\$|usd)',
        r'(\d[\d\s]{2,12}\d)',  # любое многозначное число
    ]

    min_price = {
        'UZS': 5000, 'KZT': 100, 'RUB': 10,
        'AZN': 1, 'USD': 1, 'EUR': 1,
    }.get(currency, 1)

    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            raw = re.sub(r'\s', '', m.group(1))
            price = clean_price(raw)
            if price and price >= min_price:
                return price
    return None


def _detect_currency(text: str, default: str) -> str:
    text_up = text.upper()
    if '$' in text or 'USD' in text_up: return 'USD'
    if '€' in text or 'EUR' in text_up: return 'EUR'
    if '₽' in text or 'RUB' in text_up or 'РУБ' in text_up: return 'RUB'
    if '₸' in text or 'KZT' in text_up or 'ТЕНГЕ' in text_up: return 'KZT'
    if '₼' in text or 'AZN' in text_up or 'МАНАТ' in text_up: return 'AZN'
    if 'СУМ' in text_up or 'UZS' in text_up or "SO'M" in text_up: return 'UZS'
    return default


# ═══════════════════════════════════════════════════════════════
# ОРКЕСТРАТОР
# ═══════════════════════════════════════════════════════════════
async def search_all_sources(
    query: str, country: str = 'UZ', region: str = ''
) -> List[Listing]:
    """
    Запускает поиск по всем источникам параллельно.
    Для Узбекистана: Glotr + Prom.uz + OLX (категория) + веб-поиск
    Для других стран: веб-поиск по специализированным сайтам
    """
    tasks = []

    if country == 'UZ':
        tasks = [
            scrape_glotr(query),
            scrape_prom_uz(query),
            scrape_olx_uz_category(query),
            search_web(query, country, region),
        ]
    elif country in ('AZ', 'KZ', 'KG', 'RU', 'TR'):
        tasks = [
            search_web(query, country, region),
        ]
    else:
        tasks = [
            search_web(query, country, region),
        ]

    all_results: List[Listing] = []
    scraped = await asyncio.gather(*tasks, return_exceptions=True)
    for r in scraped:
        if isinstance(r, list):
            all_results.extend(r)
        elif isinstance(r, Exception):
            print(f'⚠ Source failed: {r}')

    return all_results
