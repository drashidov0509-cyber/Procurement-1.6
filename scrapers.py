"""
Procurement Global v1.6 — Поиск поставщиков
Стратегия: специализированные B2B сайты + веб-поиск через DuckDuckGo
"""
import asyncio, re
import httpx
from urllib.parse import quote_plus, urlparse
from typing import List, Optional
from dataclasses import dataclass
from selectolax.parser import HTMLParser

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
}
TIMEOUT = 20


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
    s = re.sub(r"[^\d.,]", "", s).replace(",", ".")
    if s.count(".") > 1:
        p = s.split("."); s = "".join(p[:-1]) + "." + p[-1]
    try:
        v = float(s); return v if v > 0 else None
    except: return None


def ct(t): return " ".join(t.split()) if t else ""


async def fetch(url: str, params=None) -> Optional[str]:
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True,
            headers=HEADERS, verify=False
        ) as c:
            r = await c.get(url, params=params)
            return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"⚠ fetch {url}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# УНИВЕРСАЛЬНЫЙ ПОИСК ЧЕРЕЗ DUCKDUCKGO
# Работает для ВСЕХ стран без ограничений
# ══════════════════════════════════════════════════════════════════
COUNTRY_CFG = {
    "UZ": {"cur":"UZS","hint":"Узбекистан купить цена сум поставщик","min":5000,
           "sites":"glotr.uz OR prom.uz OR olx.uz OR stroyka.uz"},
    "AZ": {"cur":"AZN","hint":"Azərbaycan Bakı qiymət satış","min":1,
           "sites":"tap.az OR lalafo.az OR azexport.az OR olx.az"},
    "KZ": {"cur":"KZT","hint":"Казахстан купить цена тенге поставщик","min":100,
           "sites":"olx.kz OR satu.kz OR kaspi.kz"},
    "KG": {"cur":"KGS","hint":"Кыргызстан купить цена сом","min":10,
           "sites":"lalafo.kg OR olx.kg"},
    "TJ": {"cur":"TJS","hint":"Таджикистан Душанбе купить цена","min":1,
           "sites":""},
    "TM": {"cur":"TMT","hint":"Туркменистан Ашхабад купить цена","min":1,
           "sites":""},
    "RU": {"cur":"RUB","hint":"Россия купить цена рубль поставщик оптом","min":100,
           "sites":"avito.ru OR pulscen.ru OR tiu.ru"},
    "TR": {"cur":"TRY","hint":"Türkiye satın al fiyat tedarikçi","min":1,
           "sites":"sahibinden.com OR hepsiburada.com"},
    "CN": {"cur":"CNY","hint":"China supplier price buy wholesale","min":1,
           "sites":"alibaba.com OR made-in-china.com"},
    "AE": {"cur":"AED","hint":"UAE Dubai supplier price buy","min":1,
           "sites":"dubizzle.com OR yellowpages.ae"},
    "DE": {"cur":"EUR","hint":"Deutschland kaufen Preis Lieferant","min":1,
           "sites":"ebay-kleinanzeigen.de OR mercateo.de"},
    "GB": {"cur":"GBP","hint":"UK supplier price buy wholesale","min":1,
           "sites":"gumtree.com OR thomasnet.com"},
    "US": {"cur":"USD","hint":"USA supplier price buy wholesale","min":1,
           "sites":"thomasnet.com OR globalspec.com"},
    "PL": {"cur":"PLN","hint":"Polska kupić cena dostawca","min":1,
           "sites":"olx.pl OR allegro.pl"},
    "GE": {"cur":"GEL","hint":"საქართველო ფასი შეძენა","min":1,
           "sites":"mymarket.ge OR livo.ge"},
    "AM": {"cur":"AMD","hint":"Армения Ереван купить цена","min":1,
           "sites":"list.am OR olx.am"},
}


async def search_ddg(query: str, country: str, region: str) -> List[Listing]:
    """Поиск через DuckDuckGo — работает для всех стран"""
    cfg = COUNTRY_CFG.get(country, {"cur":"USD","hint":"buy price supplier","min":1,"sites":""})
    cur = cfg["cur"]
    min_price = cfg["min"]
    results: List[Listing] = []

    # Запрос 1: по специализированным сайтам страны
    if cfg["sites"]:
        q1 = f"{query} {region} ({cfg['sites']}) цена"
        r1 = await _ddg(q1, cur, min_price)
        results.extend(r1)

    # Запрос 2: общий с контекстом страны
    if len(results) < 3:
        q2 = f"{query} {region} {cfg['hint']}"
        r2 = await _ddg(q2, cur, min_price)
        results.extend(r2)

    # Запрос 3: ещё более широкий если совсем ничего
    if len(results) < 2:
        q3 = f"{query} поставщик цена купить {region}"
        r3 = await _ddg(q3, cur, min_price)
        results.extend(r3)

    return results


async def _ddg(query: str, default_cur: str, min_price: float) -> List[Listing]:
    html = await fetch("https://html.duckduckgo.com/html", params={"q": query})
    if not html: return []
    tree = HTMLParser(html)
    results = []
    for r in tree.css(".result__body")[:20]:
        try:
            t = r.css_first(".result__title a")
            if not t: continue
            title = ct(t.text())
            href  = t.attributes.get("href","")
            if not title or not href: continue
            sn = r.css_first(".result__snippet")
            snippet = ct(sn.text()) if sn else ""
            price = _extract_price(snippet + " " + title, default_cur, min_price)
            if not price: continue
            domain = urlparse(href).netloc.replace("www.","") or "unknown"
            results.append(Listing(
                title=title, price=price,
                currency=_detect_cur(snippet, default_cur),
                seller_name=domain,
                address=snippet[:120],
                url=href,
                source=f"web ({domain})"
            ))
        except Exception:
            continue
    return results


def _extract_price(text: str, currency: str, min_p: float) -> Optional[float]:
    patterns = [
        r"(\d[\d\s]{1,10}\d)\s*(?:сум|sum|uzs|so[`']?m)",
        r"(\d[\d\s]{1,10}\d)\s*(?:тенге|kzt|₸)",
        r"(\d[\d\s]{1,10}\d)\s*(?:руб|rub|₽)",
        r"(\d[\d\s]{1,4}\d)[.,](\d{2})\s*(?:azn|ман|manat|₼)",
        r"(\d[\d\s]{1,4}\d)[.,](\d{2})\s*(?:\$|usd)",
        r"(\d[\d\s]{1,4}\d)[.,](\d{2})\s*(?:€|eur)",
        r"(\d[\d\s]{2,10}\d)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = re.sub(r"\s","", m.group(1))
            if len(m.groups()) > 1 and m.group(2):
                raw += "." + m.group(2)
            p = clean_price(raw)
            if p and p >= min_p:
                return p
    return None


def _detect_cur(text: str, default: str) -> str:
    up = text.upper()
    if "$" in text or "USD" in up: return "USD"
    if "€" in text or "EUR" in up: return "EUR"
    if "₽" in text or "RUB" in up or "РУБ" in up: return "RUB"
    if "₸" in text or "KZT" in up or "ТЕНГЕ" in up: return "KZT"
    if "₼" in text or "AZN" in up or "МАНАТ" in up: return "AZN"
    if "СУМ" in up or "UZS" in up or "SO'M" in up: return "UZS"
    if "₾" in text or "GEL" in up: return "GEL"
    return default


# ══════════════════════════════════════════════════════════════════
# СПЕЦИАЛИЗИРОВАННЫЕ СКРАПЕРЫ (Узбекистан)
# ══════════════════════════════════════════════════════════════════
async def scrape_glotr(query: str) -> List[Listing]:
    html = await fetch("https://glotr.uz/search/", params={"q": query})
    if not html: return []
    tree = HTMLParser(html)
    out = []
    for card in tree.css("[class*='product'], [class*='item'], [class*='card']")[:20]:
        try:
            t = card.css_first("a[class*='title'], h3 a, .name a, a.title")
            title = ct(t.text()) if t else ""
            if not title or len(title) < 3: continue
            p = card.css_first("[class*='price']")
            price = clean_price(p.text()) if p else None
            if not price or price < 100: continue
            link = card.css_first("a")
            href = link.attributes.get("href","") if link else ""
            url = href if href.startswith("http") else f"https://glotr.uz{href}"
            seller = card.css_first("[class*='company'], [class*='seller']")
            out.append(Listing(
                title=title, price=price, currency="UZS",
                seller_name=ct(seller.text()) if seller else "glotr.uz",
                url=url, source="glotr.uz"
            ))
        except Exception: continue
    return out


async def scrape_prom_uz(query: str) -> List[Listing]:
    html = await fetch(f"https://prom.uz/search/?search_term={quote_plus(query)}")
    if not html: return []
    tree = HTMLParser(html)
    out = []
    for card in tree.css("[data-qaid='product_block'], [class*='product']")[:20]:
        try:
            t = card.css_first("[data-qaid='product_name'], a[class*='name']")
            title = ct(t.text()) if t else ""
            if not title or len(title) < 3: continue
            p = card.css_first("[data-qaid='price'], [class*='price']")
            price = clean_price(p.text()) if p else None
            if not price or price < 100: continue
            link = card.css_first("a")
            href = link.attributes.get("href","") if link else ""
            url = href if href.startswith("http") else f"https://prom.uz{href}"
            seller = card.css_first("[data-qaid='company_name']")
            out.append(Listing(
                title=title, price=price, currency="UZS",
                seller_name=ct(seller.text()) if seller else "prom.uz",
                url=url, source="prom.uz"
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
    Параллельный поиск по всем источникам.
    Для UZ: Glotr + Prom + DuckDuckGo
    Для остальных: DuckDuckGo с 3 разными запросами
    """
    tasks = [search_ddg(query, country, region)]

    if country == "UZ":
        tasks += [scrape_glotr(query), scrape_prom_uz(query)]

    all_results: List[Listing] = []
    scraped = await asyncio.gather(*tasks, return_exceptions=True)
    for r in scraped:
        if isinstance(r, list):
            all_results.extend(r)
        elif isinstance(r, Exception):
            print(f"⚠ Source error: {r}")

    return all_results
