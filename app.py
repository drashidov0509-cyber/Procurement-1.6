"""
Procurement Global — настольное приложение
Запуск: python app.py
Сборка в .exe: pyinstaller --onefile --windowed --name Procurement app.py
"""
import webview
import os
import sys
import threading
from api import API


def get_html_path():
    """Путь к UI"""
    if getattr(sys, 'frozen', False):
        # Запущено как .exe — файлы внутри
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'ui.html')


def main():
    api = API()
    window = webview.create_window(
        title='Procurement Global v1.6',
        url=get_html_path(),
        js_api=api,
        width=1300,
        height=860,
        min_size=(960, 640),
        background_color='#0b1120',
        text_select=True,
    )
    api._set_window(window)
    webview.start(debug=False)


if __name__ == '__main__':
    main()
