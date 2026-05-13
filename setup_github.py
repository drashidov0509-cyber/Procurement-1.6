"""
Procurement Global — автоматическая загрузка на GitHub и сборка .exe
Запустите: python setup_github.py
"""
import os, sys, json, time, base64, zipfile, subprocess
from pathlib import Path

# ═══════════════════════════════════════════════
# После получения нового токена — вставьте его ниже
GITHUB_TOKEN    = ""   # ← сюда вставить новый токен (sk-ant-...)
GITHUB_USERNAME = "drashidov0509-cyber"
REPO_NAME       = "Procurement-1.6"
# ═══════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent.resolve()

# Если токен не заполнен — просим ввести
if not GITHUB_TOKEN:
    print("\n" + "═"*55)
    print("  Procurement Global — Автоматическая настройка")
    print("═"*55)
    print("\n  Токен не заполнен в скрипте.")
    print("  Получите новый токен:")
    print("  https://github.com/settings/tokens?type=beta")
    GITHUB_TOKEN = input("\n  Введите токен (github_pat_...): ").strip()
    if not GITHUB_TOKEN:
        print("  Токен не введён. Выход.")
        sys.exit(1)


def install(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", pkg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def step(n, text):
    print(f"\n[{n}/7] {text}")
    print("─" * 50)

def ok(t):   print(f"  ✅ {t}")
def info(t): print(f"  ℹ  {t}")
def err(t):  print(f"  ❌ {t}")


# ── Установка requests если нет ─────────────────
print("\n" + "═"*55)
print("  Procurement Global — Автоматическая настройка")
print("═"*55)
print("\n  Проверяю зависимости...")

try:
    import requests
except ImportError:
    print("  Устанавливаю requests...")
    install("requests")
    import requests

# Отключаем предупреждения SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SESSION = requests.Session()
SESSION.verify = False   # обходим SSL-проблему на Windows
SESSION.headers.update({
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "ProcurementSetup/1.0",
})

BASE = "https://api.github.com"


def api(method, path, data=None):
    url = BASE + path
    r = SESSION.request(method, url, json=data, timeout=30)
    if not r.ok:
        msg = r.json().get("message", r.text[:200])
        raise RuntimeError(f"GitHub {r.status_code}: {msg}")
    return r.json() if r.text else {}


def put_file(path, content: bytes, message: str, sha=None):
    url = f"{BASE}/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{path}"
    data = {"message": message, "content": base64.b64encode(content).decode()}
    if sha:
        data["sha"] = sha
    r = SESSION.put(url, json=data, timeout=30)
    if not r.ok:
        msg = r.json().get("message", r.text[:100])
        raise RuntimeError(f"Upload {path}: {msg}")
    return r.json()


def get_sha(path):
    url = f"{BASE}/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{path}"
    r = SESSION.get(url, timeout=10)
    return r.json().get("sha") if r.ok else None


# ── 1. Проверка токена ──────────────────────────
step(1, "Проверка токена GitHub")
try:
    user = api("GET", "/user")
    ok(f"Токен работает! Аккаунт: {user['login']}")
except Exception as e:
    err(f"Ошибка подключения: {e}")
    print("\n  Возможные причины:")
    print("  • VPN или прокси блокирует GitHub — отключите и повторите")
    print("  • Антивирус блокирует соединение — добавьте Python в исключения")
    print("  • Нет интернета")
    input("\n  Нажмите Enter для выхода...")
    sys.exit(1)

# ── 2. Создание репозитория ─────────────────────
step(2, f"Создание репозитория «{REPO_NAME}»")
try:
    r = api("GET", f"/repos/{GITHUB_USERNAME}/{REPO_NAME}")
    ok(f"Репозиторий уже существует: {r['html_url']}")
except RuntimeError:
    r = api("POST", "/user/repos", {
        "name": REPO_NAME,
        "description": "Procurement Global — поиск поставщиков ТМЦ",
        "private": False,
        "auto_init": True,
    })
    ok(f"Создан: {r['html_url']}")
    time.sleep(3)

REPO_URL = f"https://github.com/{GITHUB_USERNAME}/{REPO_NAME}"

# ── 3. Загрузка файлов ─────────────────────────
step(3, "Загрузка файлов программы")

FILES = [
    "app.py", "api.py", "scrapers.py", "classifier.py",
    "excel_export.py", "ui.html", "requirements.txt",
    ".github/workflows/build.yml",
]

uploaded = 0
for fname in FILES:
    fpath = SCRIPT_DIR / fname
    if not fpath.exists():
        print(f"  ⚠  Не найден: {fname}")
        continue
    try:
        sha = get_sha(fname)
        put_file(fname, fpath.read_bytes(), f"Add {fname}", sha)
        ok(f"{fname}")
        uploaded += 1
        time.sleep(0.5)
    except Exception as e:
        print(f"  ⚠  {fname}: {e}")

info(f"Загружено: {uploaded}/{len(FILES)}")

if not get_sha(".github/workflows/build.yml"):
    err("Файл .github/workflows/build.yml не загружен — сборка невозможна")
    sys.exit(1)

# ── 4. Запуск Actions ───────────────────────────
step(4, "Запуск сборки .exe на серверах GitHub")
ok("GitHub Actions запустится автоматически после загрузки файлов")
info(f"Следить: {REPO_URL}/actions")

# ── 5. Ожидание сборки ─────────────────────────
step(5, "Ожидание завершения сборки (~5 минут)")
info("GitHub собирает .exe на своих Windows-серверах...\n")

max_wait = 15 * 60
interval = 15
elapsed  = 0
run_id   = None

while elapsed < max_wait:
    time.sleep(interval)
    elapsed += interval

    try:
        runs = api("GET", f"/repos/{GITHUB_USERNAME}/{REPO_NAME}/actions/runs")
        wf = runs.get("workflow_runs", [])
        if not wf:
            print(f"  ⏳ Ожидаю запуска... ({elapsed}с)   ", end="\r")
            continue

        latest     = wf[0]
        run_id     = latest["id"]
        status     = latest["status"]
        conclusion = latest.get("conclusion")

        print(f"  ⏳ {status} / {conclusion or '...'} ({elapsed}с)   ", end="\r")

        if status == "completed":
            print()
            if conclusion == "success":
                ok("Сборка завершена успешно! 🎉")
                break
            else:
                err(f"Сборка провалилась: {conclusion}")
                print(f"  Подробности: {REPO_URL}/actions")
                input("\nНажмите Enter...")
                sys.exit(1)
    except Exception as e:
        print(f"\n  ⚠  Проверка: {e}")
else:
    print()
    err("Превышено время ожидания")
    print(f"  Проверьте вручную: {REPO_URL}/actions")
    sys.exit(1)

# ── 6. Скачивание .exe ─────────────────────────
step(6, "Скачивание готового Procurement.exe")

arts = api("GET", f"/repos/{GITHUB_USERNAME}/{REPO_NAME}/actions/runs/{run_id}/artifacts")
art_list = arts.get("artifacts", [])

if not art_list:
    err("Артефакты не найдены")
    print(f"  Скачайте вручную: {REPO_URL}/actions")
    sys.exit(1)

art = art_list[0]
ok(f"Артефакт: {art['name']} ({art['size_in_bytes']//1024//1024} MB)")

dl_url = f"{BASE}/repos/{GITHUB_USERNAME}/{REPO_NAME}/actions/artifacts/{art['id']}/zip"
print("  ⏳ Скачиваю...", end="", flush=True)
r = SESSION.get(dl_url, timeout=120, stream=True)
zip_path = SCRIPT_DIR / "tmp_art.zip"
with open(zip_path, "wb") as f:
    for chunk in r.iter_content(65536):
        f.write(chunk)
print(" готово!")

exe_out = SCRIPT_DIR / "Procurement.exe"
with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall(SCRIPT_DIR)
zip_path.unlink()

if exe_out.exists():
    size = exe_out.stat().st_size / 1024 / 1024
    ok(f"Procurement.exe ({size:.1f} MB) сохранён в:\n  {SCRIPT_DIR}")
else:
    ok("Файлы распакованы — ищите Procurement.exe в папке")

# ── 7. Итог ────────────────────────────────────
step(7, "ГОТОВО! 🎉")
print(f"""
  ✅ Procurement.exe готов!
  📁 Папка: {SCRIPT_DIR}

  🖱  Дважды кликните Procurement.exe — программа запустится.

  ⚠️  УДАЛИТЕ токен GitHub (он больше не нужен):
  🔗 https://github.com/settings/tokens
  → Нажмите Delete рядом с токеном procurement-build

  📦 Ваш репозиторий (для обновлений):
  🔗 {REPO_URL}
""")
input("Нажмите Enter для выхода...")
