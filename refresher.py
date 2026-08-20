import random
import threading
import time
from datetime import datetime, timezone

import database
import license
import onet_scraper

# Rozproszony punkt weryfikacji anti-tamper — drugi niezależny check.
# Atakujący musi znaleźć i załatać wszystkie punkty, nie tylko license.py.
def _tamper_ok():
    return license.check_pubkey()

# ---- konfiguracja throttlingu ----
MIN_INTERVAL_SECONDS = 140        # min. przerwa miedzy odswiezeniami
MAX_PER_HOUR = 15                 # limit odswiezen na godzine
FAST_CADENCE_SECONDS = 10 * 60    # automat co 10 min dopoki coverage < 90%
FAST_CADENCE_JITTER = 15          # +-15 s losowej roznicy
SLOW_CADENCE_SECONDS = 60 * 60    # potem automatycznie co godzine
COVERAGE_TARGET = 0.90            # 90% contentu zgodnego z baza

_state = {
    "lock": threading.Lock(),
    "last_refresh": 0.0,          # timestamp ostatniego zakonczonego odswiezenia
    "refresh_times": [],          # czasy odswiezen w oknie godzinowym
    "coverage": None,             # ostatni wspolczynnik zgodnosci z baza
    "mode": "fast",               # "fast" (10min) lub "slow" (1h)
    "status": "idle",             # idle | refreshing
    "last_result": None,
    "thread": None,
}


def _now():
    return time.time()


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def status():
    """Aktualny stan systemu odswiezan."""
    with _state["lock"]:
        wait_throttle = max(0.0, _state["last_refresh"] + MIN_INTERVAL_SECONDS - _now())
        now = _now()
        window = [t for t in _state["refresh_times"] if now - t < 3600]
        if len(window) >= MAX_PER_HOUR:
            wait_quota = max(0.0, min(window) + 3600 - now)
        else:
            wait_quota = 0.0
        return {
            "status": _state["status"],
            "mode": _state["mode"],
            "coverage": _state["coverage"],
            "last_refresh": _iso(_state["last_refresh"]),
            "refreshes_this_hour": len(window),
            "max_per_hour": MAX_PER_HOUR,
            "wait_throttle_seconds": round(wait_throttle),
            "wait_quota_seconds": round(wait_quota),
            "min_interval_seconds": MIN_INTERVAL_SECONDS,
        }


def _do_refresh():
    """Wykonuje scrape wszystkich kategorii i zapisuje do bazy.

    Coverage liczone w trakcie skanowania (bez drugiego scrapowania stron):
    udzial artykulow juz obecnych w bazie sposrod wszystkich znalezionych.
    """
    added = 0
    known = 0
    total = 0
    errors = {}
    for cat in onet_scraper.CATEGORIES:
        try:
            arts = onet_scraper.scrape_category(cat)
            for a in arts:
                total += 1
                if database.is_known(a["link"]):
                    known += 1
                database.upsert_article(a)
            added += len(arts)
        except Exception as e:
            errors[cat] = str(e)

    removed = database.cleanup_old()
    coverage = known / total if total else 1.0
    return {"added": added, "errors": errors, "purged": removed, "coverage": coverage}


def refresh(trigger="user"):
    """Proba odswiezenia z throttlingiem. Zwraca odpowiedz dla API.

    trigger: "user" (recznie) lub "auto" (zaplanowany). Odpowiedz:
      - {"status": "refreshing"}   juz trwa
      - {"status": "waiting", "wait_seconds": n}  za wczesnie (min. przerwa)
      - {"status": "quota", "wait_seconds": n}    limit godzinowy wyczerpany
      - {"status": "ok", "result": {...}}          wykonano
    """
    with _state["lock"]:
        if _state["status"] == "refreshing":
            return {"status": "refreshing"}

        now = _now()
        since = now - _state["last_refresh"]
        if since < MIN_INTERVAL_SECONDS:
            return {"status": "waiting", "wait_seconds": round(MIN_INTERVAL_SECONDS - since)}

        _state["refresh_times"] = [t for t in _state["refresh_times"] if now - t < 3600]
        if len(_state["refresh_times"]) >= MAX_PER_HOUR:
            wait = min(_state["refresh_times"]) + 3600 - now
            return {"status": "quota", "wait_seconds": round(wait)}

        _state["status"] = "refreshing"

    try:
        result = _do_refresh()
    except Exception as e:
        result = {"added": 0, "errors": {"_": str(e)}, "purged": 0, "coverage": None}
    finally:
        with _state["lock"]:
            _state["status"] = "idle"

    with _state["lock"]:
        _state["last_refresh"] = _now()
        _state["refresh_times"].append(_state["last_refresh"])
        _state["coverage"] = result.get("coverage")
        if _state["coverage"] is not None:
            _state["mode"] = "slow" if _state["coverage"] >= COVERAGE_TARGET else "fast"
        _state["last_result"] = result

    # Kotwica czasu z dat artykułów Onetu — odporność na manipulację zegarem.
    try:
        dates = database.recent_published_timestamps(40)
        if dates:
            license.observe_dates(dates)
    except Exception:
        pass

    return {"status": "ok", "trigger": trigger, "result": result}


def _auto_loop():
    while True:
        with _state["lock"]:
            mode = _state["mode"]
        if mode == "fast":
            cadence = FAST_CADENCE_SECONDS + random.uniform(-FAST_CADENCE_JITTER, FAST_CADENCE_JITTER)
        else:
            cadence = SLOW_CADENCE_SECONDS + random.uniform(-60, 60)
        time.sleep(max(cadence, 1))
        # Nie scrapuj, gdy okres próbny minął i nie wprowadzono klucza.
        try:
            if not license.is_active():
                continue
            # Rozproszony punkt anti-tamper — jeśli klucz publiczny podmieniony,
            # nie scrapuj (drugi niezależny check poza app.startup).
            if not _tamper_ok():
                continue
        except Exception:
            pass
        refresh(trigger="auto")


def start():
    """Uruchamia watek automatycznego odswiezania (idempotentnie)."""
    with _state["lock"]:
        if _state["thread"] and _state["thread"].is_alive():
            return
        _state["thread"] = threading.Thread(target=_auto_loop, daemon=True)
        _state["thread"].start()
