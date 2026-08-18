import json
import os
import random
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Realistyczne User-Agenty współczesnych przeglądarek — każda instalacja
# losuje jeden przy pierwszym uruchomieniu i trzyma go stabilnie.
USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.87",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.2535.67",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _data_dir():
    try:
        import database

        return database.get_data_dir()
    except ImportError:
        return os.path.dirname(os.path.abspath(__file__))


def browser_identity():
    """Identyfikator przeglądarki (User-Agent) przypisany tej instalacji.

    Losowany raz — przy pierwszym uruchomieniu po instalacji — i zapisywany
    w katalogu danych. Dzięki temu jest stały dla danej instalacji (jak
    w prawdziwej przeglądarce), a różny między instalacjami — co utrudnia
    rozpoznanie i zablokowanie scrapera po stronie Onetu.
    """
    path = os.path.join(_data_dir(), "browser_identity.txt")
    try:
        with open(path, encoding="utf-8") as f:
            ua = f.read().strip()
        if ua:
            return ua
    except OSError:
        pass
    ua = random.choice(USER_AGENT_POOL)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ua)
    except OSError:
        pass
    return ua


HEADERS = {
    "User-Agent": browser_identity(),
}

# Strona główna jest renderowana przez JS dla zwykłych UA;
# Googlebot dostaje pełny SSR, dlatego używamy jego UA tylko dla niej.
BOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

ARTICLE_URL_RE = re.compile(r"/(?:[a-z0-9-]+/)+[a-z0-9]{6,}(?:,[0-9a-f]{8})?(?:#[a-z0-9]+)?$")

# Sufiks sluga kończący się stabilnym ID artykułu (np. '/.../1xp7wn9' lub '/...,30bc1058').
_ARTICLE_ID_RE = re.compile(r"/([a-z0-9]{6,})(?:,[0-9a-f]{8})?(?:#[a-z0-9]+)?$")


def article_key(link):
    """Stabilny identyfikator artykułu niezależny od sluga i kotwicy.

    Onet zmienia slug w URL tej samej treści (np.
    '/kolejny-odcinek-.../1xp7wn9' vs '/rafal-brzoska-.../1xp7wn9'),
    a dopisek '#pco' pojawia się/znika losowo. Stabilnym klucdem jest
    domena + końcowe ID artykułu. Zwraca '' gdy nie uda się wyłuskać ID.
    """
    s = link.split("#", 1)[0].rstrip("/")
    m = _ARTICLE_ID_RE.search(s)
    if not m:
        return ""
    host = re.match(r"https?://([^/]+)", link)
    host = host.group(1).lower() if host else ""
    if host.startswith("www."):
        host = host[4:]
    return f"{host}/{m.group(1)}"

SPONSOR_PHRASES = (
    "materiał promocyjny",
    "materiał sponsorowany",
    "artykuł promocyjny",
    "artykuł sponsorowany",
    "sponsorowane",
    "sponsoring",
    "reklama",
)

# Domeny, których nie zawsze można wywnioskować z nazwy kategorii
EXTERNAL_DOMAINS = {
    "auto-swiat.pl": {"www.auto-swiat.pl", "auto-swiat.pl"},
    "businessinsider.com.pl": {"www.businessinsider.com.pl", "businessinsider.com.pl"},
    "komputerswiat.pl": {"www.komputerswiat.pl", "komputerswiat.pl"},
    "przegladsportowy.onet.pl": {"www.przegladsportowy.onet.pl", "przegladsportowy.onet.pl"},
    "newsweek.pl": {"www.newsweek.pl", "newsweek.pl"},
    "fakt.pl": {"www.fakt.pl", "fakt.pl", "ludzie.fakt.pl"},
    "plejada.pl": {"plejada.pl", "www.plejada.pl"},
    "ofeminin.pl": {"www.ofeminin.pl", "ofeminin.pl"},
    "noizz.pl": {"noizz.pl", "www.noizz.pl"},
    "medonet.pl": {"www.medonet.pl", "medonet.pl", "zywienie.medonet.pl"},
    "forbes.pl": {"www.forbes.pl", "forbes.pl"},
    "gratka.pl": {"gratka.pl", "www.gratka.pl"},
    "lamoda.pl": {"lamoda.pl", "www.lamoda.pl"},
}

CATEGORIES = {
    "glowna": {
        "urls": ["https://www.onet.pl"],
        "bot": True,
    },
    "najnowsze": {
        "urls": ["https://wiadomosci.onet.pl/najnowsze"],
        # Feed najnowszych wiadomości — artykuły przechowywane w kategorii
        # treści; w zakładce 'najnowsze' pojawiają się tylko przez 2h od
        # pierwszego znalezienia (kategoria wirtualna, zob. database.get_articles).
        "category": "wiadomosci",
    },
    "wiadomosci": {
        "urls": [
            "https://wiadomosci.onet.pl",
            "https://wiadomosci.onet.pl/kraj",
            "https://wiadomosci.onet.pl/swiat",
            "https://wiadomosci.onet.pl/polska",
        ],
    },
    "sport": {
        "urls": [
            "https://przegladsportowy.onet.pl",
            "https://przegladsportowy.onet.pl/pilka-nozna",
            "https://przegladsportowy.onet.pl/tenis",
            "https://przegladsportowy.onet.pl/koszykowka",
        ],
    },
    "biznes": {
        "urls": [
            "https://biznes.onet.pl",
            "https://businessinsider.com.pl/biznes",
            "https://businessinsider.com.pl/gospodarka",
            "https://businessinsider.com.pl/prawo",
            "https://businessinsider.com.pl/finanse",
            "https://businessinsider.com.pl/technologie",
            "https://businessinsider.com.pl/praca",
            "https://businessinsider.com.pl/nieruchomosci",
        ],
        "domains": ["biznes.onet.pl", "businessinsider.com.pl"],
    },
    "kultura": {
        "urls": [
            "https://kultura.onet.pl",
            "https://kultura.onet.pl/film",
            "https://kultura.onet.pl/muzyka",
            "https://kultura.onet.pl/ksiazki",
            "https://kultura.onet.pl/seriale",
        ],
    },
    "technologie": {
        "urls": [
            "https://technologie.onet.pl",
            "https://technologie.onet.pl/gry",
        ],
    },
    "inspiracje": {
        "urls": ["https://kobieta.onet.pl"],
    },
    "motoryzacja": {
        "urls": [
            "https://moto.onet.pl",
            "https://www.auto-swiat.pl/wiadomosci",
        ],
    },
    "podroze": {
        "urls": [
            "https://podroze.onet.pl",
            "https://podroze.onet.pl/podroze",
        ],
    },
}

LANGS = {"vr", "men", "kobieta", "happy", "magia", "styl", "gust", "romans"}

# Mapowanie sekcji strony głównej (<section data-section="...">) na nasze kategorie.
# Sekcje ogólne (news, importantnews, popular itd.) NIE są mapowane — artykuły
# z nich dostają kategorię treści z domeny/ścieżki URL (patrz _infer_category).
# Sekcje reklamowe (bigbox*, oferty*, paid_promo itd.) nie są mapowane.
SECTION_TO_CATEGORY = {
    "sport": "sport",
    "economy": "biznes",
    "lifestyle": "inspiracje",
    "tech": "technologie",
    "moto": "motoryzacja",
    "travel": "podroze",
}

# Dodatkowe domeny partnerskie -> nasza kategoria treści (dla _infer_category).
# Domeny zdefiniowane w CATEGORIES (urle + domains) są brane automatycznie.
_EXTRA_DOMAIN_CATEGORY = {
    "newsweek.pl": "wiadomosci",
    "www.newsweek.pl": "wiadomosci",
    "fakt.pl": "wiadomosci",
    "www.fakt.pl": "wiadomosci",
    "ludzie.fakt.pl": "wiadomosci",
    "medonet.pl": "wiadomosci",
    "www.medonet.pl": "wiadomosci",
    "zywienie.medonet.pl": "wiadomosci",
    "komputerswiat.pl": "technologie",
    "www.komputerswiat.pl": "technologie",
    "forbes.pl": "biznes",
    "www.forbes.pl": "biznes",
    "plejada.pl": "kultura",
    "www.plejada.pl": "kultura",
    "noizz.pl": "inspiracje",
    "www.noizz.pl": "inspiracje",
    "ofeminin.pl": "inspiracje",
    "www.ofeminin.pl": "inspiracje",
    "lamoda.pl": "inspiracje",
    "www.lamoda.pl": "inspiracje",
}

# Kanał w ścieżce www.onet.pl/<kanal>/... -> nasza kategoria.
_CHANNEL_CATEGORY = {
    "informacje": "wiadomosci",
    "kraj": "wiadomosci",
    "swiat": "wiadomosci",
    "polska": "wiadomosci",
    "polityka": "wiadomosci",
    "news": "wiadomosci",
    "sport": "sport",
    "pilka-nozna": "sport",
    "biznes": "biznes",
    "gospodarka": "biznes",
    "gielda": "biznes",
    "finanse": "biznes",
    "kultura": "kultura",
    "film": "kultura",
    "muzyka": "kultura",
    "seriale": "kultura",
    "ksiazki": "kultura",
    "technologie": "technologie",
    "technologia": "technologie",
    "gry": "technologie",
    "kobieta": "inspiracje",
    "styl": "inspiracje",
    "moda": "inspiracje",
    "moto": "motoryzacja",
    "motoryzacja": "motoryzacja",
    "podroze": "podroze",
    "turystyka": "podroze",
}

_DOMAIN_CATEGORY = {}
for _cat, _cfg in CATEGORIES.items():
    if _cat in ("glowna", "najnowsze"):
        continue
    _hosts = set(_cfg.get("domains", []))
    for _u in _cfg.get("urls", []):
        _h = re.match(r"https?://([^/]+)", _u)
        if _h:
            _hosts.add(_h.group(1).lower())
    for _h in _hosts:
        _DOMAIN_CATEGORY.setdefault(_h, _cat)
for _h, _cat in _EXTRA_DOMAIN_CATEGORY.items():
    _DOMAIN_CATEGORY.setdefault(_h, _cat)


def _infer_category(url):
    """Kategoria treści na podstawie domeny i ścieżki URL.

    Używana dla artykułów, których sekcja strony głównej nie daje konkretnej
    kategorii (np. news/importantnews) oraz do migracji starych wpisów
    'glowna'/'najnowsze'. Fallback: 'wiadomosci'.
    """
    m = re.match(r"https?://([^/]+)(/[^/]*)?", url)
    if not m:
        return "wiadomosci"
    host = m.group(1).lower()
    first = (m.group(2) or "").strip("/").lower()
    cat = _DOMAIN_CATEGORY.get(host)
    if not cat:
        # Obsługa wariantów www/non-www (np. www.businessinsider.com.pl)
        alt = host[4:] if host.startswith("www.") else "www." + host
        cat = _DOMAIN_CATEGORY.get(alt)
    if cat:
        return cat
    if host == "www.onet.pl" and first:
        return _CHANNEL_CATEGORY.get(first, "wiadomosci")
    return "wiadomosci"


def _section_category(art, default):
    """Zwraca naszą kategorię dla <article> na podstawie sekcji data-section."""
    sec = art.find_parent("section", attrs={"data-section": True})
    if sec is None:
        return default
    return SECTION_TO_CATEGORY.get(sec["data-section"], default)


def _merge_article(found, art):
    """Dodaje artykuł z priorytetem dla kategorii z sekcji redakcyjnej.

    Dedup po stabilnym identyfikatorze (article_key), nie po pełnym linku —
    Onet zmienia slug tego samego artykułu, a dopisek '#pco' pojawia się
    losowo. Jeśli ten sam artykuł był już znaleziony w sekcji reklamowej
    (domyślnie 'glowna'), a teraz wiemy, że należy do konkretnej kategorii,
    nadpisujemy (zachowując dotychczasowy link). Data publikacji jest
    uzupełniana, jeśli dopiero teraz ją poznaliśmy.
    """
    key = article_key(art["link"]) or art["link"]
    if key not in found:
        found[key] = art
        return
    if found[key]["category"] == "glowna" and art["category"] != "glowna":
        # zachowaj pierwszy link, nadpisz kategorię
        art_keep_link = {**art, "link": found[key]["link"]}
        found[key] = art_keep_link
        return
    if not found[key].get("published_at") and art.get("published_at"):
        found[key]["published_at"] = art["published_at"]


def fetch_html(url, bot=False):
    r = requests.get(url, headers=BOT_HEADERS if bot else HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def _is_accept_domain(href, category):
    """Czy domena linku może być artykułem (Onet + partnerzy kategorii)."""
    m = re.match(r"https?://([^/]+)/", href)
    if not m:
        return True
    host = m.group(1).lower()
    if host == "onet.pl" or host.endswith(".onet.pl"):
        return True
    cfg_domains = set(CATEGORIES.get(category, {}).get("domains", []))
    for ext in EXTERNAL_DOMAINS.values():
        cfg_domains |= ext
    return host in cfg_domains


def _is_sponsored(soup):
    """Czy blok HTML to materiał promocyjny (po treści, nie po klasach CSS)."""
    return any(p in soup.get_text() for p in SPONSOR_PHRASES)


def _is_sponsored_title(title):
    """Czy tytuł wprost oznacza materiał promocyjny."""
    t = title.lower()
    return t.startswith("materiał promocyjny") or t.startswith("materiał sponsorowany") \
        or t.startswith("artykuł promocyjny") or t.startswith("artykuł sponsorowany") \
        or t.startswith("reklama")


def _sponsored_hrefs(soup):
    """Zbiera URL-e kart oznaczonych jako materiał promocyjny."""
    hrefs = set()
    for a in soup.find_all("a", href=True, attrs={"data-uuid-ui": True}):
        card = a.find_parent("article") or a.find_parent("div")
        if card and _is_sponsored(card):
            hrefs.add(a["href"])
    return hrefs


def _is_premium_card(card):
    """Czy karta oznacza artykuł premium (klasa PremiumLabel_* w środku)."""
    if card is None:
        return False
    return bool(card.select_one('[class*="PremiumLabel_"]'))


def _clean_title(title_el):
    """Tytuł z oddzielonymi labelami (np. 'W skrócie') od reszty tekstu.

    Onet wstawia w element tytułu labele jako osobne spany
    (ods-a-label-card / ods-a-content-label, np. 'W skrócie'). get_text()
    skleilby je z tytułem bez spacji, dlatego wyciągamy je i poprzedzamy
    nimi tytuł ze spacją.
    """
    if title_el is None:
        return ""
    clone = BeautifulSoup(str(title_el), "html.parser")
    labels = []
    for span in clone.select("span[class*='label-card'], span[class*='content-label']"):
        txt = " ".join(span.get_text().split())
        if txt:
            labels.append(txt)
        span.decompose()
    title = " ".join(clone.get_text().split())
    prefix = " ".join(labels)
    return f"{prefix} {title}" if prefix else title


def _card_title(card, a):
    """Tytuł karty (h3 lub link) z labelami oddzielonymi spacją."""
    h3 = card.find("h3") if card else None
    return _clean_title(h3 or a)


def extract_card_articles(soup, category):
    """Wyciąga artykuły z kart (a[data-uuid-ui]) — strona główna, feedy.

    Pomija materiały promocyjne. Duplikaty NIE są filtrowane — robi to
    aplikacja (dedup po link/uuid w database.upsert_article).
    """
    articles = []
    for a in soup.find_all("a", href=True, attrs={"data-uuid-ui": True}):
        href = a["href"]
        m = ARTICLE_URL_RE.search(href)
        if not m:
            continue
        if not _is_accept_domain(href, category):
            continue

        card = a.find_parent("article") or a.find_parent("div")
        if card and _is_sponsored(card):
            continue

        title = _card_title(card, a)
        if len(title) < 15:
            continue

        img = card.find("img") if card else None
        image = img.get("src") if img else ""

        articles.append({
            "uuid": a["data-uuid-ui"],
            "link": href,
            "title": title,
            "category": category,
            "image": image,
            "is_premium": 1 if _is_premium_card(card) else 0,
        })
    return articles


def extract_article_tags(soup, category):
    """Wyciąga wszystkie artykuły zamknięte w <article> (wszystkie typy kart).

    Na stronie głównej kategoria jest nadpisywana na podstawie sekcji
    <section data-section="..."> (np. news -> najnowsze, sport -> sport).
    Pomija materiały promocyjne i treści spoza domen redakcyjnych.
    Duplikaty NIE są filtrowane — robi to aplikacja.
    """
    articles = []
    for art in soup.find_all("article"):
        a = art.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not ARTICLE_URL_RE.search(href):
            continue
        if not _is_accept_domain(href, category):
            continue
        if _is_sponsored(art):
            continue

        h3 = art.find("h3") or a.find("h3")
        title = _clean_title(h3 or a)
        if len(title) < 15:
            continue
        if _is_sponsored_title(title):
            continue

        img = art.find("img")
        image = img.get("src") if img else ""

        articles.append({
            "uuid": a.get("data-uuid-ui", ""),
            "link": href,
            "title": title,
            "category": _section_category(art, category),
            "image": image,
            "is_premium": 1 if _is_premium_card(art) else 0,
        })
    return articles


def scrape_category(category):
    """Zwraca listę artykułów wykrytych na stronach kategorii (bez RSS)."""
    cfg = CATEGORIES[category]
    target_cat = cfg.get("category", category)
    found = {}

    for page_url in cfg["urls"]:
        try:
            html = fetch_html(page_url, bot=cfg.get("bot", False))
        except requests.RequestException:
            continue
        soup = BeautifulSoup(html, "html.parser")
        dates = _parse_next_data_dates(html)
        sponsored_hrefs = _sponsored_hrefs(soup)

        for art in extract_article_tags(soup, target_cat):
            art["published_at"] = dates.get(art["link"], "")
            _merge_article(found, art)

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href in sponsored_hrefs:
                continue
            if a.find_parent("article") is None and not a.get("data-uuid-ui"):
                continue
            m = ARTICLE_URL_RE.search(href)
            if not m:
                continue

            if not _is_accept_domain(href, target_cat):
                continue

            title = _clean_title(a)
            if len(title) < 15:
                continue
            if _is_sponsored_title(title):
                continue

            card = a.find_parent("article") or a.find_parent("div")
            _merge_article(found, {
                "title": title,
                "link": href,
                "category": _section_category(a, target_cat),
                "is_premium": 1 if _is_premium_card(card) else 0,
                "published_at": dates.get(href, ""),
            })

    # Artykuły ze strony głównej, które wylądowały w sekcjach ogólnych
    # (kategoria 'glowna'), dostają kategorię treści z domeny/ścieżki URL.
    for art in found.values():
        if art["category"] in ("glowna", "najnowsze"):
            art["category"] = _infer_category(art["link"])

    return sorted(found.values(), key=lambda x: x["title"].lower())


def extract_text(body):
    """Wyciąga akapity i nagłówki z treści artykułu."""
    parts = []
    for el in body.select("div.ods-a-body-text, h2.ods-a-h2, p, blockquote, li"):
        if el.select_one("div.ods-a-body-text"):
            continue
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    return "\n\n".join(parts)


def _parse_published(html):
    """Data publikacji z JSON-LD (datePublished) lub contentCreated.

    Pobieramy ją z już pobranego HTML artykułu — bez dodatkowych requestów.
    Zwraca ISO 8601 w UTC lub "".
    """
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if not m:
        m = re.search(r'"contentCreated"\s*:\s*"([^"]+)"', html)
    if not m:
        m = re.search(
            r'<time[^>]+class="[^"]*ods-m-date-authorship__publication[^"]*"[^>]*\sdatetime="([^"]+)"',
            html,
        )
    if not m:
        return ""
    return _to_utc_iso(m.group(1))


def _normalize_iso(raw):
    """Ujednolica format ISO 8601 do formy akceptowanej przez fromisoformat.

    Python < 3.11 odrzuca offset bez dwukropka (np. +0200) oraz sufiks 'Z' —
    Onet zwraca właśnie +0200.
    """
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw)


def _to_utc_iso(raw):
    """Parsuje ISO 8601 i zwraca ujednolicone ISO w UTC (lub '' gdy błąd)."""
    try:
        dt = datetime.fromisoformat(_normalize_iso(raw))
    except ValueError:
        return ""
    return dt.astimezone(timezone.utc).isoformat()


def _parse_next_data_dates(html):
    """Mapa URL -> data publikacji ze strony głównej (payload __NEXT_DATA__).

    Next.js wstrzykuje dane teaserów jako JSON; wpis artykułu ma pole
    'published' oraz URL (phoenixUrl / href / link.href). Gdy wpis nie ma
    własnego 'published', dziedziczymy go z najbliższego obiektu-rodzica.
    Zwraca dict link -> ISO 8601 w UTC.
    """
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    dates = {}
    stack = []

    def walk(o):
        if isinstance(o, dict):
            pushed = False
            pub = o.get("published")
            if isinstance(pub, str):
                norm = _to_utc_iso(pub)
                if norm:
                    stack.append(norm)
                    pushed = True
            urls = []
            for key in ("phoenixUrl", "href"):
                v = o.get(key)
                if isinstance(v, str) and ARTICLE_URL_RE.search(v):
                    urls.append(v)
            link = o.get("link")
            if isinstance(link, dict) and isinstance(link.get("href"), str) and ARTICLE_URL_RE.search(link["href"]):
                urls.append(link["href"])
            if stack:
                for u in urls:
                    dates[u] = stack[-1]
            for v in o.values():
                walk(v)
            if pushed:
                stack.pop()
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return dates


def migrate_legacy_categories():
    """Jednorazowa migracja starych wpisów 'glowna'/'najnowsze'.

    Artykuły zapisane z kategorią 'glowna' (strona główna bez sekcji) lub
    'najnowsze' (stary schemat) dostają kategorię treści wywnioskowaną z URL.
    Idempotentna — po pierwszym przebiegu nie ma już takich wpisów.
    """
    import database

    return database.migrate_categories(_infer_category)


def fetch_article_details(link):
    """Pobiera pełną treść, lead, główne zdjęcie i datę publikacji artykułu."""
    try:
        html = fetch_html(link)
        soup = BeautifulSoup(html, "html.parser")
    except requests.RequestException as e:
        return {"error": f"Nie udało się pobrać: {e}", "content": "", "lead": "", "image": "", "published_at": ""}

    body = soup.select_one("article.ods-article-body") or soup.select_one("article")
    lead_el = soup.select_one("article.ods-article-lead")
    image_el = soup.select_one('meta[property="og:image"]')

    return {
        "content": extract_text(body) if body else "",
        "lead": lead_el.get_text(" ", strip=True) if lead_el else "",
        "image": image_el.get("content", "") if image_el else "",
        "published_at": _parse_published(html),
    }