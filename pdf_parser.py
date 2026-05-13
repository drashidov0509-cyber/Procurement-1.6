"""
Умный парсер PDF для заявок и спецификаций ТМЦ.
Поддерживает: таблицы, текстовые списки, нумерованные позиции.
"""
import re
import sys

# Статический импорт для правильной упаковки PyInstaller
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
from typing import List, Optional


def parse_pdf(path: str) -> list:
    """
    Основная функция парсинга PDF.
    Возвращает список позиций: [{name, param, unit, qty}, ...]
    """
    global HAS_PDFPLUMBER
    if not HAS_PDFPLUMBER:
        try:
            import subprocess
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "pdfplumber"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            import pdfplumber as _pdf
            HAS_PDFPLUMBER = True
        except Exception as e:
            print(f"pdfplumber install failed: {e}", file=sys.stderr)
            return []

    import pdfplumber

    items = []
    raw_text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            # ── Метод 1: извлечение таблиц ──────────────────────────
            tables = page.extract_tables() or []
            for table in tables:
                table_items = _parse_table(table)
                items.extend(table_items)

            # Собираем текст для метода 2
            text = page.extract_text() or ""
            raw_text += text + "\n"

    # ── Метод 2: парсинг текста если таблицы не дали результат ──
    if len(items) < 1 and raw_text.strip():
        items = _parse_text(raw_text)

    # Убираем дубликаты по имени
    seen = set()
    unique = []
    for it in items:
        key = it["name"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(it)

    return unique


def _parse_table(table: list) -> List[Dict[str, Any]]:
    """Парсит таблицу из PDF"""
    if not table or len(table) < 2:
        return []

    items = []

    # Определяем индексы колонок по заголовку
    header = [str(c).lower().strip() if c else "" for c in table[0]]
    col_name  = _find_col(header, ["наименование","название","товар","материал",
                                    "name","item","description","позиция","номенклатура"])
    col_param = _find_col(header, ["параметр","характеристика","марка","тип",
                                    "specification","grade","param"])
    col_unit  = _find_col(header, ["ед","единица","unit","мера","изм"])
    col_qty   = _find_col(header, ["кол","количество","qty","quantity","объём",
                                    "объем","amount","число"])

    # Если колонка имени не найдена — берём первую
    if col_name is None:
        col_name = 0

    for row in table[1:]:
        if not row or not row[col_name]:
            continue

        cells = [str(c).strip() if c else "" for c in row]

        name = cells[col_name] if col_name < len(cells) else ""
        if not name or len(name) < 2:
            continue

        # Пропускаем строки-заголовки и итоги
        skip_words = {"итого","total","всего","sum","наименование","название",
                      "товар","name","item","№","#","п/п"}
        if name.lower() in skip_words:
            continue

        param = cells[col_param] if col_param is not None and col_param < len(cells) else ""
        unit  = cells[col_unit]  if col_unit  is not None and col_unit  < len(cells) else "шт"
        qty_raw = cells[col_qty] if col_qty   is not None and col_qty   < len(cells) else ""

        qty = _parse_qty(qty_raw)
        unit = _clean_unit(unit)

        if qty <= 0:
            qty = 1.0  # если не нашли кол-во — ставим 1

        items.append({
            "name":  name[:200].strip(),
            "param": param[:200].strip(),
            "unit":  unit or "шт",
            "qty":   qty,
        })

    return items


def _parse_text(text: str) -> List[Dict[str, Any]]:
    """
    Парсит текстовое содержимое PDF.
    Ищет паттерны вида:
    - "1. Цемент М400 мешок 50 кг ..... 100 шт"
    - "Цемент М400    100    шт"
    - "- Цемент М400 (50 кг) - 100 шт"
    """
    items = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line or len(line) < 4:
            continue

        # Пропускаем явные заголовки
        skip = {"итого","total","всего","наименование","единица","количество",
                "кол-во","ед.изм","параметр","характеристика"}
        if line.lower() in skip:
            continue

        # Паттерн 1: "1. Цемент М400  100 шт" или "№1 Цемент 100 шт"
        m = re.match(
            r'^(?:\d+[\.\)\s]+|[-•]\s*)'   # номер или маркер
            r'(.+?)\s{2,}'                  # название (2+ пробела = разделитель)
            r'(\d+(?:[.,]\d+)?)\s*'         # количество
            r'(шт|кг|т(?:онн)?|м(?:2|3|²|³)?|л|уп|компл|пог\.м|рул|пач|мп)?\s*$',
            line, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip()
            qty  = _parse_qty(m.group(2))
            unit = m.group(3) or "шт"
            if name and len(name) > 2 and qty > 0:
                # Разделяем параметры если есть скобки: "Цемент М400 (мешок 50 кг)"
                param = ""
                pm = re.search(r'\(([^)]+)\)', name)
                if pm:
                    param = pm.group(1)
                    name  = name[:pm.start()].strip()
                items.append({
                    "name":  name[:200],
                    "param": param[:200],
                    "unit":  _clean_unit(unit),
                    "qty":   qty,
                })
                continue

        # Паттерн 2: строки с разделителем табуляцией или множеством пробелов
        parts = re.split(r'\t|\s{3,}', line)
        if len(parts) >= 2:
            name = parts[0].strip()
            # Ищем число среди частей
            qty  = 0.0
            unit = "шт"
            for part in parts[1:]:
                q = _parse_qty(part)
                if q > 0:
                    qty = q
                u = _clean_unit(part)
                if u:
                    unit = u
            if name and len(name) > 2 and qty > 0:
                # Убираем числа и маркеры из начала имени
                name = re.sub(r'^[\d\.\)\s]+','', name).strip()
                if name and len(name) > 2:
                    items.append({
                        "name":  name[:200],
                        "param": "",
                        "unit":  unit,
                        "qty":   qty,
                    })

    return items


def _find_col(header: list, keywords: list) -> int | None:
    """Находит индекс колонки по ключевым словам"""
    for i, h in enumerate(header):
        for kw in keywords:
            if kw in h:
                return i
    return None


def _parse_qty(s: str) -> float:
    """Извлекает число из строки"""
    if not s: return 0.0
    s = str(s).strip()
    m = re.search(r'(\d+(?:[.,]\d+)?)', s)
    if m:
        try:
            return float(m.group(1).replace(",","."))
        except:
            return 0.0
    return 0.0


def _clean_unit(s: str) -> str:
    """Нормализует единицу измерения"""
    if not s: return ""
    s = s.strip().lower()
    mapping = {
        "штук":"шт","штуки":"шт","шт.":"шт",
        "кг.":"кг","килограмм":"кг","килограммов":"кг",
        "тонн":"т","тонна":"т","тонны":"т","т.":"т",
        "метр":"м","метров":"м","м.":"м",
        "м2":"м²","м²":"м²","кв.м":"м²","кв м":"м²",
        "м3":"м³","куб.м":"м³","куб м":"м³",
        "литр":"л","литров":"л","л.":"л",
        "упаковка":"уп","упак":"уп","уп.":"уп",
        "комплект":"компл","компл.":"компл",
        "погонный метр":"пог.м","пог.м.":"пог.м","пм":"пог.м",
        "рулон":"рул","рул.":"рул",
        "пачка":"пач","пач.":"пач",
    }
    return mapping.get(s, s if len(s) <= 6 else "")
