"""Pobieranie i parsowanie partii z Chess.com i Lichess.

Moduł nie zależy od Streamlita, więc da się go testować (patrz tests/).
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API_TIMEOUT = 15  # sekundy na pojedyncze zapytanie (czas między kolejnymi bajtami)
MAX_MOVE_TIME_SECONDS = 300
CHESSCOM_WORKERS = 3  # Chess.com zaleca zapytania sekwencyjne; więcej równoległych grozi 429
PLAYER_CACHE_TTL = 15 * 60  # jak długo pełny wynik gracza jest trzymany w pamięci
PLAYER_CACHE_MAX = 50
DEFAULT_TZ = "Europe/Warsaw"
USER_AGENT = "ChessStats (github.com/BartoszKrop/ChessCom-Analiza)"

DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
LICHESS_SKIP_STATUS = {"aborted", "noStart", "created", "started", "unknownFinish"}
DAYS = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Czw", 4: "Pt", 5: "Sb", 6: "Nd"}

# Kolumny surowe (z API). Kolumny czasowe (Timestamp, Godzina, ...) dokłada localize_games().
RAW_COLS = ["Konto", "Platforma", "EndTs", "Tryb", "Wynik", "ELO", "Elo_Rywala", "Ruchy", "Debiut",
            "Debiut_Grupa", "Przeciwnik", "Kolor", "Powod", "PGN_Raw", "Link", "MoveTimes"]
TIME_COLS = ["Timestamp", "Godzina", "Dzień", "Dzień_Nr", "Data", "Miesiąc"]


class PlayerNotFound(Exception):
    pass


class ApiError(Exception):
    pass


# ---------------------------------------------------------------- parsowanie
def get_opening_group(opening_name):
    name = opening_name.lower()
    groups = [
        (("sicilian",), "Sicilian Defense"),
        (("french",), "French Defense"),
        (("caro-kann", "caro kann"), "Caro-Kann Defense"),
        (("ruy lopez", "spanish"), "Ruy Lopez"),
        (("italian", "giuoco piano"), "Italian Game"),
        (("scotch",), "Scotch Game"),
        (("vienna",), "Vienna Game"),
        (("four knights",), "Four Knights Game"),
        (("two knights",), "Two Knights Defense"),
        (("petrov", "russian"), "Petrov's Defense"),
        (("philidor",), "Philidor Defense"),
        (("bishop's opening", "bishops opening"), "Bishop's Opening"),
        (("scandinavian",), "Scandinavian Defense"),
        (("alekhine",), "Alekhine's Defense"),
        (("pirc",), "Pirc Defense"),
        (("modern defense",), "Modern Defense"),
        (("queens gambit", "queen's gambit"), "Queen's Gambit"),
        (("kings gambit", "king's gambit"), "King's Gambit"),
        (("kings indian", "king's indian"), "King's Indian Defense"),
        (("queens indian", "queen's indian"), "Queen's Indian Defense"),
        (("nimzo",), "Nimzo-Indian Defense"),
        (("bogo-indian", "bogo indian"), "Bogo-Indian Defense"),
        (("grunfeld", "grünfeld", "gruenfeld"), "Grünfeld Defense"),
        (("slav",), "Slav Defense"),
        (("catalan",), "Catalan Opening"),
        (("london",), "London System"),
        (("trompowsky",), "Trompowsky Attack"),
        (("benoni",), "Benoni Defense"),
        (("benko", "volga"), "Benko Gambit"),
        (("dutch",), "Dutch Defense"),
        (("english",), "English Opening"),
        (("reti", "réti"), "Réti Opening"),
        (("bird",), "Bird's Opening"),
        (("king's pawn", "kings pawn"), "King's Pawn Opening"),
        (("queen's pawn", "queens pawn"), "Queen's Pawn Opening"),
    ]
    for keys, group in groups:
        if any(k in name for k in keys):
            return group
    fallback = opening_name.split(':')[0].strip()
    for keyword in [" Defense", " Opening", " Game", " Gambit", " System", " Attack"]:
        idx = fallback.lower().find(keyword.lower())
        if idx != -1:
            return fallback[:idx + len(keyword)].title()
    return fallback.title()


def extract_opening(pgn):
    if not pgn:
        return "Nieznany"
    opening_tag = re.search(r'\[Opening "(.*?)"\]', pgn)
    if opening_tag:
        return opening_tag.group(1).strip()
    match = re.search(r'openings/(.*?)"', pgn)
    if not match:
        return "Inny"
    slug = match.group(1)
    # Chess.com koduje apostrofy jako myślniki (King-s-Pawn → King's-Pawn)
    slug = re.sub(r'(?<=[A-Za-z])-s(?=-[A-Z]|-$)', "'s", slug)
    result = slug.replace('-', ' ').title()
    return re.sub(r"(?<=[A-Za-z])'S\b", "'s", result)


def opening_for_user(opening_name, is_white):
    if not opening_name:
        return "Nieznany"
    parts = [p.strip() for p in str(opening_name).split(":") if p.strip()]
    if not parts:
        return "Nieznany"
    if is_white or len(parts) == 1:
        return parts[0]
    role_keywords = r"\b(defen[sc]e|counter(?:gambit)?|gambit|system|attack)\b"
    for part in parts[1:] + [parts[0]]:
        if re.search(role_keywords, part, flags=re.IGNORECASE):
            return part
    return parts[1]


def pgn_movetext(pgn):
    """Sam zapis ruchów: bez nagłówków [Tag "..."] i komentarzy {...} (np. zegara)."""
    if not pgn:
        return ""
    text = re.sub(r'^\s*\[[^\]]*\]\s*$', "", pgn, flags=re.MULTILINE)
    text = re.sub(r'\{[^}]*\}', " ", text)
    return text


def extract_moves_count(pgn):
    """Liczba pełnych ruchów. Liczy numery ruchów tylko w samym zapisie partii,
    żeby nie łapać cyfr z dat w nagłówkach ani z zegara [%clk 0:02:48.4]."""
    matches = re.findall(r'(?<![\d.])(\d+)\.', pgn_movetext(pgn))
    return max((int(m) for m in matches), default=0)


def _clock_to_seconds(clock_text):
    try:
        parts = clock_text.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return 0.0
    except (ValueError, TypeError):
        return 0.0


def _clock_deltas(my_clocks):
    deltas = []
    for i in range(1, len(my_clocks)):
        d = my_clocks[i - 1] - my_clocks[i]
        if 0 <= d <= MAX_MOVE_TIME_SECONDS:
            deltas.append(round(d, 2))
    return deltas


def extract_move_times_from_pgn(pgn, is_white):
    clocks = re.findall(r'\[%clk ([0-9:\.]+)\]', pgn or "")
    sec = [_clock_to_seconds(c) for c in clocks]
    my_clocks = sec[0 if is_white else 1::2]
    if len(my_clocks) < 2:
        return []
    return _clock_deltas(my_clocks)


def extract_move_times_from_lichess_clocks(clocks, is_white):
    if not clocks or len(clocks) < 4:
        return []
    my_clocks = [float(c) / 100 for c in clocks[0 if is_white else 1::2]]
    return _clock_deltas(my_clocks)


def parse_chesscom_game(g, user, k_id):
    """Jedna partia z archiwum Chess.com → słownik wiersza albo None (pomijamy)."""
    if "end_time" not in g or g.get("rules", "chess") != "chess":
        return None
    is_w = g["white"]["username"].lower() == user.lower()
    me, opp = (g["white"], g["black"]) if is_w else (g["black"], g["white"])
    my_r, opp_r = me["result"], opp["result"]
    out = "Wygrane" if my_r == "win" else ("Remisy" if my_r in DRAW_RESULTS else "Przegrane")
    pgn = g.get("pgn", "")
    deb = opening_for_user(extract_opening(pgn), is_w)
    return {
        "Konto": k_id, "Platforma": "Chess.com", "EndTs": int(g["end_time"]),
        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out,
        "ELO": me.get("rating", 0), "Elo_Rywala": opp.get("rating", 0),
        "Ruchy": extract_moves_count(pgn), "Debiut": deb, "Debiut_Grupa": get_opening_group(deb),
        "Przeciwnik": opp["username"], "Kolor": "Białe" if is_w else "Czarne",
        "Powod": my_r if out == "Przegrane" else opp_r, "PGN_Raw": pgn, "Link": g.get("url", ""),
        "MoveTimes": extract_move_times_from_pgn(pgn, is_w),
    }


def parse_lichess_game(g, user, k_id):
    """Jedna partia z eksportu Lichess (ndjson) → słownik wiersza albo None (pomijamy)."""
    if g.get("status") in LICHESS_SKIP_STATUS or g.get("variant", "standard") != "standard":
        return None
    white_name = g["players"]["white"].get("user", {}).get("name", "")
    my_col = "white" if white_name.lower() == user.lower() else "black"
    opp_col = "black" if my_col == "white" else "white"
    winner = g.get("winner")
    out = "Wygrane" if winner == my_col else ("Przegrane" if winner == opp_col else "Remisy")
    moves = g.get("moves", "").split()
    deb = opening_for_user(g.get("opening", {}).get("name", "Nieznany"), my_col == "white")
    # lastMoveAt = koniec partii, tak samo jak end_time w Chess.com
    end_ms = g.get("lastMoveAt") or g.get("createdAt")
    return {
        "Konto": k_id, "Platforma": "Lichess", "EndTs": int(end_ms // 1000),
        "Tryb": g.get("speed", "Inne").capitalize(), "Wynik": out,
        "ELO": g["players"][my_col].get("rating", 0), "Elo_Rywala": g["players"][opp_col].get("rating", 0),
        "Ruchy": (len(moves) + 1) // 2, "Debiut": deb, "Debiut_Grupa": get_opening_group(deb),
        "Przeciwnik": g["players"][opp_col].get("user", {}).get("name", "Anonim"),
        "Kolor": "Białe" if my_col == "white" else "Czarne",
        "Powod": g.get("status"), "PGN_Raw": g.get("moves", ""), "Link": f"https://lichess.org/{g['id']}",
        "MoveTimes": extract_move_times_from_lichess_clocks(g.get("clocks", []), my_col == "white"),
    }


def localize_games(df, tz_name=DEFAULT_TZ):
    """Dokłada kolumny czasowe w strefie użytkownika (zamiast strefy serwera)."""
    try:
        tz = ZoneInfo(tz_name or DEFAULT_TZ)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    out = df.copy()
    if out.empty:
        for c in TIME_COLS:
            out[c] = pd.Series(dtype="object")
        return out
    ts = pd.to_datetime(out["EndTs"], unit="s", utc=True).dt.tz_convert(tz).dt.tz_localize(None)
    out["Timestamp"] = ts
    out["Godzina"] = ts.dt.hour
    out["Dzień_Nr"] = ts.dt.weekday
    out["Dzień"] = out["Dzień_Nr"].map(DAYS)
    out["Data"] = ts.dt.date
    out["Miesiąc"] = ts.dt.strftime("%Y-%m")
    return out


# ---------------------------------------------------------------- pobieranie
def _get(url, headers=None, timeout=API_TIMEOUT, stream=False):
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    for attempt in range(3):
        try:
            res = requests.get(url, headers=h, timeout=timeout, stream=stream)
        except requests.RequestException as e:
            if attempt == 2:
                raise ApiError(f"Brak połączenia z API ({e.__class__.__name__}).") from e
            time.sleep(1 + attempt)
            continue
        if res.status_code == 429:
            wait = float(res.headers.get("Retry-After", 0) or 0) or (5 * (attempt + 1))
            if attempt == 2:
                raise ApiError("Przekroczono limit zapytań API (429). Spróbuj za minutę.")
            time.sleep(min(wait, 60))
            continue
        return res
    raise ApiError("Nie udało się pobrać danych.")


def _current_month_suffix():
    now = datetime.now(timezone.utc)
    return f"/{now.year}/{now.month:02d}"


@lru_cache(maxsize=1000)
def _chesscom_finished_month(url, user):
    """Zakończone miesiące się nie zmieniają, więc trzymamy je w pamięci na stałe."""
    return tuple(_chesscom_month(url, user))


def _chesscom_month(url, user):
    res = _get(url)
    if res.status_code != 200:
        raise ApiError(f"Chess.com zwrócił {res.status_code} dla {url.rsplit('/', 2)[-2:]}.")
    k_id = f"{user} (C)"
    rows = []
    for g in res.json().get("games", []):
        row = parse_chesscom_game(g, user, k_id)
        if row:
            rows.append(row)
    return rows


def fetch_chesscom(user, progress_cb=None):
    p_res = _get(f"https://api.chess.com/pub/player/{user}")
    if p_res.status_code == 404:
        raise PlayerNotFound(user)
    if p_res.status_code != 200:
        raise ApiError(f"Chess.com zwrócił błąd {p_res.status_code}.")
    a_res = _get(f"https://api.chess.com/pub/player/{user}/games/archives")
    if a_res.status_code != 200:
        raise ApiError(f"Chess.com zwrócił błąd {a_res.status_code} (lista archiwów).")
    archives = a_res.json().get("archives", [])
    current = _current_month_suffix()

    def load(url):
        # Bieżący miesiąc (i ostatni z listy) pobieramy zawsze na nowo, resztę z cache.
        if url.endswith(current) or url == archives[-1]:
            return _chesscom_month(url, user)
        return list(_chesscom_finished_month(url, user))

    # Postęp raportujemy z głównego wątku (Streamlit nie pozwala rysować z wątków roboczych).
    with ThreadPoolExecutor(max_workers=CHESSCOM_WORKERS) as ex:
        futures = {ex.submit(load, url): i for i, url in enumerate(archives)}
        months = [None] * len(archives)
        for n, fut in enumerate(as_completed(futures), start=1):
            months[futures[fut]] = fut.result()
            if progress_cb:
                progress_cb(n, len(archives), f"Chess.com: archiwum {n}/{len(archives)}")
    rows = [r for m in months for r in m]
    return {"avatar": p_res.json().get("avatar", "")}, rows


def fetch_lichess(user, progress_cb=None):
    p_res = _get(f"https://lichess.org/api/user/{user}")
    if p_res.status_code == 404:
        raise PlayerNotFound(user)
    if p_res.status_code != 200:
        raise ApiError(f"Lichess zwrócił błąd {p_res.status_code}.")
    profile = p_res.json()
    perfs = profile.get("perfs", {})
    expected = sum(perfs.get(p, {}).get("games", 0) for p in ("bullet", "blitz", "rapid"))
    if profile.get("disabled") or profile.get("closed"):
        raise PlayerNotFound(user)
    # Tylko standardowe szachy w trybach, które aplikacja pokazuje: mniej danych = szybciej.
    url = (f"https://lichess.org/api/games/user/{user}"
           "?opening=true&clocks=true&perfType=bullet,blitz,rapid")
    res = _get(url, headers={"Accept": "application/x-ndjson"}, timeout=60, stream=True)
    if res.status_code != 200:
        raise ApiError(f"Lichess zwrócił błąd {res.status_code} (eksport partii).")
    k_id = f"{user} (L)"
    rows, seen = [], 0
    for line in res.iter_lines():
        if not line:
            continue
        seen += 1
        try:
            row = parse_lichess_game(json.loads(line), user, k_id)
        except (KeyError, ValueError, TypeError):
            continue
        if row:
            rows.append(row)
        if progress_cb and seen % 200 == 0:
            progress_cb(seen, max(expected, seen), f"Lichess: {seen} partii")
    return {"avatar": profile.get("profile", {}).get("avatar", "")}, rows


_player_cache = {}
_player_cache_lock = threading.Lock()


def fetch_player(user, platform, progress_cb=None, force=False):
    """Zwraca (profil, DataFrame z RAW_COLS posortowany od najstarszej partii).

    Wynik jest trzymany w pamięci przez PLAYER_CACHE_TTL; force=True pobiera od nowa
    (zakończone miesiące Chess.com i tak zostają w cache, bo się nie zmieniają).
    Rzuca PlayerNotFound albo ApiError.
    """
    user = user.strip()
    key = (platform, user.lower())
    now = time.time()
    with _player_cache_lock:
        hit = _player_cache.get(key)
    if hit and not force and now - hit[0] < PLAYER_CACHE_TTL:
        return hit[1], hit[2].copy()

    if platform == "Chess.com":
        profile, rows = fetch_chesscom(user, progress_cb)
    elif platform == "Lichess":
        profile, rows = fetch_lichess(user, progress_cb)
    else:
        raise ValueError(platform)
    df = pd.DataFrame(rows, columns=RAW_COLS).sort_values("EndTs", kind="stable").reset_index(drop=True)

    with _player_cache_lock:
        _player_cache[key] = (now, profile, df)
        if len(_player_cache) > PLAYER_CACHE_MAX:
            oldest = min(_player_cache, key=lambda k: _player_cache[k][0])
            _player_cache.pop(oldest, None)
    return profile, df.copy()
