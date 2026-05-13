"""
Procurement Global v1.6 — Поиск поставщиков
Надёжный поиск через DuckDuckGo + специализированные B2B сайты
"""
import asyncio, re, sys
import httpx
from urllib.parse import quote_plus, urlparse
from typing import List, Optional
from dataclasses import dataclass

# selectolax может не быть в некоторых сборках — используем fallback
try:
    from selectolax.parser import HTMLParser
    HAS_SELECTOLAX = True
except ImportError:
    HAS_SELECTOLAX = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}
TIMEOUT = 25


@dataclass
class Listing:
    title:       str
    price:       float
    currency:    str
    seller_name: str = ""
    address:     str = ""
    url:         str = ""
    source:      str = ""


def clean_price(s: str) -> Optional[float]:
    if not s: return None
    s = re.sub(r"[^\d.,]", "", str(s)).replace(",", ".")
    if s.count(".") > 1:
        p = s.split("."); s = "".join(p[:-1]) + "." + p[-1]
    try:
        v = float(s); return v if v > 0 else None
    except: return None


def ct(t: str) -> str:
    return " ".join(str(t).split()) if t else ""


async def fetch(url: str, params: dict = None) -> Optional[str]:
    """Загрузка HTML с обработкой всех ошибок"""
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers=HEADERS,
            verify=False,
        ) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.text
            print(f"HTTP {r.status_code}: {url}", file=sys.stderr)
    except Exception as e:
        print(f"Fetch error {url}: {e}", file=sys.stderr)
    return None


def parse_html(html: str, selector: str) -> list:
    """Парсинг HTML — с selectolax или через regex fallback"""
    if HAS_SELECTOLAX:
        tree = HTMLParser(html)
        return tree.css(selector)
    return []


def get_text(node) -> str:
    """Получить текст из узла"""
    if node is None: return ""
    try: return ct(node.text())
    except: return ""


def get_attr(node, attr: str) -> str:
    """Получить атрибут из узла"""
    if node is None: return ""
    try: return node.attributes.get(attr, "") or ""
    except: return ""


# ══════════════════════════════════════════════════════════════════
# НАСТРОЙКИ ПО СТРАНАМ
# ══════════════════════════════════════════════════════════════════
COUNTRY_CFG = {
    "UZ": {
        "cur": "UZS", "min": 1000,
        "queries": [
            "{q} {r} цена сум купить glotr.uz OR prom.uz OR olx.uz",
            "{q} {r} поставщик Узбекистан Ташкент цена оптом",
            "{q} купить цена сум Узбекистан",
        ]
    },
    "AZ": {
        "cur": "AZN", "min": 1,
        "queries": [
            "{q} {r} qiymət almaq tap.az OR lalafo.az",
            "{q} {r} Azərbaycan Bakı qiymət satış tedarikçi",
            "{q} Azərbaycan qiymət almaq",
        ]
    },
    "KZ": {
        "cur": "KZT", "min": 100,
        "queries": [
            "{q} {r} цена тенге купить olx.kz OR satu.kz",
            "{q} {r} Казахстан Алматы поставщик цена",
            "{q} купить цена тенге Казахстан",
        ]
    },
    "KG": {
        "cur": "KGS", "min": 10,
        "queries": [
            "{q} {r} цена сом купить lalafo.kg OR olx.kg",
            "{q} Кыргызстан Бишкек поставщик цена",
            "{q} купить Кыргызстан цена",
        ]
    },
    "TJ": {
        "cur": "TJS", "min": 1,
        "queries": [
            "{q} {r} Таджикистан Душанбе купить цена",
            "{q} Таджикистан поставщик цена",
        ]
    },
    "TM": {
        "cur": "TMT", "min": 1,
        "queries": [
            "{q} Туркменистан Ашхабад купить цена",
            "{q} Turkmenistan price buy",
        ]
    },
    "RU": {
        "cur": "RUB", "min": 100,
        "queries": [
            "{q} {r} цена рубль купить avito.ru OR pulscen.ru OR tiu.ru",
            "{q} {r} Россия поставщик цена оптом",
            "{q} купить цена рубль Россия",
        ]
    },
    "TR": {
        "cur": "TRY", "min": 1,
        "queries": [
            "{q} {r} fiyat satın al sahibinden.com",
            "{q} Türkiye tedarikçi fiyat",
            "{q} Turkey price supplier",
        ]
    },
    "CN": {
        "cur": "CNY", "min": 1,
        "queries": [
            "{q} China supplier price wholesale alibaba.com",
            "{q} China manufacturer price buy",
        ]
    },
    "AE": {
        "cur": "AED", "min": 1,
        "queries": [
            "{q} UAE Dubai supplier price dubizzle.com",
            "{q} Dubai price buy supplier",
        ]
    },
    "DE": {
        "cur": "EUR", "min": 1,
        "queries": [
            "{q} Deutschland Preis kaufen Lieferant",
            "{q} Germany supplier price buy",
        ]
    },
    "GB": {
        "cur": "GBP", "min": 1,
        "queries": [
            "{q} UK supplier price buy gumtree.com",
            "{q} United Kingdom price wholesale",
        ]
    },
    "US": {
        "cur": "USD", "min": 1,
        "queries": [
            "{q} USA supplier price buy wholesale",
            "{q} United States price manufacturer",
        ]
    },
    "PL": {
        "cur": "PLN", "min": 1,
        "queries": [
            "{q} Polska cena kupić dostawca olx.pl",
            "{q} Poland price supplier buy",
        ]
    },
    "GE": {
        "cur": "GEL", "min": 1,
        "queries": [
            "{q} Georgia Tbilisi price buy mymarket.ge OR livo.ge",
            "{q} Gruziya Tbilisi qiymət almaq",
        ]
    },
    "AM": {
        "cur": "AMD", "min": 1,
        "queries": [
            "{q} Армения Ереван купить цена list.am OR olx.am",
            "{q} Armenia Yerevan price buy",
        ]
    },
}


def _detect_cur(text: str, default: str) -> str:
    up = text.upper()
    if "$" in text or "USD" in up: return "USD"
    if "€" in text or "EUR" in up: return "EUR"
    if "₽" in text or "RUB" in up or "РУБ" in up: return "RUB"
    if "₸" in text or "KZT" in up or "ТЕНГЕ" in up: return "KZT"
    if "₼" in text or "AZN" in up or "МАНАТ" in up: return "AZN"
    if "СУМ" in up or "UZS" in up or "SO'M" in up: return "UZS"
    if "₾" in text or "GEL" in up: return "GEL"
    if "AMD" in up or "ДРАМ" in up: return "AMD"
    return default


def _extract_price(text: str, min_p: float) -> Optional[float]:
    """Извлекает цену из текста — множество паттернов"""
    # Ищем числа с разделителями тысяч (1 000 000 или 1,000,000)
    patterns = [
        r'(\d[\d\s]{2,12}\d)[.,](\d{2})\b',   # 45 000,00
        r'(\d[\d\s]{1,12}\d)\s*(?:сум|sum|uzs|som|so\'m)',
        r'(\d[\d\s]{1,12}\d)\s*(?:тенге|kzt)',
        r'(\d[\d\s]{1,12}\d)\s*(?:руб|rub)',
        r'(\d[\d\s]{1,10}\d)\s*(?:azn|manat)',
        r'(\d+[.,]\d{2})\s*(?:\$|usd|€|eur|£|gbp)',
        r'(?:цена|price|qiymət|fiyat|koszt)[:\s]+(\d[\d\s]{1,10}\d)',
        r'(\d[\d\s]{2,12}\d)',  # любое многозначное число
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = re.sub(r'\s', '', m.group(1))
            if len(m.groups()) > 1 and m.lastindex and m.lastindex >= 2:
                try: raw += "." + m.group(2)
                except: pass
            p = clean_price(raw)
            if p and p >= min_p:
                return p
    return None


async def search_ddg_query(query: str, cur: str, min_p: float) -> List[Listing]:
    """Один запрос в DuckDuckGo"""
    html = await fetch("https://html.duckduckgo.com/html", params={"q": query})
    if not html:
        return []

    results: List[Listing] = []

    if HAS_SELECTOLAX:
        tree = HTMLParser(html)
        for r in tree.css(".result__body")[:20]:
            try:
                t_node = r.css_first(".result__title a")
                if not t_node: continue
                title = get_text(t_node)
                href  = get_attr(t_node, "href")
                if not title or not href: continue

                sn = r.css_first(".result__snippet")
                snippet = get_text(sn) if sn else ""
                full_text = f"{title} {snippet}"

                price = _extract_price(full_text, min_p)
                if not price: continue

                domain = urlparse(href).netloc.replace("www.", "") or "unknown"
                results.append(Listing(
                    title=title, price=price,
                    currency=_detect_cur(full_text, cur),
                    seller_name=domain,
                    address=snippet[:150],
                    url=href,
                    source=f"web ({domain})"
                ))
            except Exception as e:
                print(f"Parse error: {e}", file=sys.stderr)
    else:
        # Fallback: regex парсинг без selectolax
        links = re.findall(
            r'class="result__title"[^>]*>.*?href="([^"]+)"[^>]*>([^<]+)',
            html, re.DOTALL
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>([^<]+)', html
        )
        for i, (href, title) in enumerate(links[:15]):
            snippet = snippets[i] if i < len(snippets) else ""
            full_text = f"{title} {snippet}"
            price = _extract_price(full_text, min_p)
            if not price: continue
            domain = urlparse(href).netloc.replace("www.", "") or "unknown"
            results.append(Listing(
                title=ct(title), price=price,
                currency=_detect_cur(full_text, cur),
                seller_name=domain,
                address=ct(snippet)[:150],
                url=href,
                source=f"web ({domain})"
            ))

    return results


# ══════════════════════════════════════════════════════════════════
# СПЕЦИАЛИЗИРОВАННЫЕ СКРАПЕРЫ UZ
# ══════════════════════════════════════════════════════════════════
async def scrape_glotr(query: str) -> List[Listing]:
    html = await fetch("https://glotr.uz/search/", params={"q": query})
    if not html or not HAS_SELECTOLAX: return []
    tree = HTMLParser(html)
    out = []
    for card in tree.css("[class*='product'], [class*='item']")[:15]:
        try:
            t = card.css_first("[class*='title'] a, h3 a, a.title")
            title = get_text(t)
            if not title or len(title) < 3: continue
            p = card.css_first("[class*='price']")
            price = clean_price(get_text(p)) if p else None
            if not price or price < 1000: continue
            link = card.css_first("a")
            href = get_attr(link, "href")
            url = href if href.startswith("http") else f"https://glotr.uz{href}"
            out.append(Listing(
                title=title, price=price, currency="UZS",
                seller_name="glotr.uz", url=url, source="glotr.uz"
            ))
        except Exception: continue
    return out


async def scrape_prom_uz(query: str) -> List[Listing]:
    html = await fetch(f"https://prom.uz/search/?search_term={quote_plus(query)}")
    if not html or not HAS_SELECTOLAX: return []
    tree = HTMLParser(html)
    out = []
    for card in tree.css("[data-qaid='product_block'], [class*='product']")[:15]:
        try:
            t = card.css_first("[data-qaid='product_name'], a[class*='name']")
            title = get_text(t)
            if not title or len(title) < 3: continue
            p = card.css_first("[data-qaid='price'], [class*='price']")
            price = clean_price(get_text(p)) if p else None
            if not price or price < 1000: continue
            link = card.css_first("a")
            href = get_attr(link, "href")
            url = href if href.startswith("http") else f"https://prom.uz{href}"
            out.append(Listing(
                title=title, price=price, currency="UZS",
                seller_name="prom.uz", url=url, source="prom.uz"
            ))
        except Exception: continue
    return out


# ══════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОРКЕСТРАТОР
# ══════════════════════════════════════════════════════════════════
async def search_all_sources(
    query: str, country: str = "UZ", region: str = ""
) -> List[Listing]:
    """
    Поиск поставщиков по всем источникам параллельно.
    Использует несколько запросов чтобы гарантированно найти результаты.
    """
    cfg = COUNTRY_CFG.get(country, COUNTRY_CFG["UZ"])
    cur = cfg["cur"]
    min_p = cfg["min"]
    region_str = region or ""

    # Формируем запросы с подстановкой товара и региона
    queries = []
    for tmpl in cfg["queries"]:
        q = tmpl.replace("{q}", query).replace("{r}", region_str)
        queries.append(q)

    # Запускаем DDG-запросы параллельно
    ddg_tasks = [search_ddg_query(q, cur, min_p) for q in queries]

    # Для Узбекистана добавляем специализированные скраперы
    extra_tasks = []
    if country == "UZ":
        extra_tasks = [scrape_glotr(query), scrape_prom_uz(query)]

    all_tasks = ddg_tasks + extra_tasks
    all_results: List[Listing] = []

    scraped = await asyncio.gather(*all_tasks, return_exceptions=True)
    for r in scraped:
        if isinstance(r, list):
            all_results.extend(r)
        elif isinstance(r, Exception):
            print(f"Source error: {r}", file=sys.stderr)

    # Убираем дубликаты по URL
    seen_urls = set()
    unique = []
    for item in all_results:
        if item.url not in seen_urls:
            seen_urls.add(item.url)
            unique.append(item)

    print(f"Найдено: {len(unique)} объявлений для '{query}'", file=sys.stderr)
    return unique
