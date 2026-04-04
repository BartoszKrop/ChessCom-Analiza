import streamlit as st 
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re
import json
import streamlit.components.v1 as components

# --- INICJALIZACJA STANU SESJI (USTAWIENIA) ---
if 'ui_lang' not in st.session_state: st.session_state.ui_lang = "Polski"
if 'op_lang' not in st.session_state: st.session_state.op_lang = "English"
if 'theme' not in st.session_state: st.session_state.theme = "Ciemny"
if 'cw_solo' not in st.session_state: st.session_state.cw_solo = True
if 'cb_solo' not in st.session_state: st.session_state.cb_solo = True
if 'cw_por' not in st.session_state: st.session_state.cw_por = True
if 'cb_por' not in st.session_state: st.session_state.cb_por = True

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="ChessStats", page_icon="♟️", layout="wide")

bg_dict = {
    "Jasny": "#ffffff", 
    "Ciemny": "#0e1117", 
    "Chess.com": "#312e2b", 
    "Neon Retro": "#090914"
}
bg_color = bg_dict.get(st.session_state.theme, "#0e1117")

components.html(
    f"""
    <script>
        const meta = window.parent.document.createElement('meta');
        meta.name = "theme-color";
        meta.content = "{bg_color}";
        window.parent.document.head.appendChild(meta);
    </script>
    """, height=0, width=0
)

# --- KOLORYSTYKA WYKRESÓW DLA MOTYWÓW ---
if st.session_state.theme == "Chess.com":
    cw, cd, cl = "#81b64c", "#a7a6a2", "#fa412d"  # Green, Grey, Red
    cp1, cp2 = "#81b64c", "#fa412d"               # Player 1, Player 2
    c_scale = "Greens"
elif st.session_state.theme == "Neon Retro":
    cw, cd, cl = "#00ffff", "#b829ea", "#ff007f"  # Cyan, Purple, Pink
    cp1, cp2 = "#00ffff", "#ff007f"               # Player 1, Player 2
    c_scale = "Purples"
elif st.session_state.theme == "Jasny":
    cw, cd, cl = "#1d4ed8", "#6b7280", "#dc2626"  # Blue, Grey, Red
    cp1, cp2 = "#1d4ed8", "#dc2626"               # Player 1, Player 2
    c_scale = "Blues"
else: # Ciemny
    cw, cd, cl = "#1e88e5", "#8b949e", "#ef553b"  # Blue, Grey, Orange-Red
    cp1, cp2 = "#1e88e5", "#ef553b"               # Player 1, Player 2
    c_scale = "Blues"

# --- TŁUMACZENIA UI ---
lang_map = {"Polski": "pl", "English": "en", "Deutsch": "de"}
ui_dict = {
    "title": {"pl": "ChessStats", "en": "ChessStats", "de": "ChessStats"},
    "btn_analize": {"pl": "Analizuj", "en": "Analyze", "de": "Analysieren"},
    "btn_connect": {"pl": "Połącz i Analizuj", "en": "Merge & Analyze", "de": "Zusammenführen & Analysieren"},
    "btn_refresh": {"pl": "Odśwież", "en": "Refresh", "de": "Aktualisieren"},
    "btn_change": {"pl": "Zmień gracza", "en": "Change player", "de": "Spieler wechseln"},
    "btn_rival": {"pl": "Pobierz dane rywala", "en": "Fetch rival data", "de": "Gegnerdaten abrufen"},
    "filters": {"pl": "🔍 Filtry", "en": "🔍 Filters", "de": "🔍 Filter"},
    "color_white": {"pl": "Białe", "en": "White", "de": "Weiß"},
    "color_black": {"pl": "Czarne", "en": "Black", "de": "Schwarz"},
    "fav_op": {"pl": "Ulubione debiuty", "en": "Favorite Openings", "de": "Lieblingseröffnungen"},
    "win_by_hour": {"pl": "Skuteczność wg godzin", "en": "Win Rate by hour", "de": "Erfolgsquote nach Stunden"},
    "win_by_length": {"pl": "Skuteczność wg długości partii", "en": "Win Rate by game length", "de": "Erfolgsquote nach Partielänge"},
    "win_by_day": {"pl": "Skuteczność wg dni", "en": "Win Rate by day", "de": "Erfolgsquote nach Tagen"},
    "win_reason": {"pl": "Sposób wygranej", "en": "Win reason", "de": "Gewinngrund"},
    "loss_reason": {"pl": "Sposób porażki", "en": "Loss reason", "de": "Verlustgrund"},
    "chart_desc": {"pl": "Wysokość słupka to Win Rate (%), a kolor oznacza ilość rozegranych partii. Najedź na słupek, aby zobaczyć szczegóły.", "en": "Bar height is Win Rate (%), and color indicates the number of games played. Hover over a bar for details.", "de": "Die Balkenhöhe ist die Erfolgsquote (%) und die Farbe gibt die Anzahl der gespielten Partien an. Fahren Sie über einen Balken für Details."},
    "chart_desc_comp": {"pl": "Wysokość słupka to Win Rate (%), a kolory oznaczają graczy.", "en": "Bar height is Win Rate (%), and colors represent players.", "de": "Die Balkenhöhe ist die Erfolgsquote (%) und die Farben stehen für die Spieler."},
    "streak_desc": {"pl": "Analizuje wyniki partii w zależności od passy w ramach jednej ciągłej sesji (przerwa między partiami < 2h).", "en": "Analyzes game results based on streaks within a single session (break < 2h).", "de": "Analysiert Partien basierend auf Serien innerhalb einer Sitzung (Pause < 2h)."},
    "games_count": {"pl": "Ilość partii", "en": "Games count", "de": "Anzahl Partien"},
    "win_rate": {"pl": "Skuteczność (%)", "en": "Win Rate (%)", "de": "Erfolgsquote (%)"},
    "hour": {"pl": "Godzina", "en": "Hour", "de": "Stunde"},
    "length": {"pl": "Długość (ruchy)", "en": "Length (moves)", "de": "Länge (Züge)"},
    "day": {"pl": "Dzień", "en": "Day", "de": "Tag"},
    "player": {"pl": "Gracz", "en": "Player", "de": "Spieler"}
}

reason_dict = {
    "resigned": {"pl": "Rezygnacja", "en": "Resignation", "de": "Aufgabe"},
    "timeout": {"pl": "Przekroczenie czasu", "en": "Timeout", "de": "Zeitüberschreitung"},
    "outoftime": {"pl": "Przekroczenie czasu", "en": "Timeout", "de": "Zeitüberschreitung"},
    "checkmated": {"pl": "Mat", "en": "Checkmate", "de": "Schachmatt"},
    "mate": {"pl": "Mat", "en": "Checkmate", "de": "Schachmatt"},
    "abandoned": {"pl": "Opuszczenie", "en": "Abandoned", "de": "Verlassen"},
    "agreed": {"pl": "Remis (zgoda)", "en": "Draw (Agreed)", "de": "Remis (Vereinbarung)"},
    "repetition": {"pl": "Powtórzenie", "en": "Repetition", "de": "Wiederholung"},
    "stalemate": {"pl": "Pat", "en": "Stalemate", "de": "Patt"},
    "insufficient": {"pl": "Niewyst. mat.", "en": "Insufficient", "de": "Ungenügend"},
    "50move": {"pl": "Zasada 50 r.", "en": "50-move rule", "de": "50-Züge"},
    "timevsinsufficient": {"pl": "Czas vs Niewyst.", "en": "Timeout vs Insuf.", "de": "Zeit vs Ungen."},
    "win": {"pl": "Wygrana", "en": "Win", "de": "Sieg"}
}

def t(key, default=""):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return ui_dict.get(key, {}).get(l, default if default else key)

def t_reason(reason):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return reason_dict.get(reason.lower(), {}).get(l, reason.capitalize())

# --- CSS (DYNAMICZNY MOTYW) ---
css_dark = """
    .stApp { background-color: #0e1117; color: #ffffff; }
    [data-testid="stHeader"] { background-color: #0e1117; }
    .stMetric, div.row-widget.stRadio > div, .asym-header { background-color: #161b22; border: 1px solid #30363d; }
    [data-testid="stMetricValue"], .asym-val-w { color: #ffffff !important; }
    .asym-label { color: #8b949e; } .asym-val-b { color: #58a6ff; }
    .custom-info-box { background-color: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; color: #e6edf3; }
    .custom-info-title { color: #58a6ff; }
"""
css_light = """
    .stApp { background-color: #ffffff; color: #000000; }
    [data-testid="stHeader"] { background-color: #ffffff; }
    .stMetric, div.row-widget.stRadio > div, .asym-header { background-color: #f3f4f6; border: 1px solid #d1d5db; }
    [data-testid="stMetricValue"], .asym-val-w, [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { color: #000000 !important; }
    [data-testid="stMetricLabel"] { color: #4b5563 !important; }
    .asym-label { color: #4b5563; } .asym-val-b { color: #1d4ed8; }
    .custom-info-box { background-color: #eff6ff; border-left: 4px solid #3b82f6; color: #1f2937; }
    .custom-info-title { color: #1d4ed8; }
    .stTabs [data-baseweb="tab-list"] button { color: #4b5563; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #000000; }
"""
css_chesscom = """
    .stApp { background-color: #312e2b; color: #ffffff; }
    [data-testid="stHeader"] { background-color: #312e2b; }
    .stMetric, div.row-widget.stRadio > div, .asym-header { background-color: #262421; border: 1px solid #403d39; }
    [data-testid="stMetricValue"], .asym-val-w, [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { color: #ffffff !important; }
    [data-testid="stMetricLabel"] { color: #c3c3c0 !important; }
    .asym-label { color: #c3c3c0; } .asym-val-b { color: #81b64c; }
    .custom-info-box { background-color: rgba(129, 182, 76, 0.15); border-left: 4px solid #81b64c; color: #e6edf3; }
    .custom-info-title { color: #81b64c; }
    .stTabs [data-baseweb="tab-list"] button { color: #c3c3c0; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #ffffff; border-bottom-color: #81b64c; }
"""
css_neon = """
    .stApp { background-color: #090914; color: #e0e0ff; }
    [data-testid="stHeader"] { background-color: #090914; }
    .stMetric, div.row-widget.stRadio > div, .asym-header { background-color: #13132b; border: 1px solid #b829ea; box-shadow: 0 0 5px rgba(184, 41, 234, 0.2); }
    [data-testid="stMetricValue"], .asym-val-w, [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { color: #00ffff !important; text-shadow: 0 0 2px rgba(0, 255, 255, 0.3); }
    [data-testid="stMetricLabel"] { color: #ff007f !important; }
    .asym-label { color: #e0e0ff; } .asym-val-b { color: #00ffff; }
    .custom-info-box { background-color: rgba(0, 255, 255, 0.08); border-left: 4px solid #00ffff; color: #e0e0ff; }
    .custom-info-title { color: #ff007f; }
    .stTabs [data-baseweb="tab-list"] button { color: #a0a0c0; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #00ffff; border-bottom-color: #00ffff; text-shadow: 0 0 5px rgba(0,255,255,0.4); }
"""

active_css = css_dark
if st.session_state.theme == "Jasny": active_css = css_light
elif st.session_state.theme == "Chess.com": active_css = css_chesscom
elif st.session_state.theme == "Neon Retro": active_css = css_neon

st.markdown(f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    [data-testid="stMetricValue"] {{ font-size: 0.9rem !important; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.75rem !important; }}
    .stMetric {{ padding: 8px; border-radius: 10px; }}
    .block-container {{ padding: 1rem; top: 1rem; }}
    div.row-widget.stRadio > div {{ flex-direction: row; justify-content: center; padding: 10px; border-radius: 10px; }}
    .asym-row {{ display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #30363d; text-align: center; }}
    .asym-val-w {{ width: 35%; font-size: 1.2rem; font-weight: bold; }}
    .asym-label {{ width: 30%; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }}
    .asym-val-b {{ width: 35%; font-size: 1.2rem; font-weight: bold; }}
    .asym-header {{ display: flex; justify-content: space-between; padding: 8px; border-radius: 8px; font-weight: bold; margin-bottom: 5px; font-size: 0.8rem;}}
    .custom-info-box {{ padding: 12px; border-radius: 8px; margin-bottom: 16px; }}
    .custom-info-title {{ font-weight: bold; margin-bottom: 6px; }}
    
    /* Ukrywanie obramowania i tła zębatki ustawień */
    [data-testid="stPopover"] > button {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        color: inherit !important;
    }}
    [data-testid="stPopover"] > button:hover {{
        color: #58a6ff !important;
    }}
    
    {active_css}
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE (DEBIUTY) ---
op_translations = {
    "Sicilian Defense": {"pl": "Obrona Sycylijska", "de": "Sizilianische Verteidigung"},
    "French Defense": {"pl": "Obrona Francuska", "de": "Französische Verteidigung"},
    "Caro-Kann Defense": {"pl": "Obrona Caro-Kann", "de": "Caro-Kann-Verteidigung"},
    "Ruy Lopez": {"pl": "Partia Hiszpańska", "de": "Spanische Partie"},
    "Italian Game": {"pl": "Partia Włoska", "de": "Italienische Partie"},
    "Scotch Game": {"pl": "Partia Szkocka", "de": "Schottische Partie"},
    "Vienna Game": {"pl": "Partia Wiedeńska", "de": "Wiener Partie"},
    "Four Knights Game": {"pl": "Partia 4 Skoczków", "de": "Vierspringerspiel"},
    "Two Knights Defense": {"pl": "Obrona 2 Skoczków", "de": "Zweispringerspiel"},
    "Petrov's Defense": {"pl": "Obrona Petrowa", "de": "Russische Partie"},
    "Philidor Defense": {"pl": "Obrona Philidora", "de": "Philidor-Verteidigung"},
    "Bishop's Opening": {"pl": "Otwarcie Gońca", "de": "Läuferspiel"},
    "Scandinavian Defense": {"pl": "Obrona Skandynawska", "de": "Skandinavische Vert."},
    "Alekhine's Defense": {"pl": "Obrona Alechina", "de": "Aljechin-Verteidigung"},
    "Pirc Defense": {"pl": "Obrona Pirca", "de": "Pirc-Ufimzew-Vert."},
    "Modern Defense": {"pl": "Obrona Nowoczesna", "de": "Moderne Verteidigung"},
    "Queen's Gambit": {"pl": "Gambit Hetmański", "de": "Damengambit"},
    "King's Gambit": {"pl": "Gambit Królewski", "de": "Königsgambit"},
    "King's Indian Defense": {"pl": "Obrona K-I", "de": "Königsindisch"},
    "Queen's Indian Defense": {"pl": "Obrona H-I", "de": "Damenindisch"},
    "Nimzo-Indian Defense": {"pl": "Obrona Nimzowitscha", "de": "Nimzo-Indisch"},
    "Bogo-Indian Defense": {"pl": "Obrona Bogo-I", "de": "Bogo-Indisch"},
    "Grünfeld Defense": {"pl": "Obrona Grünfelda", "de": "Grünfeld-Indisch"},
    "Slav Defense": {"pl": "Obrona Słowiańska", "de": "Slawische Verteidigung"},
    "Catalan Opening": {"pl": "Otwarcie Katalońskie", "de": "Katalanische Eröffnung"},
    "London System": {"pl": "System Londyński", "de": "Londoner System"},
    "Trompowsky Attack": {"pl": "Atak Trompowskiego", "de": "Trompowsky-Eröffnung"},
    "Benoni Defense": {"pl": "Obrona Benoni", "de": "Benoni-Verteidigung"},
    "Benko Gambit": {"pl": "Gambit Wołżański", "de": "Wolga-Gambit"},
    "Dutch Defense": {"pl": "Obrona Holenderska", "de": "Holländische Vert."},
    "English Opening": {"pl": "Partia Angielska", "de": "Englische Eröffnung"},
    "Réti Opening": {"pl": "Otwarcie Rétiego", "de": "Réti-Eröffnung"},
    "Bird's Opening": {"pl": "Otwarcie Birda", "de": "Bird-Eröffnung"},
    "King's Pawn Opening": {"pl": "Pion Królewski", "de": "Königsbauernspiel"},
    "Queen's Pawn Opening": {"pl": "Pion Hetmański", "de": "Damenbauernspiel"},
}

def t_op(eng_name):
    if eng_name == "Brak" or not eng_name: return "Brak"
    l = lang_map.get(st.session_state.op_lang, "pl")
    if l == "en": return eng_name
    return op_translations.get(eng_name, {}).get(l, eng_name)

def get_opening_group(opening_name):
    name = opening_name.lower()
    if "sicilian" in name: return "Sicilian Defense"
    if "french" in name: return "French Defense"
    if "caro-kann" in name or "caro kann" in name: return "Caro-Kann Defense"
    if "ruy lopez" in name or "spanish" in name: return "Ruy Lopez"
    if "italian" in name or "giuoco piano" in name: return "Italian Game"
    if "scotch" in name: return "Scotch Game"
    if "vienna" in name: return "Vienna Game"
    if "four knights" in name: return "Four Knights Game"
    if "two knights" in name: return "Two Knights Defense"
    if "petrov" in name or "russian" in name: return "Petrov's Defense"
    if "philidor" in name: return "Philidor Defense"
    if "bishop's opening" in name or "bishops opening" in name: return "Bishop's Opening"
    if "scandinavian" in name: return "Scandinavian Defense"
    if "alekhine" in name: return "Alekhine's Defense"
    if "pirc" in name: return "Pirc Defense"
    if "modern defense" in name: return "Modern Defense" 
    if "queens gambit" in name or "queen's gambit" in name: return "Queen's Gambit"
    if "kings gambit" in name or "king's gambit" in name: return "King's Gambit"
    if "kings indian" in name or "king's indian" in name: return "King's Indian Defense"
    if "queens indian" in name or "queen's indian" in name: return "Queen's Indian Defense"
    if "nimzo" in name: return "Nimzo-Indian Defense"
    if "bogo-indian" in name or "bogo indian" in name: return "Bogo-Indian Defense"
    if "grunfeld" in name or "grünfeld" in name or "gruenfeld" in name: return "Grünfeld Defense"
    if "slav" in name: return "Slav Defense"
    if "catalan" in name: return "Catalan Opening"
    if "london" in name: return "London System"
    if "trompowsky" in name: return "Trompowsky Attack"
    if "benoni" in name: return "Benoni Defense"
    if "benko" in name or "volga" in name: return "Benko Gambit"
    if "dutch" in name: return "Dutch Defense"
    if "english" in name: return "English Opening"
    if "reti" in name or "réti" in name: return "Réti Opening"
    if "bird" in name: return "Bird's Opening"
    if "king's pawn" in name or "kings pawn" in name: return "King's Pawn Opening"
    if "queen's pawn" in name or "queens pawn" in name: return "Queen's Pawn Opening"
    fallback = opening_name.split(':')[0].strip()
    for keyword in [" Defense", " Opening", " Game", " Gambit", " System", " Attack"]:
        idx = fallback.lower().find(keyword.lower())
        if idx != -1: return fallback[:idx + len(keyword)].title()
    return fallback.title()

def extract_opening(pgn):
    if not pgn: return "Nieznany"
    match = re.search(r'openings/(.*?)"', pgn)
    return match.group(1).replace('-', ' ').title() if match else "Inny"

def extract_moves_count(pgn):
    if not pgn: return 0
    matches = re.findall(r'(\d+)\.', pgn)
    return int(matches[-1]) if matches else 0

def get_duration_bin(moves):
    bins = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
    if moves <= 20: return bins[0]
    elif moves <= 30: return bins[1]
    elif moves <= 40: return bins[2]
    elif moves <= 50: return bins[3]
    elif moves <= 60: return bins[4]
    elif moves <= 70: return bins[5]
    else: return bins[6]

def import_to_lichess(pgn_text):
    try:
        res = requests.post("https://lichess.org/api/import", data={'pgn': pgn_text}, headers={"Accept": "application/json"}, timeout=10)
        return res.json().get("url") if res.status_code == 200 else None
    except: return None

def calc_elo(df, mode):
    mdf = df[df["Tryb"] == mode]
    if mdf.empty: return "-", "-", None
    best_peak, best_curr = -1, -1
    p_plat, c_plat = "", ""
    for plat in mdf["Platforma"].unique():
        pdf = mdf[mdf["Platforma"] == plat]
        peak = int(pdf["ELO"].max())
        curr = int(pdf.sort_values("Timestamp").iloc[-1]["ELO"])
        if peak > best_peak: best_peak, p_plat = peak, plat
        if curr > best_curr: best_curr, c_plat = curr, plat
    is_m = len(df["Platforma"].unique()) > 1
    p_s = (" (C)" if p_plat == "Chess.com" else " (L)") if is_m else ""
    c_s = (" (C)" if c_plat == "Chess.com" else " (L)") if is_m else ""
    return f"{best_peak}{p_s}", f"{best_curr}{c_s}", best_curr

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user, platform="Chess.com"):
    try:
        headers = {"User-Agent": f"AnalizySzachowe-V30-{user}"}
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        all_games = []
        k_id = f"{user} ({'C' if platform == 'Chess.com' else 'L'})"
        if platform == "Chess.com":
            p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
            a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
            if p_res.status_code != 200: return None, None
            for url in a_res.json().get("archives", []):
                try:
                    m_res = requests.get(url, headers=headers, timeout=10)
                    if m_res.status_code == 200:
                        for g in m_res.json().get("games", []):
                            if "end_time" in g:
                                ts = datetime.fromtimestamp(g["end_time"])
                                is_w = g["white"]["username"].lower() == user.lower()
                                my_r, opp_r = g["white" if is_w else "black"]["result"], g["black" if is_w else "white"]["result"]
                                out = "Wygrane" if my_r == "win" else ("Remisy" if my_r in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                                pgn = g.get("pgn", "")
                                deb = extract_opening(pgn)
                                all_games.append({
                                    "Konto": k_id, "Platforma": platform, "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                                    "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"), "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                                    "ELO": g["white" if is_w else "black"].get("rating", 0), "Elo_Rywala": g["black" if is_w else "white"].get("rating", 0),
                                    "Ruchy": extract_moves_count(pgn), "Debiut": deb, "Debiut_Grupa": get_opening_group(deb), "Przeciwnik": g["black" if is_w else "white"]["username"],
                                    "Kolor": "Białe" if is_w else "Czarne", "Powod": my_r if out=="Przegrane" else opp_r, "PGN_Raw": pgn, "Link": ""
                                })
                except: continue 
            return {"avatar": p_res.json().get("avatar", "")}, pd.DataFrame(all_games)
        elif platform == "Lichess":
            p_res = requests.get(f"https://lichess.org/api/user/{user}", headers=headers)
            if p_res.status_code != 200: return None, None
            g_res = requests.get(f"https://lichess.org/api/games/user/{user}?opening=true", headers={"Accept": "application/x-ndjson"})
            for line in g_res.text.strip().split('\n'):
                if not line: continue
                try:
                    g = json.loads(line)
                    ts = datetime.fromtimestamp(g["createdAt"] / 1000.0)
                    my_col = "white" if g["players"]["white"].get("user", {}).get("name", "").lower() == user.lower() else "black"
                    opp_col = "black" if my_col == "white" else "white"
                    out = "Wygrane" if g.get("winner") == my_col else ("Przegrane" if g.get("winner") == opp_col else "Remisy")
                    m_l = g.get("moves", "").split()
                    deb = g.get("opening", {}).get("name", "Nieznany").split(':')[0]
                    all_games.append({
                        "Konto": k_id, "Platforma": platform, "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"), "Tryb": g.get("speed", "Inne").capitalize(), "Wynik": out, 
                        "ELO": g["players"][my_col].get("rating", 0), "Elo_Rywala": g["players"][opp_col].get("rating", 0),
                        "Ruchy": len(m_l)//2 + len(m_l)%2, "Debiut": deb, "Debiut_Grupa": get_opening_group(deb),
                        "Przeciwnik": g["players"][opp_col].get("user", {}).get("name", "Anonim"), "Kolor": "Białe" if my_col == "white" else "Czarne",
                        "Powod": g.get("status"), "PGN_Raw": g.get("moves", ""), "Link": f"https://lichess.org/{g['id']}"
                    })
                except: continue
            return {"avatar": p_res.json().get("profile", {}).get("avatar", "")}, pd.DataFrame(all_games)
    except: return None, None

# --- SESSION & START ---
for k in ['data','data2','url']: 
    if k not in st.session_state: st.session_state[k] = None
for k in ['user','user2','plat2']: 
    if k not in st.session_state: st.session_state[k] = ""
if 'platforms' not in st.session_state: st.session_state.platforms = []

if st.session_state.data is None:
    # EKRAN LOGOWANIA
    c_l1, c_l2 = st.columns([7, 3])
    c_l1.title(f"♟️ {t('title')}")
    with c_l2.expander("⚙️ Ustawienia"):
        st.selectbox("🌍 Język UI", ["Polski", "English", "Deutsch"], key="ui_lang")
        st.selectbox("♟️ Język Debiutów", ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio("🎨 Motyw", ["Ciemny", "Jasny", "Chess.com", "Neon Retro"], key="theme", horizontal=True)

    log_m = st.radio("Zasięg:", ["Jeden profil", "Połącz profile (C+L)"], horizontal=True)
    if log_m == "Jeden profil":
        c1, c2 = st.columns([1, 4])
        plat = c1.selectbox("Plat:", ["Chess.com", "Lichess"])
        nick = c2.text_input("Nick:")
        if st.button(t("btn_analize"), use_container_width=True):
            if nick:
                with st.spinner("Pobieranie..."):
                    f = fetch_data(nick, plat)
                    if f[1] is not None: st.session_state.data, st.session_state.user, st.session_state.platforms = f, nick, [plat]; st.rerun()
    else:
        c1, c2 = st.columns(2)
        p1, n1 = c1.selectbox("P1:", ["Chess.com", "Lichess"]), c1.text_input("Nick 1:")
        p2, n2 = c2.selectbox("P2:", ["Lichess", "Chess.com"]), c2.text_input("Nick 2:")
        if st.button(t("btn_connect"), use_container_width=True):
            if n1 and n2:
                with st.spinner("Łączenie..."):
                    f1, f2 = fetch_data(n1, p1), fetch_data(n2, p2)
                    if f1[1] is not None and f2[1] is not None:
                        st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                        st.session_state.user, st.session_state.platforms = f"{n1}+{n2}", list(set([p1, p2]))
                        st.rerun()
else:
    profile, df = st.session_state.data
    username, user_plats = st.session_state.user, st.session_state.platforms
    
    df_loc = df.copy()
    df_loc["Debiut_Grupa"] = df_loc["Debiut_Grupa"].apply(t_op)
    
    # EKRAN GŁÓWNY APLIKACJI - Flexbox dla avatara i nicku
    if profile.get("avatar"):
        st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                <img src="{profile.get("avatar")}" width="60" style="border-radius: 10px; border: 1px solid {cw};">
                <h2 style="margin: 0; padding: 0;">{username}</h2>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<h2 style='margin-bottom: 15px;'>{username}</h2>", unsafe_allow_html=True)
    
    with st.expander("⚙️ Ustawienia"):
        app_m = st.radio("Widok:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], label_visibility="collapsed", horizontal=True)
        c_l_ui, c_l_op = st.columns(2)
        c_l_ui.selectbox("🌍 Język UI", ["Polski", "English", "Deutsch"], key="ui_lang")
        c_l_op.selectbox("♟️ Język Debiutów", ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio("🎨 Motyw", ["Ciemny", "Jasny", "Chess.com", "Neon Retro"], key="theme", horizontal=True)
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button(t("btn_refresh"), use_container_width=True):
                fetch_data.clear() 
                with st.spinner("Odświeżanie danych..."):
                    nowe_dane = []
                    nowy_profil = profile
                    for konto in df["Konto"].unique():
                        u_nick = konto[:-4]
                        u_plat = "Chess.com" if konto[-2] == 'C' else "Lichess"
                        f_res = fetch_data(u_nick, u_plat)
                        if f_res[1] is not None:
                            nowe_dane.append(f_res[1])
                            nowy_profil = f_res[0]
                    if nowe_dane:
                        st.session_state.data = (nowy_profil, pd.concat(nowe_dane, ignore_index=True))
                st.rerun()
                
        with c_btn2:
            if st.button(t("btn_change"), use_container_width=True):
                for k in ['data','data2','url','user','user2','plat2']: st.session_state[k] = None if k in ['data','data2','url'] else ""
                st.session_state.platforms = []; st.rerun()
    
    st.divider()

    if app_m == "👤 Moja Analiza":
        m1, m2, m3 = st.columns(3)
        p_r, c_r, _ = calc_elo(df_loc, "Rapid"); p_b, c_b, _ = calc_elo(df_loc, "Blitz"); p_bl, c_bl, _ = calc_elo(df_loc, "Bullet")
        m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
        m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
        m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")

        with st.expander(t("filters")):
            f1, f2 = st.columns(2)
            d_r = f1.date_input("Zakres:", value=(df_loc["Data"].min(), df_loc["Data"].max()))
            s_m = f2.selectbox("Tryb:", ["Wszystkie"] + sorted(df_loc["Tryb"].unique().tolist()))
            
            st.write(f"<span style='font-size:0.9rem; font-weight:bold;'>Kolor</span>", unsafe_allow_html=True)
            c_w_btn, c_b_btn, _ = st.columns([1, 1, 4])
            if c_w_btn.button("⚪ " + t("color_white"), type="primary" if st.session_state.cw_solo else "secondary", use_container_width=True, key="sw_solo"):
                st.session_state.cw_solo = not st.session_state.cw_solo; st.rerun()
            if c_b_btn.button("⚫ " + t("color_black"), type="primary" if st.session_state.cb_solo else "secondary", use_container_width=True, key="sb_solo"):
                st.session_state.cb_solo = not st.session_state.cb_solo; st.rerun()
            
            s_c = []
            if st.session_state.cw_solo: s_c.append("Białe")
            if st.session_state.cb_solo: s_c.append("Czarne")
            
            s_h = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df_loc.copy()
        if isinstance(d_r, (list, tuple)) and len(d_r) == 2:
            df_f = df_f[(df_f["Data"] >= d_r[0]) & (df_f["Data"] <= d_r[1])]
        df_f = df_f[df_f["Kolor"].isin(s_c) & (df_f["Godzina"] >= s_h[0]) & (df_f["Godzina"] <= s_h[1])]
        if s_m != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_m]

        if not df_f.empty:
            t_stat, t_hist, t_czas, t_deb, t_ana = st.tabs(["📊 Stat", "📅 Hist", "⏳ Czas", "🔬 Debiuty", "🧠 Analiza"])
            
            with t_stat:
                w, d, l = (df_f["Wynik"]=="Wygrane").sum(), (df_f["Wynik"]=="Remisy").sum(), (df_f["Wynik"]=="Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                
                fav_w = df_f[df_f["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Białe"].empty else "Brak"
                fav_b = df_f[df_f["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Czarne"].empty else "Brak"
                
                st.markdown(f"""
                <div class="custom-info-box">
                    <div class="custom-info-title">{t('fav_op')}:</div>
                    <div style="font-size: 0.85rem;">⚪ <b>{fav_w}</b> &emsp;|&emsp; ⚫ <b>{fav_b}</b></div>
                </div>
                """, unsafe_allow_html=True)
                
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.plotly_chart(px.line(mdf, x="Timestamp", y="ELO", color="Konto", title=f"Ranking {m}", markers=True).update_layout(xaxis_title="", yaxis_title="ELO", height=300, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None)), use_container_width=True)

                st.divider()
                c1, c2 = st.columns(2)
                df_f_pie = df_f.copy()
                df_f_pie["Powod_T"] = df_f_pie["Powod"].apply(t_reason)
                c1.plotly_chart(px.pie(df_f_pie[df_f_pie["Wynik"]=="Wygrane"], names="Powod_T", hole=0.4, title=t("win_reason"), color_discrete_sequence=[cw, "#5ab4ac", "#d8b365", "#01665e"]), use_container_width=True)
                c2.plotly_chart(px.pie(df_f_pie[df_f_pie["Wynik"]=="Przegrane"], names="Powod_T", hole=0.4, title=t("loss_reason"), color_discrete_sequence=[cl, "#c51b7d", "#e9a3c9", "#4d9221"]), use_container_width=True)

            with t_hist:
                st.write("### Aktywność i wyniki dzienne")
                act_df = df_f.groupby(["Data", "Wynik"]).size().reset_index(name="Partie")
                fig_act = px.bar(act_df, x="Data", y="Partie", color="Wynik", title="Ilość gier w czasie", color_discrete_map={"Wygrane":cw, "Remisy":cd, "Przegrane":cl})
                fig_act.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None), barmode='stack')
                st.plotly_chart(fig_act, use_container_width=True)
                
                mon = df_f.groupby("Miesiąc").agg(G=('Wynik','count'), W=('Wynik',lambda x:(x=='Wygrane').sum()), R=('Wynik',lambda x:(x=='Remisy').sum()), L=('Wynik',lambda x:(x=='Przegrane').sum())).reset_index().sort_values("Miesiąc", ascending=False)
                mon["Win%"] = (mon["W"]/mon["G"]*100).round(0).astype(int)
                st.dataframe(mon.rename(columns={"G":"Gry"}), use_container_width=True, hide_index=True)

            with t_czas:
                h_st = df_f.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                h_st["Win%"] = (h_st["W"] / h_st["G"] * 100).round(0).astype(int)
                
                st.subheader(t("win_by_hour"), help=t("chart_desc"))
                fig_h = px.bar(h_st, x="Godzina", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Godzina": t("hour"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_h.update_layout(coloraxis_showscale=False, title="", xaxis=dict(tickmode='linear', tick0=0, dtick=1, tickangle=0))
                fig_h.update_yaxes(range=[0, 100])
                st.plotly_chart(fig_h, use_container_width=True)
                
                st.write("") 
                
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["G"] * 100).round(0).astype(int)
                
                st.subheader(t("win_by_day"), help=t("chart_desc"))
                fig_d = px.bar(d_st, x="Dzień", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Dzień": t("day"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_d.update_layout(coloraxis_showscale=False, title="", xaxis=dict(tickangle=0))
                fig_d.update_yaxes(range=[0, 100])
                st.plotly_chart(fig_d, use_container_width=True)
                
                st.write("")
                
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["G"] * 100).round(0).astype(int)
                order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
                
                st.subheader(t("win_by_length"), help=t("chart_desc"))
                fig_dur = px.bar(dst.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), x="Bin", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Bin": t("length"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_dur.update_layout(coloraxis_showscale=False, showlegend=False, xaxis_title="", title="")
                fig_dur.update_yaxes(range=[0, 100])
                st.plotly_chart(fig_dur, use_container_width=True)
                
                st.write("")
                
                st.subheader("Wpływ serii", help=t("streak_desc"))
                df_t = df_f.sort_values('Timestamp').copy()
                st_l, sc_l, l_ts, ct, cc = [], [], None, None, 0
                for _, r in df_t.iterrows():
                    if l_ts and (r['Timestamp'] - l_ts).total_seconds() > 7200: ct, cc = None, 0
                    st_l.append(ct); sc_l.append(cc)
                    if r['Wynik'] == 'Wygrane':
                        if ct == 'W': cc += 1
                        else: ct, cc = 'W', 1
                    elif r['Wynik'] == 'Przegrane':
                        if ct == 'L': cc += 1
                        else: ct, cc = 'L', 1
                    else: ct, cc = None, 0
                    l_ts = r['Timestamp']
                df_t['ST'], df_t['SC'] = st_l, sc_l 
                t_res = []
                for s, n in [('W', 'Po serii Wygranych'), ('L', 'Po serii Porażek')]:
                    for c in [1, 2, 3, 4]:
                        sub = df_t[(df_t['ST'] == s) & (df_t['SC'] == c)]
                        if not sub.empty: t_res.append({"Typ": n, "Seria": f"{c} z rzędu", "Win%": int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0)), "Partie": len(sub)})
                    sub5 = df_t[(df_t['ST'] == s) & (df_t['SC'] >= 5)] 
                    if not sub5.empty: t_res.append({"Typ": n, "Seria": "5+ z rzędu", "Win%": int(round((sub5['Wynik']=='Wygrane').sum()/len(sub5)*100,0)), "Partie": len(sub5)})
                if t_res: st.plotly_chart(px.bar(pd.DataFrame(t_res), x="Seria", y="Win%", color="Typ", barmode='group', text="Win%", hover_data=["Partie"], color_discrete_map={"Po serii Wygranych":cw, "Po serii Porażek":cl}).update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None)), use_container_width=True)

            with t_deb:
                c_w1, c_b1 = st.columns(2)
                df_w = df_f[df_f["Kolor"] == "Białe"]
                df_b = df_f[df_f["Kolor"] == "Czarne"]
                
                with c_w1:
                    st.markdown(f"<h5 style='text-align: center;'>⚪ {t('color_white')}</h5>", unsafe_allow_html=True)
                    if not df_w.empty:
                        op_g_w = df_w.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_w.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                        with st.expander(f"Szczegółowe Warianty - ⚪ {t('color_white')}"):
                            op_w = df_w.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            st.dataframe(op_w.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii")
                        
                with c_b1:
                    st.markdown(f"<h5 style='text-align: center;'>⚫ {t('color_black')}</h5>", unsafe_allow_html=True)
                    if not df_b.empty:
                        op_g_b = df_b.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_b.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                        with st.expander(f"Szczegółowe Warianty - ⚫ {t('color_black')}"):
                            op_b = df_b.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            st.dataframe(op_b.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii")

            with t_ana:
                fa1, fa2, fa3 = st.columns([1,1,1])
                d_val = fa1.date_input("Dzień:", value=df_f["Data"].max())
                opp_search = fa2.text_input("Nick rywala (opcjonalnie):")
                deb_search = fa3.selectbox("Grupa debiutu:", ["Wszystkie"] + sorted(df_f["Debiut_Grupa"].unique().tolist()))
                
                ana = df_f.copy()
                if opp_search or deb_search != "Wszystkie":
                    if opp_search: ana = ana[ana["Przeciwnik"].str.lower().str.contains(opp_search.lower())]
                    if deb_search != "Wszystkie": ana = ana[ana["Debiut_Grupa"] == deb_search]
                else:
                    ana = ana[ana["Data"] == d_val]
                    
                if not ana.empty:
                    def get_res(r):
                        if r == "Wygrane": return "W"
                        if r == "Przegrane": return "L"
                        return "D"
                    
                    ana["label"] = ana.apply(lambda x: f"{x['Data']} {x['Timestamp'].strftime('%H:%M')} | {x['Tryb']} vs {x['Przeciwnik']} ({'C' if x['Platforma'] == 'Chess.com' else 'L'}) ({get_res(x['Wynik'])})", axis=1)
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False)["label"])
                    g_sel = ana[ana["label"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        st.session_state.url = g_sel["Link"] if g_sel["Platforma"]=="Lichess" else import_to_lichess(g_sel["PGN_Raw"]); st.rerun()
                    if st.session_state.url: st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:{cw}; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:10px;">ANALIZA ➡️</a>', unsafe_allow_html=True)
                else:
                    st.info("Brak partii do analizy dla podanych kryteriów.")

    elif app_m == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        p2 = c2.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        n2 = c2.text_input("Nick rywala:")
        
        if st.button(t("btn_rival"), use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie danych dla {n2}..."):
                    f2 = fetch_data(n2, p2)
                    if f2[1] is not None: 
                        st.session_state.data2, st.session_state.user2, st.session_state.plat2 = f2[1], n2, p2
                        st.rerun()
                    else:
                        st.error("Nie udało się pobrać danych rywala.")

        if st.session_state.data2 is not None:
            df2 = st.session_state.data2.copy()
            df2["Debiut_Grupa"] = df2["Debiut_Grupa"].apply(t_op)
            
            u1, u2, p2_p = username, st.session_state.user2, st.session_state.plat2
            
            with st.expander(t("filters"), expanded=False):
                fx1, fx2 = st.columns(2)
                min_date = min(df_loc["Data"].min(), df2["Data"].min())
                max_date = max(df_loc["Data"].max(), df2["Data"].max())
                
                dr_c = fx1.date_input("Zakres dat:", value=(min_date, max_date), key="c_dr")
                wspolne_tryby = list(set(df_loc["Tryb"].unique()) | set(df2["Tryb"].unique()))
                sm_c = fx2.selectbox("Tryb:", ["Wszystkie"] + sorted(wspolne_tryby), key="c_sm")
                
                st.write(f"<span style='font-size:0.9rem; font-weight:bold;'>Kolor</span>", unsafe_allow_html=True)
                c_w_por, c_b_por, _ = st.columns([1, 1, 4])
                if c_w_por.button("⚪ " + t("color_white"), type="primary" if st.session_state.cw_por else "secondary", use_container_width=True, key="por_w"):
                    st.session_state.cw_por = not st.session_state.cw_por; st.rerun()
                if c_b_por.button("⚫ " + t("color_black"), type="primary" if st.session_state.cb_por else "secondary", use_container_width=True, key="por_b"):
                    st.session_state.cb_por = not st.session_state.cb_por; st.rerun()
                
                sc_c = []
                if st.session_state.cw_por: sc_c.append("Białe")
                if st.session_state.cb_por: sc_c.append("Czarne")
                
                sh_c = st.slider("Godziny:", 0, 23, (0, 23), key="c_sh")

            df1_c, df2_c = df_loc.copy(), df2.copy()
            
            if isinstance(dr_c, (list, tuple)) and len(dr_c) == 2:
                df1_c = df1_c[(df1_c["Data"] >= dr_c[0]) & (df1_c["Data"] <= dr_c[1])]
                df2_c = df2_c[(df2_c["Data"] >= dr_c[0]) & (df2_c["Data"] <= dr_c[1])]
                
            df1_c = df1_c[df1_c["Kolor"].isin(sc_c) & (df1_c["Godzina"] >= sh_c[0]) & (df1_c["Godzina"] <= sh_c[1])]
            df2_c = df2_c[df2_c["Kolor"].isin(sc_c) & (df2_c["Godzina"] >= sh_c[0]) & (df2_c["Godzina"] <= sh_c[1])]
            
            if sm_c != "Wszystkie":
                df1_c = df1_c[df1_c["Tryb"] == sm_c]
                df2_c = df2_c[df2_c["Tryb"] == sm_c]

            tabs_names = ["📊 Ogólne Statystyki", "📅 Historia", "⏳ Czas", "🔬 Debiuty"]
            if p2_p in user_plats:
                tabs_names.append("🥊 H2H")
            tabs = st.tabs(tabs_names)

            with tabs[0]:
                st.markdown(f"### 🏆 Podsumowanie: {u1} vs {u2}")
                
                g1, g2 = len(df1_c), len(df2_c)
                w1 = int(round((df1_c["Wynik"]=="Wygrane").sum()/g1*100,0)) if g1 > 0 else 0
                w2 = int(round((df2_c["Wynik"]=="Wygrane").sum()/g2*100,0)) if g2 > 0 else 0
                d1 = int(round((df1_c["Wynik"]=="Remisy").sum()/g1*100,0)) if g1 > 0 else 0
                d2 = int(round((df2_c["Wynik"]=="Remisy").sum()/g2*100,0)) if g2 > 0 else 0
                m1 = int(df1_c["Ruchy"].mean()) if g1 > 0 else 0
                m2 = int(df2_c["Ruchy"].mean()) if g2 > 0 else 0
                
                fav_op1_w = df1_c[df1_c["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df1_c[df1_c["Kolor"] == "Białe"].empty else "Brak"
                fav_op1_b = df1_c[df1_c["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df1_c[df1_c["Kolor"] == "Czarne"].empty else "Brak"
                
                fav_op2_w = df2_c[df2_c["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df2_c[df2_c["Kolor"] == "Białe"].empty else "Brak"
                fav_op2_b = df2_c[df2_c["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df2_c[df2_c["Kolor"] == "Czarne"].empty else "Brak"

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Partie", f"{g1} / {g2}", g1 - g2)
                k2.metric("Win Rate (%)", f"{w1}% / {w2}%", w1 - w2)
                k3.metric("Draw Rate (%)", f"{d1}% / {d2}%", d1 - d2)
                k4.metric("Śr. ruchów", f"{m1} / {m2}", m1 - m2)

                st.divider()
                st.markdown("**Aktualny Ranking:**")
                cx1, cx2, cx3 = st.columns(3)
                df1_p = df1_c[df1_c["Platforma"] == p2_p] if not df1_c[df1_c["Platforma"] == p2_p].empty else df1_c
                _, r1_s, r1_i = calc_elo(df1_p, "Rapid"); _, r2_s, r2_i = calc_elo(df2_c, "Rapid")
                cx1.metric(f"Rapid", f"{r1_s} / {r2_s}", r1_i - r2_i if r1_i and r2_i else None)
                
                _, b1_s, b1_i = calc_elo(df1_p, "Blitz"); _, b2_s, b2_i = calc_elo(df2_c, "Blitz")
                cx2.metric(f"Blitz", f"{b1_s} / {b2_s}", b1_i - b2_i if b1_i and b2_i else None)
                
                _, l1_s, l1_i = calc_elo(df1_p, "Bullet"); _, l2_s, l2_i = calc_elo(df2_c, "Bullet")
                cx3.metric(f"Bullet", f"{l1_s} / {l2_s}", l1_i - l2_i if l1_i and l2_i else None)
                
                st.divider()
                o1, o2 = st.columns(2)
                
                o1.markdown(f"""
                <div class="custom-info-box">
                    <div class="custom-info-title">{t('fav_op')} ({u1}):</div>
                    <div style="font-size: 0.85rem;">⚪ <b>{fav_op1_w}</b><br>⚫ <b>{fav_op1_b}</b></div>
                </div>
                """, unsafe_allow_html=True)
                
                o2.markdown(f"""
                <div class="custom-info-box">
                    <div class="custom-info-title">{t('fav_op')} ({u2}):</div>
                    <div style="font-size: 0.85rem;">⚪ <b>{fav_op2_w}</b><br>⚫ <b>{fav_op2_b}</b></div>
                </div>
                """, unsafe_allow_html=True)

                st.divider()
                st.write("### Sposób zakończenia partii")
                df1_r = df1_c.copy()
                df2_r = df2_c.copy()
                df1_r["Gracz"] = u1
                df2_r["Gracz"] = u2
                df_r_comb = pd.concat([df1_r, df2_r])
                df_r_comb["Powod_T"] = df_r_comb["Powod"].apply(t_reason)
                
                c_r1, c_r2 = st.columns(2)
                if not df_r_comb.empty:
                    df_win = df_r_comb[df_r_comb["Wynik"] == "Wygrane"].groupby(["Powod_T", "Gracz"]).size().reset_index(name="Ilość")
                    if not df_win.empty:
                        fig_r_w = px.bar(df_win, x="Powod_T", y="Ilość", color="Gracz", barmode="group", title="Sposób wygranej", color_discrete_sequence=[cp1, cp2])
                        fig_r_w.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                        c_r1.plotly_chart(fig_r_w, use_container_width=True)

                    df_loss = df_r_comb[df_r_comb["Wynik"] == "Przegrane"].groupby(["Powod_T", "Gracz"]).size().reset_index(name="Ilość")
                    if not df_loss.empty:
                        fig_r_l = px.bar(df_loss, x="Powod_T", y="Ilość", color="Gracz", barmode="group", title="Sposób porażki", color_discrete_sequence=[cp1, cp2])
                        fig_r_l.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                        c_r2.plotly_chart(fig_r_l, use_container_width=True)

            with tabs[1]:
                if not df1_c.empty and not df2_c.empty:
                    st.write("### Porównanie aktywności dziennej")
                    act_df1 = df1_c.groupby("Data").size().reset_index(name="Partie")
                    act_df1["Gracz"] = u1
                    act_df2 = df2_c.groupby("Data").size().reset_index(name="Partie")
                    act_df2["Gracz"] = u2
                    act_comb = pd.concat([act_df1, act_df2])
                    
                    fig_act_c = px.bar(act_comb, x="Data", y="Partie", color="Gracz", barmode="group", 
                                   title="Ilość gier w czasie",
                                   color_discrete_sequence=[cp1, cp2])
                    fig_act_c.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                    st.plotly_chart(fig_act_c, use_container_width=True)
                    
                    st.write("### Zmiana ELO w czasie")
                    df1_elo = df1_c.copy()
                    df2_elo = df2_c.copy()
                    df1_elo["Gracz"] = u1
                    df2_elo["Gracz"] = u2
                    df_elo_comb = pd.concat([df1_elo, df2_elo]).sort_values("Timestamp")
                    
                    if not df_elo_comb.empty:
                        for m in ["Rapid", "Blitz", "Bullet"]:
                            mdf = df_elo_comb[df_elo_comb["Tryb"] == m]
                            if not mdf.empty:
                                fig_elo_c = px.line(mdf, x="Timestamp", y="ELO", color="Gracz", title=f"Ranking {m}",
                                                    color_discrete_sequence=[cp1, cp2])
                                fig_elo_c.update_layout(xaxis_title="", yaxis_title="ELO", height=300, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None))
                                st.plotly_chart(fig_elo_c, use_container_width=True)
                else:
                    st.info("Brak wystarczających danych do wygenerowania wykresów dla podanego filtru.")

            with tabs[2]:
                if not df1_c.empty and not df2_c.empty:
                    h_df1 = df1_c.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    h_df1["Win%"] = (h_df1["W"] / h_df1["G"] * 100).round(0).astype(int)
                    h_df1["Gracz"] = u1
                    
                    h_df2 = df2_c.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    h_df2["Win%"] = (h_df2["W"] / h_df2["G"] * 100).round(0).astype(int)
                    h_df2["Gracz"] = u2
                    
                    h_comb = pd.concat([h_df1, h_df2])
                    
                    st.subheader(t("win_by_hour"), help=t("chart_desc_comp"))
                    fig_h = px.bar(h_comb, x="Godzina", y="Win%", color="Gracz", barmode="group", 
                                   labels={"Godzina": t("hour"), "Win%": t("win_rate"), "G": t("games_count"), "Gracz": t("player")},
                                   hover_data={"G": True},
                                   color_discrete_sequence=[cp1, cp2])
                    fig_h.update_layout(title="", xaxis=dict(tickmode='linear', tick0=0, dtick=1, tickangle=0), legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                    fig_h.update_yaxes(range=[0, 100])
                    st.plotly_chart(fig_h, use_container_width=True)
                
                st.write("") 
                
                if not df1_c.empty and not df2_c.empty:
                    d_df1 = df1_c.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    d_df1["Win%"] = (d_df1["W"] / d_df1["G"] * 100).round(0).astype(int)
                    d_df1["Gracz"] = u1
                    
                    d_df2 = df2_c.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    d_df2["Win%"] = (d_df2["W"] / d_df2["G"] * 100).round(0).astype(int)
                    d_df2["Gracz"] = u2
                    
                    d_comb = pd.concat([d_df1, d_df2]).sort_values("Dzień_Nr")
                    
                    st.subheader(t("win_by_day"), help=t("chart_desc_comp"))
                    fig_d_c = px.bar(d_comb, x="Dzień", y="Win%", color="Gracz", barmode="group", 
                                     labels={"Dzień": t("day"), "Win%": t("win_rate"), "Gracz": t("player")},
                                     hover_data={"G": True},
                                     color_discrete_sequence=[cp1, cp2])
                    fig_d_c.update_layout(title="", xaxis_title="", legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                    fig_d_c.update_yaxes(range=[0, 100])
                    st.plotly_chart(fig_d_c, use_container_width=True)
                
                st.write("") 
                
                if not df1_c.empty and not df2_c.empty:
                    df1_c["Bin"] = df1_c["Ruchy"].apply(get_duration_bin)
                    df2_c["Bin"] = df2_c["Ruchy"].apply(get_duration_bin)
                    
                    b_df1 = df1_c.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    b_df1["Win%"] = (b_df1["W"] / b_df1["G"] * 100).round(0).astype(int)
                    b_df1["Gracz"] = u1
                    
                    b_df2 = df2_c.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    b_df2["Win%"] = (b_df2["W"] / b_df2["G"] * 100).round(0).astype(int)
                    b_df2["Gracz"] = u2
                    
                    b_comb = pd.concat([b_df1, b_df2])
                    
                    order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
                    
                    st.subheader(t("win_by_length"), help=t("chart_desc_comp"))
                    fig_b = px.bar(b_comb.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), 
                                   x="Bin", y="Win%", color="Gracz", barmode="group", 
                                   labels={"Bin": t("length"), "Win%": t("win_rate"), "G": t("games_count"), "Gracz": t("player")},
                                   hover_data={"G": True},
                                   color_discrete_sequence=[cp1, cp2])
                    fig_b.update_layout(title="", xaxis_title="", legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                    fig_b.update_yaxes(range=[0, 100])
                    st.plotly_chart(fig_b, use_container_width=True)

            with tabs[3]:
                st.write("### 🛡️ Najpopularniejsze Debiuty")
                
                def merge_openings(color_name):
                    df1_sub = df1_c[df1_c["Kolor"] == color_name]
                    df2_sub = df2_c[df2_c["Kolor"] == color_name]
                    
                    g1_op = df1_sub.groupby("Debiut_Grupa").size().reset_index(name=f"Partie [{u1}]")
                    g2_op = df2_sub.groupby("Debiut_Grupa").size().reset_index(name=f"Partie [{u2}]")
                    
                    m = pd.merge(g1_op, g2_op, on="Debiut_Grupa", how="outer").fillna(0)
                    m[f"Partie [{u1}]"] = m[f"Partie [{u1}]"].astype(int)
                    m[f"Partie [{u2}]"] = m[f"Partie [{u2}]"].astype(int)
                    m["Razem"] = m[f"Partie [{u1}]"] + m[f"Partie [{u2}]"]
                    return m.sort_values("Razem", ascending=False).drop(columns=["Razem"]).reset_index(drop=True)

                c_w_op, c_b_op = st.columns(2)
                with c_w_op:
                    st.markdown(f"<h5 style='text-align: center;'>⚪ {t('color_white')}</h5>", unsafe_allow_html=True)
                    st.dataframe(merge_openings("Białe").head(20), use_container_width=True, hide_index=True)
                    
                with c_b_op:
                    st.markdown(f"<h5 style='text-align: center;'>⚫ {t('color_black')}</h5>", unsafe_allow_html=True)
                    st.dataframe(merge_openings("Czarne").head(20), use_container_width=True, hide_index=True)

            if len(tabs) > 4:
                with tabs[4]:
                    h2 = df1_c[(df1_c['Przeciwnik'].str.lower() == u2.lower()) & (df1_c['Platforma'] == p2_p)].copy().sort_values("Timestamp").reset_index(drop=True)
                    if not h2.empty:
                        st.markdown(f"### H2H: {u1} vs {u2}")
                        h2_w, h2_d, h2_l = (h2["Wynik"] == "Wygrane").sum(), (h2["Wynik"] == "Remisy").sum(), (h2["Wynik"] == "Przegrane").sum()
                        
                        st.markdown(f"""
                        <div class="asym-header" style="font-size:1.1rem;">
                            <div style="width:30%; text-align:center; color:{cp1};">{u1} ({h2_w})</div>
                            <div style="width:40%; text-align:center; color:{cd};">REMISY: {h2_d} | RAZEM: {len(h2)}</div>
                            <div style="width:30%; text-align:center; color:{cp2};">{u2} ({h2_l})</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.write("")
                        
                        h2["Partia_Nr"] = h2.index + 1
                        h2["Ty"], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                        
                        fig_h2h = px.line(h2.melt(id_vars=["Partia_Nr"], value_vars=["Ty", u2]), 
                                          x="Partia_Nr", y="value", color="variable", 
                                          title="Wyścig zwycięstw H2H",
                                          color_discrete_sequence=[cp1, cp2])
                        fig_h2h.update_layout(xaxis_title="Numer partii", yaxis_title="Suma wygranych", 
                                              legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None))
                        st.plotly_chart(fig_h2h, use_container_width=True)
                        
                        st.write("**Historia spotkań:**")
                        st.dataframe(h2[["Data", "Tryb", "Kolor", "Wynik", "Ruchy", "Debiut"]].sort_values("Data", ascending=False), use_container_width=True, hide_index=True)
                    else: 
                        st.info(f"Brak zarejestrowanych bezpośrednich partii pomiędzy **{u1}** a **{u2}** (przy obecnych filtrach).")
