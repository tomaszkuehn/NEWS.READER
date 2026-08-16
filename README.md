# News Reader

Prosty czytnik artykułów ze serwisów grupy Onet. Aplikacja okresowo scrapuje strony Onetu i zapisuje wykryte artykuły do lokalnej bazy SQLite, a następnie udostępnia je przez interfejs WWW (FastAPI + prosty frontend).

## Spis treści

- [Jak działa](#jak-działa)
- [Wymagania i instalacja](#wymagania-i-instalacja)
- [Uruchomienie](#uruchomienie)
- [Aplikacja Windows (tray + instalator)](#aplikacja-windows-tray--instalator)
- [API](#api)
- [Throttling odświeżeń](#throttling-odświeżeń)
- [Kategorie i źródła](#kategorie-i-źródła)
- [Jakie artykuły są zapisywane](#jakie-artykuły-są-zapisywane)
- [Jakie artykuły są pomijane](#jakie-artykuły-są-pomijane)
- [Kwalifikacja artykułów do grup (kategorii)](#kwalifikacja-artykułów-do-grup-kategorii)
- [Struktura bazy danych](#struktura-bazy-danych)
- [Implementacja](#implementacja)
- [Znane ograniczenia](#znane-ograniczenia)

## Jak działa

Całość to trzy moduły:

1. **`onet_scraper.py`** — pobiera strony i wyciąga artykuły:
   - `fetch_html()` — pobiera HTML (z losowym User-Agent tej instalacji, zob. [Losowy identyfikator przeglądarki](#losowy-identyfikator-przeglądarki); dla strony głównej z UA Googlebota, zob. [Strona główna Onetu](#strona-główna-onetu)).
   - `scrape_category()` — główna pętla dla jednej kategorii; łączy ekstrakcję z tagów `<article>` z generycznym skanem wszystkich linków.
   - `extract_article_tags()` — wyciąga artykuły z tagów `<article>` (wszystkie typy kart: StandardCard, LinkCard, SmallCard, BigCard, CartoonCard).
   - `fetch_article_details()` — pobiera treść artykułu po jego otwarciu.

2. **`refresher.py`** — throttling odświeżeń (min. 140 s, limit 15/h), coverage i automatyczny harmonogram w tle (co 10 min ± 15 s, potem co 1 h).

3. **`database.py`** — warstwa SQLite:
   - `upsert_article()` — zapis/aktualizacja (dedup po `link`).
   - `get_articles()` — filtrowanie, wyszukiwanie, sortowanie.
   - `cleanup_old()` — usuwanie artykułów nieaktualizowanych dłużej niż `RETENTION_DAYS`.

4. **`app.py`** — serwer FastAPI udostępniający API i statyczny frontend (`index.html`).

Przepływ:

```
POST /api/refresh
  (throttling: min. 140 s, limit 15/h) -> status waiting|quota|refreshing|ok
  ok: for każda kategoria w CATEGORIES:
          scrape_category(kategoria) -> lista artykułów
          for każdy artykuł: upsert_article(artykuł)
      cleanup_old()
  coverage = znane / znalezione  (>=90% -> tryb slow)
Wątek w tle: co 10 min ±15s (fast) albo co 1h (slow) wywołuje refresh(trigger="auto")
```

Odświeżenie przechodzi przez **wszystkie** kategorie po kolei. Duplikaty są obsługiwane dwupoziomowo: w obrębie jednego scrapu (słownik kluczowany po `link`) oraz w bazie (klucz główny `link`).

## Wymagania i instalacja

- Python 3.9+
- Zależności w `requirements.txt`:

```
feedparser==6.0.11
requests==2.32.3
beautifulsoup4==4.12.3
fastapi==0.111.0
uvicorn==0.30.1
pystray==0.19.5
pywin32==312
```

```bash
pip install -r requirements.txt
```

## Uruchomienie

```bash
python app.py
```

Serwer startuje na `http://localhost:8000`. Frontend jest dostępny pod `/`.

### Odświeżanie artykułów

Kliknij przycisk **Odśwież** w interfejsie lub wywołaj ręcznie:

```bash
curl -X POST http://localhost:8000/api/refresh
```

Baza jest inicjalizowana automatycznie przy starcie serwera.

## Aplikacja Windows (tray + instalator)

Oprócz uruchamiania z kodu można zbudować gotową aplikację dla **Windows 7 / 10 / 11**:

- **`tray.py`** — launcher okienkowy: startuje serwer FastAPI w wątku i pokazuje ikonę
  w zasobniku systemowym (pystray) z menu: otwórz czytnik, odśwież artykuły, folder danych,
  wyjdź. Blokuje drugą instancję (mutex `Global\NewsReader.SingleInstance`) i loguje
  do `%APPDATA%\NewsReader\news-reader.log`.
- **Wersja spakowana (PyInstaller)** — wszystkie biblioteki wbudowane w jeden `NewsReader.exe`.
  `index.html` jest rozpakowywany z archiwum (`sys._MEIPASS`), a baza `articles.db` i logi
  trafiają do `%APPDATA%\NewsReader` — nie do katalogu temp onefile (który jest czyszczony
  przy zamknięciu).
- **Instalator (`NewsReader-Setup.exe`)** — budowany przenośnym NSIS. Instaluje aplikację
  per-user (bez UAC) do `%LOCALAPPDATA%\NewsReader`, tworzy skróty w menu Start i na pulpicie,
  oferuje autostart z systemem oraz odinstalator. Dane użytkownika (`%APPDATA%\NewsReader`)
  są przy odinstalowaniu celowo zachowywane.
- **Wykrywanie instalacji i aktualizacja (upgrade)** — instalator sprawdza w `.onInit`,
  czy aplikacja jest już zainstalowana (klucz rejestru `Add/Remove Programs` +
  istnienie `NewsReader.exe`). Jeśli tak: pyta o zgodę na aktualizację (w trybie cichym
  `/S` aktualizuje automatycznie), zatrzymuje działającą aplikację (`taskkill`), nadpisuje
  pliki i odświeża wersję w rejestrze. Katalog instalacji jest wczytywany z poprzedniego
  wpisu rejestru. Dane użytkownika (artykuły, ustawienia, identyfikator przeglądarki)
  pozostają nietknięte.

### Budowanie dla Windows 7

Windows 7 nie obsługuje Pythona ≥ 3.10, dlatego budowanie odbywa się z **przenośnego Pythona
3.9** (wersja embed, bez instalacji). Wszystkie narzędzia budowania są przenośne — **nic nie
jest instalowane w systemie**:

1. Pobierz `python-3.9.13-embed-amd64.zip`, rozpakuj np. do `toolchain\py39` i włącz
   `import site` w pliku `python39._pth`.
2. Zainstaluj pip i zależności:
   ```
   python -m pip install -r requirements.txt pillow pyinstaller
   ```
3. Wygeneruj ikonę: `python make_icon.py` (tworzy `app.ico`).
4. Zbuduj exe:
   ```
   python -m PyInstaller newsreader.spec --noconfirm --clean --distpath dist --workpath build
   ```
   (wynik: `dist\NewsReader.exe` — wersja GUI, bez konsoli).
5. Zbuduj instalator przenośnym NSIS:
   ```
   makensis.exe NewsReader.nsi
   ```
   (wynik: `dist\NewsReader-Setup.exe`).

### Ręczne uruchomienie (bez instalatora)

Skompilowany `NewsReader.exe` można uruchomić bezpośrednio — po chwili pojawi się ikona
w tray i otworzy czytnik w domyślnej przeglądarce.

## API

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/` | Frontend |
| GET | `/api/categories` | Lista kategorii |
| POST | `/api/refresh` | Prosi o odświeżenie (z throttlingiem, zob. [Throttling odświeżeń](#throttling-odświeżeń)) |
| GET | `/api/refresh/status` | Stan odświeżania (przerwa, limit/h, tryb, coverage) |
| GET | `/api/articles` | Lista artykułów (filtry: `category`, `q`, `sort`, `unread`) |
| GET | `/api/articles/{link}/read` | Oznacza jako przeczytane i pobiera pełną treść |
| GET | `/api/health` | Status serwera |

## Throttling odświeżeń

Aby nie przeciążać serwerów Onetu (i nie narazić się na blokadę), odświeżanie jest
ograniczane na trzy sposoby (`refresher.py`):

1. **Minimalna przerwa między odświeżeniami: 140 s.** Odświeżenie na żądanie użytkownika
   w krótszym odstępie nie wykonuje scrapera — odpowiedź `/api/refresh` ma wtedy status
   `waiting` z liczbą sekund do upłynięcia przerwy, a interfejs pokazuje odliczanie
   ("Czekam na odświeżenie… 2m 15s") i po jego zakończeniu automatycznie ponawia prośbę.

2. **Limit 15 odświeżeń na godzinę** (okno przesuwne). Po jego wyczerpaniu odpowiedź ma
   status `quota` z czasem oczekiwania do pierwszego wolnego miejsca w oknie.

3. **Automatyczne odświeżanie w tle** (osobny wątek, startowany przy starcie serwera):
   - dopóki **coverage < 90%** (czyli mniej niż 90% artykułów z Onetu jest już w bazie),
     skanuje co **10 minut ± 15 s** (losowy jitter, żeby wzorzec nie był przewidywalny),
   - po osiągnięciu **coverage ≥ 90%** przechodzi w tryb spokojny: co **1 godzinę**.
   - Coverage liczony w trakcie samego skanowania (udział artykułów już obecnych w bazie
     wśród wszystkich znalezionych) — bez drugiego scrapowania stron.

Status odświeżania (`/api/refresh/status`) zwraca: aktualny tryb (`fast`/`slow`), ostatni
coverage, czas do następnego dozwolonego odświeżenia (osobno dla przerwy i limitu godzinowego),
liczbę odświeżeń w bieżącej godzinie.

## Kategorie i źródła

Kategorie i ich URL-e są zdefiniowane w `CATEGORIES` (`onet_scraper.py`):

| Kategoria | Źródła |
|---|---|
| `glowna` | `https://www.onet.pl` (User-Agent Googlebota) |
| `najnowsze` | `wiadomosci.onet.pl/najnowsze` |
| `wiadomosci` | `wiadomosci.onet.pl` (+ `/kraj`, `/swiat`, `/polska`) |
| `sport` | `przegladsportowy.onet.pl` (+ `/pilka-nozna`, `/tenis`, `/koszykowka`) |
| `biznes` | `biznes.onet.pl`, `businessinsider.com.pl` (+ `/biznes`, `/gospodarka`, `/prawo`, `/finanse`, `/technologie`, `/praca`, `/nieruchomosci`) |
| `kultura` | `kultura.onet.pl` (+ `/film`, `/muzyka`, `/ksiazki`, `/seriale`) |
| `technologie` | `technologie.onet.pl` (+ `/gry`) |
| `inspiracje` | `kobieta.onet.pl` |
| `motoryzacja` | `moto.onet.pl`, `auto-swiat.pl/wiadomosci` |
| `podroze` | `podroze.onet.pl` (+ `/podroze`) |

### Strona główna Onetu

Strona główna `www.onet.pl` jest renderowana przez JavaScript dla zwykłych przeglądarek — statyczny HTML zawiera tylko puste szkielety kart. Żeby otrzymać pełny SSR, scraper używa **User-Agent Googlebota** (`BOT_HEADERS`). Bez tego strona główna nie zawiera artykułów (testy wykazały 0 trafień zamiast ~200).

## Jakie artykuły są zapisywane

Artykuł jest zapisywany, gdy spełnia **wszystkie** poniższe warunki:

1. **Adres URL pasuje do `ARTICLE_URL_RE`** — końcówka ścieżki jest postaci:
   - klasycznej: `/kategoria/slug/ID` (ID = 6+ znaków alfanumerycznych),
   - nowszej: `/slug,hex8` (np. `sbt420g,30bc1058`),
   - skróconej bez kategorii: `/slug/ID`,
   - z fragmentem kotwicy `#pco` na końcu.
   - Odrzucane są gry (`/gry/pl/wyzwanie-lexi`), oferty (`/oferta/...`), strony zbiorcze i URL-e z `?query`.

2. **Domena linku jest dozwolona** (`_is_accept_domain`):
   - `onet.pl` i wszystkie subdomeny `*.onet.pl`,
   - domeny partnerów z `EXTERNAL_DOMAINS`: `auto-swiat.pl`, `businessinsider.com.pl`, `komputerswiat.pl`, `przegladsportowy.onet.pl`, `newsweek.pl`, `fakt.pl` (w tym `ludzie.fakt.pl`), `plejada.pl`, `ofeminin.pl`, `noizz.pl`, `medonet.pl` (w tym `zywienie.medonet.pl`), `forbes.pl`, `gratka.pl`, `lamoda.pl`.

3. **Tytuł ma co najmniej 15 znaków.**

4. **Nie jest materiałem promocyjnym** (zob. [Jakie artykuły są pomijane](#jakie-artykuły-są-pomijane)).

Dla każdego artykułu zapisywane są: `uuid` (atrybut `data-uuid-ui`), `link`, `title`, `category`, `image` (zdjęcie z karty) oraz flagi `is_premium`.

Pełna treść, lead i zdjęcie `og:image` są pobierane dopiero, gdy użytkownik **otworzy** artykuł (`/api/articles/{link}/read`).

## Jakie artykuły są pomijane

Pomijane są następujące treści:

1. **Materiały promocyjne / sponsorowane** — wykrywane **po treści**, nie po klasach CSS (klasy CSS Onetu są hashowane i zmieniają się przy każdym buildzie):
   - w treści karty pojawia się jedno z wyrażeń `SPONSOR_PHRASES`: *materiał promocyjny*, *materiał sponsorowany*, *artykuł promocyjny*, *artykuł sponsorowany*, *sponsorowane*, *sponsoring*, *reklama*;
   - tytuł zaczyna się od *Materiał promocyjny* / *Materiał sponsorowany* / *Artykuł promocyjny* / *Artykuł sponsorowany* / *Reklama* (`_is_sponsored_title`);
   - lista adresów kart sponsorowanych (`_sponsored_hrefs`) jest budowana przed generycznym skanem linków, więc te URL-e nigdy nie trafiają do wyników.

2. **Treści spoza dozwolonych domen** — np. `travel.businessinsider.com.pl/oferta/...`, `gazetkarnia.pl/...`, `morizon.pl/...` (o ile nie są w `EXTERNAL_DOMAINS`).

3. **Gry i interaktywne widgety** — `/gry/pl/...`, `gameplanet.onet.pl` (URL-e nie pasują do `ARTICLE_URL_RE`).

4. **Sekcje reklamowe na stronie głównej** (`bigbox*`, `oferty*`, `paid_promo` itd.) — nie są mapowane do kategorii, a ich artykuły trafiają do `glowna` tylko jako fallback (i są zastępowane przez właściwe kategorie, gdy artykuł pojawi się też w sekcji redakcyjnej).

5. **Artykuły z tytułem krótszym niż 15 znaków** — zwykle to etykiety, gry lub podstrony, nie artykuły.

6. **Linki, które nie są kartami artykułów** — generyczny skan linków (w `scrape_category`) akceptuje tylko linki wewnątrz `<article>` **lub** z atrybutem `data-uuid-ui` (unikalne ID karty). To odfiltrowuje podstrony serwisu, które przypadkiem pasują do wzorca URL (np. Onet Chat AI `/czat/konwersacja` „Zadaj własne pytanie", strona autorów `/autorzy/...`, prognoza pogody `/prognoza-pogody/dlugoterminowa`).

7. **Stare artykuły** — `cleanup_old()` usuwa wpisy nieaktualizowane przez `RETENTION_DAYS` (7 dni), na podstawie `last_seen`.

## Kwalifikacja artykułów do grup (kategorii)

Kategoria artykułu jest ustalana w trzech krokach:

1. **Strony dedykowanych kategorii** — `scrape_category(kategoria)` scrapyje URL-e danej kategorii; artykuł dostaje kategorię tej strony.

2. **Sekcje strony głównej** — na `www.onet.pl` artykuły są poukładane w sekcjach `<section data-section="...">`. Mapowanie `SECTION_TO_CATEGORY` przypisuje im właściwe kategorie:

   | Sekcja na stronie głównej | Kategoria w aplikacji |
   |---|---|
   | `news`, `importantnews`, `pilnaExtra`, `premium_only_for_sub`, `popular` | `najnowsze` |
   | `sport` | `sport` |
   | `economy` | `biznes` |
   | `lifestyle` | `inspiracje` |
   | `tech` | `technologie` |
   | `moto` | `motoryzacja` |
   | `travel` | `podroze` |
   | pozostałe (m.in. sekcje reklamowe `bigbox*`, `oferty*`) | `glowna` (fallback) |

3. **Priorytet kategorii** — jeśli ten sam artykuł pojawia się w sekcji reklamowej (`glowna`) i w sekcji redakcyjnej (np. `sport`), wygrywa kategoria redakcyjna. Mechanizmy:
   - `_merge_article()` — dedup w obrębie jednego scrapu strony głównej: nadpisuje `glowna` → konkretną kategorią,
   - `database.upsert_article()` — przy zapisie do bazy: jeśli rekord ma kategorię `glowna`, a nowa wartość to konkretna kategoria, kategoria jest nadpisywana.

Dzięki temu ten sam link nigdy nie występuje w więcej niż jednej kategorii (testy potwierdzają: 0 duplikatów między kategoriami).

## Struktura bazy danych

Plik: `articles.db` (SQLite). Tabela `articles`:

| Kolumna | Typ | Opis |
|---|---|---|
| `link` | TEXT (PK) | URL artykułu — klucz dedup |
| `uuid` | TEXT | Unikalne ID z atrybutu `data-uuid-ui` |
| `title` | TEXT | Tytuł |
| `category` | TEXT | Kategoria (zob. [Kwalifikacja](#kwalifikacja-artykułów-do-grup-kategorii)) |
| `summary` | TEXT | Rezerwa (puste) |
| `content` | TEXT | Pełna treść (wypełniana po otwarciu) |
| `image` | TEXT | URL zdjęcia karty |
| `lead` | TEXT | Lead artykułu (po otwarciu) |
| `is_read` | INTEGER | 0/1 — przeczytane |
| `is_premium` | INTEGER | 0/1 — artykuł premium |
| `published_at` | TEXT | Data publikacji (ISO UTC — ze strony głównej `__NEXT_DATA__` lub po otwarciu artykułu) |
| `first_seen` | TEXT | ISO — pierwsze wykrycie |
| `last_seen` | TEXT | ISO — ostatnia aktualizacja |

Migracje są wykonywane automatycznie w `init_db()` (`ALTER TABLE ... ADD COLUMN` dla brakujących kolumn `uuid` / `is_premium` / `published_at`), więc istniejąca baza jest aktualizowana bez utraty danych.

## Implementacja

### Wykrywanie artykułów premium

Artykuł premium jest oznaczany, gdy wewnątrz karty `<article>` znajduje się element z klasą `PremiumLabel_*` (`_is_premium_card`). Wykrywane jest po **prefiksie klasy** — hash w sufiksie klasy (np. `PremiumLabel_container__d8RXl`) zmienia się przy buildach Onetu, ale prefiks `PremiumLabel_` jest stabilny. Zapisywane jako `is_premium` w bazie.

### Dlaczego nie klasa `SponsoringLabel` do filtrów sponsorowanych

Początkowo planowano filtrować materiały promocyjne po klasie `.SponsoringLabel_SponsoringLabelDesktop__43xKV`, ale:
- Onet zmienia strukturę strony i te hashowane klasy znikają/zmieniają się,
- dlatego detekcja opiera się na **tekście** (frazy *materiał promocyjny* itd.) i tytule, co jest odporne na zmiany layoutu.

### Losowy identyfikator przeglądarki

Każda instalacja przy pierwszym uruchomieniu losuje **losowy User-Agent** z puli
realistycznych współczesnych przeglądarek (`USER_AGENT_POOL` w `onet_scraper.py`)
i zapisuje go w `browser_identity.txt` w katalogu danych
(`%APPDATA%\NewsReader` w wersji skompilowanej). Identyfikator jest **stały dla
danej instalacji** (jak w prawdziwej przeglądarce) i **różny między instalacjami** —
dzięki temu Onet nie widzi tego samego UA od wszystkich użytkowników, co utrudnia
rozpoznanie i zablokowanie scrapera. Strona główna (`www.onet.pl`) nadal korzysta
z UA Googlebota, bo tylko wtedy Onet serwuje pełny SSR.

### Dlaczego Googlebot dla strony głównej

Bez UA Googlebota `www.onet.pl` zwraca pusty szkielet (strona renderowana po stronie klienta). Dla Googlebota Onet serwuje pełny HTML. To najprostsze, bezgłowe rozwiązanie — bez Selenium/Playwright.

### Sortowanie i filtry w API

`get_articles()` obsługuje: sortowanie (`newest`, `oldest`, `title`, `read`), wyszukiwanie po `title`/`summary` oraz filtr nieprzeczytanych.

Sortowanie `newest` i `oldest` opiera się na dacie publikacji (`published_at`), z fallbackiem na `last_seen` dla artykułów bez znanej daty (`COALESCE(NULLIF(published_at, ''), last_seen)`). Dzięki temu lista jest układana wg rzeczywistej daty publikacji, a nie momentu wykrycia. Sortowanie `read` nadal używa `last_seen`, aby przeczytane artykuły pozostawały na górze.

### Data publikacji artykułów

Data publikacji (`published_at`) pochodzi z dwóch źródeł:

1. **Strona główna Onetu** — podczas scrapowania `glowna` parsujemy payload
   `__NEXT_DATA__` (JSON Next.js) i dopasowujemy pole `published` wpisów teaserów
   do linków kart (URL `phoenixUrl` / `link.href`, dziedziczone z obiektu-rodzica).
   Dzięki temu większość artykułów z strony głównej (~92%) ma datę od razu w liście,
   bez otwierania.
2. **Po otwarciu artykułu** — data jest wyciągana z HTML artykułu — **z tej samej strony, którą już pobieramy
   po otwarciu**, bez dodatkowych requestów do Onetu. Źródła, sprawdzane w kolejności:
   JSON-LD (`"datePublished"`), `"contentCreated"`, a na końcu element
   `<time class="ods-m-date-authorship__publication">` (atrybut `datetime`) — ten ostatni
   występuje w artykułach, które nie mają znaczników JSON-LD z datą. Zapisuje się ją do bazy przy
   otwarciu (`mark_read_and_store`) i uzupełnia artykuły, których nie było na
   stronie głównej (np. z dedykowanych stron kategorii).

W podglądzie oraz na liście pokazywana jest data publikacji, jeśli jest znana
(inaczej czas wykrycia `last_seen`). W podglądzie data zawiera również rok
(np. `08.10.2024, 11:20`).

### Ostrzeżenie o starych artykułach

Gdy data publikacji otwartego artykułu jest starsza niż **7 dni**, w podglądzie na górze
treści pojawia się czerwony pasek **„Uwaga, wiadomość starsza niż 7 dni”**. To sygnał dla
czytelnika, że wiadomość może być nieaktualna — czytnik pokazuje bowiem także stare treści
z odświeżanych stron.

### Zachowanie podglądu podczas odświeżania

Po otwarciu artykułu jego treść jest wyświetlana w prawym panelu. Automatyczne odświeżanie (lub ręczne przyciskiem "Odśwież") przeładowuje listę z API, ale **zachowuje aktualnie otwarty podgląd**, jeśli wybrany artykuł nadal znajduje się w wynikach. Podgląd jest wyczyszczony tylko wtedy, gdy artykuł zostanie odfiltrowany (np. po zmianie kategorii, wyszukiwania lub filtru "tylko nieprzeczytane").

### Style interfejsu

Interfejs ma 3 style wybierane w headerze (zapamiętywane w `localStorage`):
- **czarny na białym** (`light`),
- **jasny na ciemnym** (`dark`),
- **sepia / kremowy** (`sepia`, domyślny).

### Menu kategorii

Zakładki kategorii mają kolorowe kropki spójne z oznaczeniami artykułów; pozycja **Wszystkie** jest przesunięta na koniec (skrajne prawo).

## Znane ograniczenia

- **Struktura HTML Onetu zmienia się często** — reguły bazują na `data-uuid-ui`, tagach `<article>` i prefiksach klas, ale ekstremalna przebudowa strony może wymagać aktualizacji selektorów.
- **Adresy URL mają wiele formatów** — `ARTICLE_URL_RE` pokrywa obecnie 4 znane warianty (klasyczny, `slug,hex8`, skrócony, z kotwicą), ale Onet może wprowadzać kolejne.
- **`feedparser` w requirements nie jest używany** — obecnie scraping odbywa się wyłącznie przez BeautifulSoup; zależność pozostała z wcześniejszych wersji.
- **Pełna treść jest pobierana leniwie** (dopiero przy otwarciu artykułu), więc lista artykułów nie zawiera treści.
