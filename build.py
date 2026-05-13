"""
Скрипт сборки .exe из исходников.
Запускать на Windows: python build.py
"""
import os
import sys
import subprocess
import shutil

DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    print("=" * 60)
    print("  Procurement Global — сборка .exe")
    print("=" * 60)

    # 1. Установка зависимостей
    print("\n[1/3] Установка зависимостей...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "pywebview", "httpx", "selectolax", "openpyxl", "pyinstaller",
    ])

    # 2. Очистка прошлой сборки
    for folder in ("build", "dist"):
        path = os.path.join(DIR, folder)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"  → удалена папка {folder}/")
    spec = os.path.join(DIR, "Procurement.spec")
    if os.path.exists(spec):
        os.remove(spec)

    # 3. Сборка
    print("\n[2/3] Сборка .exe (это займёт 1-2 минуты)...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                     # один файл
        "--windowed",                    # без консоли
        "--name", "Procurement",
        "--add-data", "ui.html;.",       # встроить HTML
        "--hidden-import", "_cffi_backend",
        "--collect-all", "webview",
        "--noconfirm",
        "app.py",
    ]
    # На Linux/Mac разделитель ":"
    if not sys.platform.startswith("win"):
        cmd[cmd.index("ui.html;.")] = "ui.html:."

    subprocess.check_call(cmd)

    # 4. Готово
    exe_path = os.path.join(DIR, "dist", "Procurement.exe")
    if not os.path.exists(exe_path):
        exe_path = os.path.join(DIR, "dist", "Procurement")  # Linux

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[3/3] ✓ Готово!")
        print(f"\nФайл: {exe_path}")
        print(f"Размер: {size_mb:.1f} MB")
        print(f"\nДвойной клик чтобы запустить.")
    else:
        print("\n✗ Сборка не удалась")
        sys.exit(1)


if __name__ == "__main__":
    main()
