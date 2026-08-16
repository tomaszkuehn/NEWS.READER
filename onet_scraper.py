import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# Strona główna jest renderowana przez JS dla zwykłych UA;
# Googlebot dostaje pełny SSR, dlatego używamy jego UA tylko dla niej.
BOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

ARTICLE_URL_RE = re.compile(r"/(?:[a-z0-9-]+/)+[a-z0-9]{6,}(?:,[0-9a-f]{8})?(?:#[a-z0-9]+)?$")

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
# Sekcje reklamowe (bigbox*, oferty*, paid_promo itd.) nie są mapowane.
SECTION_TO_CATEGORY = {
    "pilnaExtra": "najnowsze",
    "importantnews": "najnowsze",
    "news": "najnowsze",
    "premium_only_for_sub": "najnowsze",
    "sport": "sport",
    "economy": "biznes",
    "lifestyle": "inspiracje",
    "tech": "technologie",
    "moto": "motoryzacja",
    "travel": "podroze",
    "popular": "najnowsze",
}


def _section_category(art, default):
    """Zwraca naszą kategorię dla <article> na podstawie sekcji data-section."""
    sec = art.find_parent("section", attrs={"data-section": True})
    if sec is None:
        return default
    return SECTION_TO_CATEGORY.get(sec["data-section"], default)


def _merge_article(found, art):
    """Dodaje artykuł z priorytetem dla kategorii z sekcji redakcyjnej.

    Jeśli ten sam link był już znaleziony w sekcji reklamowej (domyślnie
    'glowna'), a teraz wiemy, że należy do konkretnej kategorii, nadpisujemy.
    """
    link = art["link"]
    if link not in found:
        found[link] = art
        return
    if found[link]["category"] == "glowna" and art["category"] != "glowna":
        found[link] = art


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
    found = {}

    for page_url in cfg["urls"]:
        try:
            html = fetch_html(page_url, bot=cfg.get("bot", False))
        except requests.RequestException:
            continue
        soup = BeautifulSoup(html, "html.parser")
        sponsored_hrefs = _sponsored_hrefs(soup)

        for art in extract_article_tags(soup, category):
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

            if not _is_accept_domain(href, category):
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
                "category": _section_category(a, category),
                "is_premium": 1 if _is_premium_card(card) else 0,
            })

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
        return ""
    raw = m.group(1)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return ""
    return dt.astimezone(timezone.utc).isoformat()


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