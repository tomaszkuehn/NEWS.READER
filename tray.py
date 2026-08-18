"""News Reader — launcher okienkowy (system tray).

Uruchamia lokalny serwer FastAPI (app.py) w tle i pokazuje ikonę w zasobniku
systemowym z menu: otwórz czytnik, odśwież, folder danych, wyjdź.
"""

import ctypes
import os
import socket
import sys
import threading
import time
import webbrowser

import pystray
import uvicorn
from PIL import Image, ImageDraw

import app as server_app
import database
import license
import refresher

APP_NAME = "News Reader"
HOST = "127.0.0.1"
PORT = 8000
MAX_PORT_TRIES = 20

# Uchwyt mutexu musi żyć w całym procesie, inaczej Windows go zwolni.
_INSTANCE_MUTEX = None


def _log_file():
    return os.path.join(database.get_data_dir(), "news-reader.log")


def _make_log_config():
    """Konfiguracja logowania uvicorn do pliku (brak konsoli w wersji GUI)."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
            "access": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": _log_file(),
                "formatter": "default",
                "encoding": "utf-8",
            },
        },
        "root": {"level": "INFO", "handlers": ["file"]},
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": ["file"], "propagate": False},
            "uvicorn.error": {"level": "INFO", "handlers": ["file"], "propagate": False},
            "uvicorn.access": {"level": "WARNING", "handlers": ["file"], "propagate": False},
        },
    }


def acquire_single_instance():
    """Blokuje drugą instancję aplikacji (mutex w namespace Global)."""
    global _INSTANCE_MUTEX
    _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\NewsReader.SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


def _find_free_port():
    for p in range(PORT, PORT + MAX_PORT_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    return PORT


def start_server():
    """Startuje serwer w wątku. Zwraca (server, url)."""
    port = _find_free_port()
    config = uvicorn.Config(
        server_app.app,
        host=HOST,
        port=port,
        log_config=_make_log_config(),
        access_log=True,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 15
    while time.time() < deadline:
        if getattr(server, "started", False):
            break
        time.sleep(0.05)

    return server, f"http://{HOST}:{port}"


def _make_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(26, 92, 240, 255))
    d.ellipse((6, 6, 58, 58), outline=(255, 255, 255, 200), width=2)
    d.text((17, 8), "N", fill="white")
    d.text((17, 30), "R", fill="white")
    return img


def _trigger_refresh():
    try:
        # Rozproszony punkt weryfikacji — tray (ikona zasobnika) również sprawdza.
        if not license.check_pubkey():
            return
        if database.count_articles() >= license.LIMIT and not license.is_unlocked():
            return
        refresher.refresh(trigger="user")
    except Exception:
        pass


def main():
    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(0, "News Reader jest już uruchomiony.", APP_NAME, 0x40)
        return 1

    server, url = start_server()

    def on_open(_icon, _item):
        webbrowser.open(url)

    def on_refresh(_icon, _item):
        threading.Thread(target=_trigger_refresh, daemon=True).start()

    def on_data_folder(_icon, _item):
        os.startfile(database.get_data_dir())

    def on_exit(_icon, _item):
        server.should_exit = True
        _icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"{APP_NAME} — otwórz czytnik", on_open, default=True),
        pystray.MenuItem("Odśwież artykuły", on_refresh),
        pystray.MenuItem("Otwórz folder danych", on_data_folder),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Wyjdź", on_exit),
    )

    icon = pystray.Icon(APP_NAME, _make_icon_image(), APP_NAME, menu)

    webbrowser.open(url)
    icon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
