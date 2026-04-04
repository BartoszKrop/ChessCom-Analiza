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
if 'theme' not in st.session_state: st.session_state.theme = "Chess.com"
if 'cw_solo' not in st.session_state: st.session_state.cw_solo = True
if 'cb_solo' not in st.session_state: st.session_state.cb_solo = True
if 'cw_por' not in st.session_state: st.session_state.cw_por = True
if 'cb_por' not in st.session_state: st.session_state.cb_por = True

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="ChessStats", page_icon="♟️", layout="wide")

bg_dict = {
    "Jasny": "#f3f4f6", 
    "Ciemny": "#0e1117", 
    "Chess.com": "#312e2b", 
    "Neon Retro": "#0a0a14"
}
bg_color = bg_dict.get(st.session_state.theme, "#312e2b")

# --- WYMUSZENIE KOLORÓW PASKÓW MOBILNYCH (THEME-COLOR) ---
components.html(
    f"""
    <script>
        const head = window.parent.document.getElementsByTagName('head')[0];
        
        let metaTheme = window.parent.document.querySelector('meta[name="theme-color"]');
        if (!metaTheme) {{
            metaTheme = window.parent.document.createElement('meta');
            metaTheme.name = "theme-color";
            head.appendChild(metaTheme);
        }}
        metaTheme.content = "{bg_color}";
        
        let metaApple = window.parent.document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
        if (!metaApple) {{
            metaApple = window.parent.document.createElement('meta');
            metaApple.name = "apple-mobile-web-app-status-bar-style";
            head.appendChild(metaApple);
        }}
        metaApple.content = "black-translucent";
        
        let metaWebApp = window.parent.document.querySelector('meta[name="apple-mobile-web-app-capable"]');
        if (!metaWebApp) {{
            metaWebApp = window.parent.document.createElement('meta');
            metaWebApp.name = "apple-mobile-web-app-capable";
            metaWebApp.content = "yes";
            head.appendChild(metaWebApp);
        }}
    </script>
    """, height=0, width=0
)

# --- KOLORYSTYKA I STYLE WYKRESÓW (PLOTLY ENGINE) ---
if st.session_state.theme == "Chess.com":
    cw, cd, cl = "#81b64c", "#a7a6a2", "#fa412d"
    cp1, cp2 = "#81b64c", "#fa412d"
    c_scale = "Greens"
    chart_bg = "#262421" 
    grid_color = "#3d3b38"
    font_color = "#c3c3c0"
elif st.session_state.theme == "Neon Retro":
    cw, cd, cl = "#00ffff", "#8c43ff", "#ff007c"  
    cp1, cp2 = "#00ffff", "#ff007c"
    c_scale = "Purples"
    chart_bg = "rgba(18, 18, 38, 0.85)"
    grid_color = "rgba(140, 67, 255, 0.2)"
    font_color = "#e0e0ff"
elif st.session_state.theme == "Jasny":
    cw, cd, cl = "#1d4ed8", "#6b7280", "#dc2626"
    cp1, cp2 = "#1d4ed8", "#dc2626"
    c_scale = "Blues"
    chart_bg = "#ffffff"
    grid_color = "#e5e7eb"
    font_color = "#1f2937"
else: # Ciemny
    cw, cd, cl = "#1e88e5", "#8b949e", "#ef553b"
    cp1, cp2 = "#1e88e5", "#ef553b"
    c_scale = "Blues"
    chart_bg = "#161b22"
    grid_color = "#30363d"
    font_color = "#c9d1d9"

def style_chart(fig):
    fig.update_layout(
        paper_bgcolor=chart_bg,
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=font_color),
        margin=dict(l=10, r=10, t=20, b=10), 
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, title=None)
    )
    fig.update_xaxes(showgrid=False, gridcolor=grid_color, zerolinecolor=grid_color)
    fig.update_yaxes(showgrid=True, gridcolor=grid_color, zerolinecolor=grid_color)
    
    for trace in fig.data:
        if trace.type == 'bar':
            trace.marker.line.width = 0
            
    fig.update_layout(template="plotly_dark" if st.session_state.theme != "Jasny" else "plotly_white")
    return fig

# --- TŁUMACZENIA UI I SŁOWNIKI ---
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
    "streak_desc": {"pl": "Analizuje wyniki partii w zależności od passy w ramach ciągłej sesji (przerwa < 2h).", "en": "Analyzes game results based on streaks within a single session (break < 2h).", "de": "Analysiert Partien basierend auf Serien innerhalb einer Sitzung (Pause < 2h)."},
    "games_count": {"pl": "Ilość partii", "en": "Games count", "de": "Anzahl Partien"},
    "win_rate": {"pl": "Skuteczność (%)", "en": "Win Rate (%)", "de": "Erfolgsquote (%)"},
    "hour": {"pl": "Godzina", "en": "Hour", "de": "Stunde"},
    "length": {"pl": "Długość (ruchy)", "en": "Length (moves)", "de": "Länge (Züge)"},
    "day": {"pl": "Dzień", "en": "Day", "de": "Tag"},
    "player": {"pl": "Gracz", "en": "Player", "de": "Spieler"}
}

reason_dict = {
    "resigned": {"pl": "Rezygnacja", "en": "Resignation", "de": "Aufgabe"},
    "timeout": {"pl": "Czas", "en": "Timeout", "de": "Zeit"},
    "outoftime": {"pl": "Czas", "en": "Timeout", "de": "Zeit"},
    "checkmated": {"pl": "Mat", "en": "Checkmate", "de": "Schachmatt"},
    "mate": {"pl": "Mat", "en": "Checkmate", "de": "Schachmatt"},
    "abandoned": {"pl": "Opuszczenie", "en": "Abandoned", "de": "Verlassen"},
    "agreed": {"pl": "Remis", "en": "Draw", "de": "Remis"},
    "repetition": {"pl": "Powtórzenie", "en": "Repetition", "de": "Wiederholung"},
    "stalemate": {"pl": "Pat", "en": "Stalemate", "de": "Patt"},
    "insufficient": {"pl": "Niewyst. mat.", "en": "Insufficient", "de": "Ungenügend"},
    "50move": {"pl": "50 ruchów", "en": "50-move", "de": "50-Züge"},
    "timevsinsufficient": {"pl": "Czas vs Niewyst.", "en": "Time vs Ins.", "de": "Zeit vs Ungen."},
    "win": {"pl": "Wygrana", "en": "Win", "de": "Sieg"}
}

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

def t(key, default=""):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return ui_dict.get(key, {}).get(l, default if default else key)

def t_reason(reason):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return reason_dict.get(reason.lower(), {}).get(l, reason.capitalize())

def t_op(eng_name):
    if eng_name == "Brak" or not eng_name: return "Brak"
    l = lang_map.get(st.session_state.op_lang, "pl")
    if l == "en": return eng_name
    return op_translations.get(eng_name, {}).get(l, eng_name)

# --- CSS (DYNAMICZNY MOTYW) ---
css_dark = """
    .stApp { background-color: #0e1117; color: #ffffff; }
    [data-testid="stHeader"] { background-color: rgba(14, 17, 23, 0); }
    .stMetric, div.row-widget.stRadio > div { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px;}
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    .stButton>button[kind="primary"] { background-color: #1e88e5; color: white; border: none; }
"""
css_light = """
    .stApp { background-color: #f3f4f6; color: #000000; }
    [data-testid="stHeader"] { background-color: rgba(255, 255, 255, 0); }
    .stMetric, div.row-widget.stRadio > div { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    [data-testid="stMetricValue"], [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { color: #000000 !important; }
    [data-testid="stMetricLabel"] { color: #4b5563 !important; }
    .stTabs [data-baseweb="tab-list"] button { color: #4b5563; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #000000; }
"""
css_chesscom = """
    .stApp { 
        background-color: #312e2b;
        color: #ffffff; 
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    [data-testid="stHeader"] { background-color: rgba(0, 0, 0, 0); }
    .stMetric, div.row-widget.stRadio > div { 
        background-color: #262421; 
        border: none; 
        border-radius: 5px; 
    }
    [data-testid="stMetricValue"], [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { color: #ffffff !important; }
    [data-testid="stMetricLabel"] { color: #c3c3c0 !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; }
    .stTabs [data-baseweb="tab-list"] button { color: #8b8987; font-weight: 600; padding-bottom: 10px; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #ffffff; border-bottom: 3px solid #81b64c; }
    .stButton>button[kind="primary"] { 
        background-color: #81b64c; 
        color: white; 
        border: none; 
        border-bottom: 4px solid #537b2f;
        border-radius: 5px;
        font-weight: bold;
        font-size: 1.1rem;
        transition: all 0.1s;
    }
    .stButton>button[kind="primary"]:active { border-bottom: 0px; transform: translateY(4px); }
    .stButton>button[kind="secondary"] {
        background-color: #3d3b38;
        color: #c3c3c0;
        border: none;
        border-radius: 5px;
    }
"""
css_neon = """
    .stApp { 
        background-color: #0a0a14; 
        background-image: radial-gradient(circle at top right, #1a0b2e, #0a0a14);
        background-attachment: fixed;
        color: #e0e0ff; 
    }
    [data-testid="stHeader"] { background-color: rgba(0, 0, 0, 0); }
    .stMetric, div.row-widget.stRadio > div { 
        background-color: rgba(18, 18, 38, 0.85); 
        border: 1px solid #8c43ff; 
        border-radius: 12px;
        box-shadow: 0 0 10px rgba(140, 67, 255, 0.2); 
    }
    [data-testid="stMetricValue"], [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 { 
        color: #00ffff !important; 
        text-shadow: 0 0 4px rgba(0, 255, 255, 0.4); 
    }
    [data-testid="stMetricLabel"] { color: #ff007c !important; }
    .stTabs [data-baseweb="tab-list"] button { color: #6a6a8c; text-transform: uppercase; letter-spacing: 1px;}
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #00ffff; border-bottom-color: #00ffff; text-shadow: 0 0 8px rgba(0,255,255,0.6); }
    .stButton>button[kind="primary"] { 
        background-color: rgba(0, 255, 255, 0.1); 
        color: #00ffff; 
        border: 1px solid #00ffff; 
        border-radius: 4px;
        box-shadow: 0 0 10px rgba(0, 255, 255, 0.3);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stButton>button[kind="primary"]:hover { background-color: rgba(0, 255, 255, 0.3); box-shadow: 0 0 20px rgba(0, 255, 255, 0.6); }
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
    [data-testid="stMetricValue"] {{ font-size: 1.1rem !important; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.8rem !important; text-transform: uppercase; }}
    .stMetric {{ padding: 12px; }}
    .block-container {{ padding: 1rem; top: 1rem; }}
    
    [data-testid="stPopover"] > button {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        color: inherit !important;
    }}
    
    {active_css}
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE ---
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
    for plat in mdf["Platforma"].unique():
        pdf = mdf[mdf["Platforma"] == plat]
        peak = int(pdf["ELO"].max())
        curr = int(pdf.sort_values("Timestamp").iloc[-1]["ELO"])
        if peak > best_peak: best_peak = peak
        if curr > best_curr: best_curr = curr
    return f"{best_peak}", f"{best_curr}", best_curr

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user, platform="Chess.com"):
    cols = ["Konto", "Platforma", "Timestamp", "Godzina", "Dzień", "Dzień_Nr", "Data", "Miesiąc", "Tryb", "Wynik", "ELO", "Elo_Rywala", "Ruchy", "Debiut", "Debiut_Grupa", "Przeciwnik", "Kolor", "Powod", "PGN_Raw", "Link"]
    try:
        headers = {"User-Agent": f"AnalizySzachowe-V30-{user}"}
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        all_games = []
        k_id = f"{user} ({'C' if platform == 'Chess.com' else 'L'})"
        
        if platform == "Chess.com":
            p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
            a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
            if p_res.status_code != 200: return None, pd.DataFrame(columns=cols)
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
            return {"avatar": p_res.json().get("avatar", "")}, pd.DataFrame(all_games, columns=cols) if all_games else pd.DataFrame(columns=cols)
            
        elif platform == "Lichess":
            p_res = requests.get(f"https://lichess.org/api/user/{user}", headers=headers)
            if p_res.status_code != 200: return None, pd.DataFrame(columns=cols)
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
            return {"avatar": p_res.json().get("profile", {}).get("avatar", "")}, pd.DataFrame(all_games, columns=cols) if all_games else pd.DataFrame(columns=cols)
    except: return None, pd.DataFrame(columns=cols)

# --- SESSION & START ---
for k in ['data','data2','url', 'user', 'user2', 'plat2']: 
    if k not in st.session_state: st.session_state[k] = None if k in ['data','data2','url'] else ""
if 'platforms' not in st.session_state: st.session_state.platforms = []

if st.session_state.data is None:
    c_l1, c_l2 = st.columns([7, 3])
    c_l1.title(f"♟️ {t('title')}")
    with c_l2.expander("⚙️ Ustawienia"):
        st.selectbox("🌍 Język UI", ["Polski", "English", "Deutsch"], key="ui_lang")
        st.selectbox("♟️ Język Debiutów", ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio("🎨 Motyw", ["Chess.com", "Neon Retro", "Ciemny", "Jasny"], key="theme", horizontal=True)

    log_m = st.radio("Zasięg:", ["Jeden profil", "Połącz profile (C+L)"], horizontal=True)
    if log_m == "Jeden profil":
        c1, c2 = st.columns([1, 4])
        plat = c1.selectbox("Plat:", ["Chess.com", "Lichess"])
        nick = c2.text_input("Nick:")
        if st.button(t("btn_analize"), type="primary", use_container_width=True):
            if nick:
                with st.spinner("Pobieranie..."):
                    f = fetch_data(nick, plat)
                    if f[0] is not None and not f[1].empty: 
                        st.session_state.data, st.session_state.user, st.session_state.platforms = f, nick, [plat]
                        st.rerun()
                    else: st.error("Nie znaleziono partii dla tego gracza.")
    else:
        c1, c2 = st.columns(2)
        p1, n1 = c1.selectbox("P1:", ["Chess.com", "Lichess"]), c1.text_input("Nick 1:")
        p2, n2 = c2.selectbox("P2:", ["Lichess", "Chess.com"]), c2.text_input("Nick 2:")
        if st.button(t("btn_connect"), type="primary", use_container_width=True):
            if n1 and n2:
                with st.spinner("Łączenie..."):
                    f1, f2 = fetch_data(n1, p1), fetch_data(n2, p2)
                    if f1[0] is not None and not f1[1].empty and f2[0] is not None and not f2[1].empty:
                        st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                        st.session_state.user, st.session_state.platforms = f"{n1}+{n2}", list(set([p1, p2]))
                        st.rerun()
                    else: st.error("Błąd pobierania danych. Upewnij się, że oba konta posiadają historię gier.")
else:
    profile, df_loc = st.session_state.data
    username, user_plats = st.session_state.user, st.session_state.platforms
    
    if df_loc.empty:
        st.error("Błąd krytyczny: Zbiór danych jest pusty. Spróbuj odświeżyć.")
        st.stop()
        
    df_loc["Debiut_Grupa"] = df_loc["Debiut_Grupa"].apply(t_op)
    
    if profile.get("avatar"):
        border_color = cw if st.session_state.theme == "Neon Retro" else "transparent"
        html_str = (
            f"<div style='display: flex; align-items: center; gap: 15px; margin-bottom: 15px;'>"
            f"<img src='{profile.get('avatar')}' width='60' style='border-radius: 5px; border: 2px solid {border_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.5);'>"
            f"<h2 style='margin: 0; padding: 0;'>{username}</h2>"
            f"</div>"
        )
        st.markdown(html_str, unsafe_allow_html=True)
    else:
        st.markdown(f"<h2 style='margin-bottom: 15px;'>{username}</h2>", unsafe_allow_html=True)
    
    with st.expander("⚙️ Ustawienia"):
        app_m = st.radio("Widok:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], label_visibility="collapsed", horizontal=True)
        c_l_ui, c_l_op = st.columns(2)
        c_l_ui.selectbox("🌍 Język UI", ["Polski", "English", "Deutsch"], key="ui_lang")
        c_l_op.selectbox("♟️ Język Debiutów", ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio("🎨 Motyw", ["Chess.com", "Neon Retro", "Ciemny", "Jasny"], key="theme", horizontal=True)
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button(t("btn_refresh"), use_container_width=True):
                fetch_data.clear() 
                st.session_state.data = None; st.rerun()
        with c_btn2:
            if st.button(t("btn_change"), type="primary", use_container_width=True):
                for k in ['data','data2','url','user','user2','plat2']: st.session_state[k] = None if k in ['data','data2','url'] else ""
                st.session_state.platforms = []; st.rerun()
    
    st.divider()

    if app_m == "👤 Moja Analiza":
        m1, m2, m3 = st.columns(3)
        p_r, c_r, _ = calc_elo(df_loc, "Rapid"); p_b, c_b, _ = calc_elo(df_loc, "Blitz"); p_bl, c_bl, _ = calc_elo(df_loc, "Bullet")
        m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
        m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
        m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")

        with st.expander("🔍 Filtry"):
            f1, f2 = st.columns(2)
            d_r = f1.date_input("Zakres dat:", value=(df_loc["Data"].min(), df_loc["Data"].max()))
            s_m = f2.selectbox("Tryb:", ["Wszystkie"] + sorted(df_loc["Tryb"].unique().tolist()))
            
            st.write(f"<span style='font-size:0.9rem; font-weight:bold;'>Kolor</span>", unsafe_allow_html=True)
            c_w_btn, c_b_btn, _ = st.columns([1, 1, 4])
            if c_w_btn.button("⚪ Białe", type="primary" if st.session_state.cw_solo else "secondary", use_container_width=True, key="sw_solo"):
                st.session_state.cw_solo = not st.session_state.cw_solo; st.rerun()
            if c_b_btn.button("⚫ Czarne", type="primary" if st.session_state.cb_solo else "secondary", use_container_width=True, key="sb_solo"):
                st.session_state.cb_solo = not st.session_state.cb_solo; st.rerun()
            
            s_c = []
            if st.session_state.cw_solo: s_c.append("Białe")
            if st.session_state.cb_solo: s_c.append("Czarne")
            
            s_h = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df_loc.copy()
        
        if isinstance(d_r, (list, tuple)):
            if len(d_r) == 2:
                df_f = df_f[(df_f["Data"] >= d_r[0]) & (df_f["Data"] <= d_r[1])]
            elif len(d_r) == 1:
                df_f = df_f[df_f["Data"] == d_r[0]]
        elif isinstance(d_r, datetime.date):
            df_f = df_f[df_f["Data"] == d_r]
            
        df_f = df_f[df_f["Kolor"].isin(s_c) & (df_f["Godzina"] >= s_h[0]) & (df_f["Godzina"] <= s_h[1])]
        if s_m != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_m]

        if not df_f.empty:
            t_stat, t_hist, t_czas, t_deb, t_ana = st.tabs(["📊 Statystyki", "📅 Historia", "⏳ Czas", "🔬 Debiuty", "🧠 Analiza"])
            
            with t_stat:
                w, d, l = (df_f["Wynik"]=="Wygrane").sum(), (df_f["Wynik"]=="Remisy").sum(), (df_f["Wynik"]=="Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                
                mod_w = df_f[df_f["Kolor"] == "Białe"]["Debiut_Grupa"].mode()
                fav_w = mod_w[0] if not mod_w.empty else "Brak"
                mod_b = df_f[df_f["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()
                fav_b = mod_b[0] if not mod_b.empty else "Brak"
                
                info_html = (
                    f"<div style='background-color: {chart_bg}; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid {cw}; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'>"
                    f"<div style='font-weight: bold; color: {font_color}; margin-bottom: 5px;'>Ulubione debiuty:</div>"
                    f"<div style='font-size: 0.9rem; color: {font_color};'>⚪ <b>{fav_w}</b> &emsp;|&emsp; ⚫ <b>{fav_b}</b></div>"
                    f"</div>"
                )
                st.markdown(info_html, unsafe_allow_html=True)
                
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.markdown(f"### Ranking {m}")
                        fig_elo = px.line(mdf, x="Timestamp", y="ELO", color="Konto", color_discrete_sequence=[cw])
                        fig_elo = style_chart(fig_elo)
                        st.plotly_chart(fig_elo, use_container_width=True)

                st.divider()
                c1, c2 = st.columns(2)
                df_f_pie = df_f.copy()
                df_f_pie["Powod_T"] = df_f_pie["Powod"].apply(t_reason)
                
                if not df_f_pie[df_f_pie["Wynik"]=="Wygrane"].empty:
                    with c1:
                        st.markdown(f"### {t('win_reason')}")
                        fig_pie_w = px.pie(df_f_pie[df_f_pie["Wynik"]=="Wygrane"], names="Powod_T", hole=0.4, color_discrete_sequence=[cw, "#5ab4ac", "#d8b365", "#01665e"])
                        fig_pie_w = style_chart(fig_pie_w)
                        st.plotly_chart(fig_pie_w, use_container_width=True)
                
                if not df_f_pie[df_f_pie["Wynik"]=="Przegrane"].empty:
                    with c2:
                        st.markdown(f"### {t('loss_reason')}")
                        fig_pie_l = px.pie(df_f_pie[df_f_pie["Wynik"]=="Przegrane"], names="Powod_T", hole=0.4, color_discrete_sequence=[cl, "#c51b7d", "#e9a3c9", "#4d9221"])
                        fig_pie_l = style_chart(fig_pie_l)
                        st.plotly_chart(fig_pie_l, use_container_width=True)

            with t_hist:
                st.markdown("### Aktywność i wyniki dzienne")
                act_df = df_f.groupby(["Data", "Wynik"]).size().reset_index(name="Partie")
                fig_act = px.bar(act_df, x="Data", y="Partie", color="Wynik", 
                                 color_discrete_map={"Wygrane": cw, "Remisy": cd, "Przegrane": cl},
                                 category_orders={"Wynik": ["Wygrane", "Remisy", "Przegrane"]})
                fig_act.update_layout(barmode='stack')
                fig_act = style_chart(fig_act)
                st.plotly_chart(fig_act, use_container_width=True)
                
                mon = df_f.groupby("Miesiąc").agg(G=('Wynik','count'), W=('Wynik',lambda x:(x=='Wygrane').sum()), R=('Wynik',lambda x:(x=='Remisy').sum()), L=('Wynik',lambda x:(x=='Przegrane').sum())).reset_index().sort_values("Miesiąc", ascending=False)
                mon["Win%"] = (mon["W"]/mon["G"]*100).round(0).astype(int)
                st.dataframe(mon.rename(columns={"G":"Gry"}), use_container_width=True, hide_index=True)

            with t_czas:
                h_st = df_f.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                h_st["Win%"] = (h_st["W"] / h_st["G"] * 100).round(0).astype(int)
                
                st.markdown(f"### {t('win_by_hour')}")
                fig_h = px.bar(h_st, x="Godzina", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Godzina": t("hour"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_h.update_layout(coloraxis_showscale=False)
                fig_h.update_yaxes(range=[0, 100])
                fig_h = style_chart(fig_h)
                st.plotly_chart(fig_h, use_container_width=True)
                
                st.write("") 
                
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["G"] * 100).round(0).astype(int)
                
                st.markdown(f"### {t('win_by_day')}")
                fig_d = px.bar(d_st, x="Dzień", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Dzień": t("day"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_d.update_layout(coloraxis_showscale=False)
                fig_d.update_yaxes(range=[0, 100])
                fig_d = style_chart(fig_d)
                st.plotly_chart(fig_d, use_container_width=True)
                
                st.write("")
                
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["G"] * 100).round(0).astype(int)
                order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
                
                st.markdown(f"### {t('win_by_length')}")
                fig_dur = px.bar(dst.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), x="Bin", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Bin": t("length"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_dur.update_layout(coloraxis_showscale=False)
                fig_dur.update_yaxes(range=[0, 100])
                fig_dur = style_chart(fig_dur)
                st.plotly_chart(fig_dur, use_container_width=True)
                
                st.write("")
                
                st.subheader("Wpływ serii na wyniki", help=t("streak_desc"))
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
                if t_res: 
                    fig_str = px.bar(pd.DataFrame(t_res), x="Seria", y="Win%", color="Typ", barmode='group', text="Win%", hover_data=["Partie"], color_discrete_map={"Po serii Wygranych":cw, "Po serii Porażek":cl})
                    fig_str = style_chart(fig_str)
                    st.plotly_chart(fig_str, use_container_width=True)

            with t_deb:
                c_w1, c_b1 = st.columns(2)
                df_w = df_f[df_f["Kolor"] == "Białe"]
                df_b = df_f[df_f["Kolor"] == "Czarne"]
                
                with c_w1:
                    st.markdown(f"<h5 style='text-align: center; color: {font_color};'>⚪ {t('color_white')}</h5>", unsafe_allow_html=True)
                    if not df_w.empty:
                        op_g_w = df_w.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_w.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                        with st.expander(f"Szczegółowe Warianty - ⚪ {t('color_white')}"):
                            op_w = df_w.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            st.dataframe(op_w.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii")
                        
                with c_b1:
                    st.markdown(f"<h5 style='text-align: center; color: {font_color};'>⚫ {t('color_black')}</h5>", unsafe_allow_html=True)
                    if not df_b.empty:
                        op_g_b = df_b.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_b.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                        with st.expander(f"Szczegółowe Warianty - ⚫ {t('color_black')}"):
                            op_b = df_b.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            st.dataframe(op_b.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii")

            with t_ana:
                fa1, fa2, fa3 = st.columns([1,1,1])
                d_val = fa1.date_input("Dzień do analizy:", value=df_f["Data"].max())
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
                    if st.button("Przygotuj analizę (Lichess Engine)", type="primary", use_container_width=True):
                        with st.spinner("Przesyłanie PGN do analizy..."):
                            st.session_state.url = g_sel["Link"] if g_sel["Platforma"]=="Lichess" else import_to_lichess(g_sel["PGN_Raw"]); st.rerun()
                    if st.session_state.url:
                        btn_html = (
                            f"<a href='{st.session_state.url}' target='_blank' style='display:block; width:100%; text-align:center; background-color:{cw}; color:white; padding:12px; border-radius:5px; text-decoration:none; font-weight:bold; margin-top:10px;'>"
                            f"OTWÓRZ ANALIZĘ ➡️"
                            f"</a>"
                        )
                        st.markdown(btn_html, unsafe_allow_html=True)
                else:
                    st.info("Brak partii do analizy dla podanych kryteriów.")

    elif app_m == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        p2 = c2.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        n2 = c2.text_input("Nick rywala:")
        
        if st.button("Pobierz dane rywala", type="primary", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie danych dla {n2}..."):
                    f2 = fetch_data(n2, p2)
                    if f2[1] is not None and not f2[1].empty: 
                        st.session_state.data2, st.session_state.user2, st.session_state.plat2 = f2[1], n2, p2
                        st.rerun()
                    else:
                        st.error("Nie udało się pobrać danych rywala lub gracz nie ma historii.")

        if st.session_state.data2 is not None:
            df2 = st.session_state.data2.copy()
            df2["Debiut_Grupa"] = df2["Debiut_Grupa"].apply(t_op)
            
            u1, u2, p2_p = username, st.session_state.user2, st.session_state.plat2
            
            with st.expander("🔍 Filtry porównania", expanded=False):
                fx1, fx2 = st.columns(2)
                v_min = [d for d in [df_loc["Data"].min(), df2["Data"].min()] if pd.notnull(d)]
                v_max = [d for d in [df_loc["Data"].max(), df2["Data"].max()] if pd.notnull(d)]
                min_date = min(v_min) if v_min else datetime.today().date()
                max_date = max(v_max) if v_max else datetime.today().date()
                
                dr_c = fx1.date_input("Zakres dat:", value=(min_date, max_date), key="c_dr")
                wspolne_tryby = list(set(df_loc["Tryb"].unique()) | set(df2["Tryb"].unique()))
                sm_c = fx2.selectbox("Tryb:", ["Wszystkie"] + sorted(wspolne_tryby), key="c_sm")
                
                c_w_por, c_b_por, _ = st.columns([1, 1, 4])
                if c_w_por.button("⚪ Białe", type="primary" if st.session_state.cw_por else "secondary", use_container_width=True, key="por_w"):
                    st.session_state.cw_por = not st.session_state.cw_por; st.rerun()
                if c_b_por.button("⚫ Czarne", type="primary" if st.session_state.cb_por else "secondary", use_container_width=True, key="por_b"):
                    st.session_state.cb_por = not st.session_state.cb_por; st.rerun()
                
                sc_c = []
                if st.session_state.cw_por: sc_c.append("Białe")
                if st.session_state.cb_por: sc_c.append("Czarne")
                
                sh_c = st.slider("Godziny:", 0, 23, (0, 23), key="c_sh")

            df1_c, df2_c = df_loc.copy(), df2.copy()
            
            if isinstance(dr_c, (list, tuple)):
                if len(dr_c) == 2:
                    df1_c = df1_c[(df1_c["Data"] >= dr_c[0]) & (df1_c["Data"] <= dr_c[1])]
                    df2_c = df2_c[(df2_c["Data"] >= dr_c[0]) & (df2_c["Data"] <= dr_c[1])]
                elif len(dr_c) == 1:
                    df1_c = df1_c[df1_c["Data"] == dr_c[0]]
                    df2_c = df2_c[df2_c["Data"] == dr_c[0]]
                
            df1_c = df1_c[df1_c["Kolor"].isin(sc_c) & (df1_c["Godzina"] >= sh_c[0]) & (df1_c["Godzina"] <= sh_c[1])]
            df2_c = df2_c[df2_c["Kolor"].isin(sc_c) & (df2_c["Godzina"] >= sh_c[0]) & (df2_c["Godzina"] <= sh_c[1])]
            
            if sm_c != "Wszystkie":
                df1_c = df1_c[df1_c["Tryb"] == sm_c]
                df2_c = df2_c[df2_c["Tryb"] == sm_c]

            tabs_names = ["📊 Ogólne Statystyki", "📅 Historia", "⏳ Czas", "🔬 Debiuty"]
            if p2_p in user_plats: tabs_names.append("🥊 H2H")
            tabs = st.tabs(tabs_names)

            with tabs[0]:
                g1, g2 = len(df1_c), len(df2_c)
                w1 = int(round((df1_c["Wynik"]=="Wygrane").sum()/g1*100,0)) if g1 > 0 else 0
                w2 = int(round((df2_c["Wynik"]=="Wygrane").sum()/g2*100,0)) if g2 > 0 else 0
                d1 = int(round((df1_c["Wynik"]=="Remisy").sum()/g1*100,0)) if g1 > 0 else 0
                d2 = int(round((df2_c["Wynik"]=="Remisy").sum()/g2*100,0)) if g2 > 0 else 0

                k1, k2, k3 = st.columns(3)
                k1.metric("Rozegrane Partie", f"{g1} / {g2}")
                k2.metric("Win Rate (%)", f"{w1}% / {w2}%", w1 - w2)
                k3.metric("Draw Rate (%)", f"{d1}% / {d2}%", d1 - d2)

                st.divider()
                st.markdown("<h4 style='color: #ffffff;'>Sposób zakończenia partii</h4>", unsafe_allow_html=True)
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
                        with c_r1:
                            st.markdown("### Jak wygrywają?")
                            fig_r_w = px.bar(df_win, x="Powod_T", y="Ilość", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                            fig_r_w = style_chart(fig_r_w)
                            st.plotly_chart(fig_r_w, use_container_width=True)

                    df_loss = df_r_comb[df_r_comb["Wynik"] == "Przegrane"].groupby(["Powod_T", "Gracz"]).size().reset_index(name="Ilość")
                    if not df_loss.empty:
                        with c_r2:
                            st.markdown("### Jak przegrywają?")
                            fig_r_l = px.bar(df_loss, x="Powod_T", y="Ilość", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                            fig_r_l = style_chart(fig_r_l)
                            st.plotly_chart(fig_r_l, use_container_width=True)

            with tabs[1]:
                if not df1_c.empty and not df2_c.empty:
                    act_df1 = df1_c.groupby("Data").size().reset_index(name="Partie")
                    act_df1["Gracz"] = u1
                    act_df2 = df2_c.groupby("Data").size().reset_index(name="Partie")
                    act_df2["Gracz"] = u2
                    act_comb = pd.concat([act_df1, act_df2])
                    
                    st.markdown("### Porównanie aktywności dziennej")
                    fig_act_c = px.bar(act_comb, x="Data", y="Partie", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                    fig_act_c = style_chart(fig_act_c)
                    st.plotly_chart(fig_act_c, use_container_width=True)
                    
                    st.markdown("<h4 style='color: #ffffff; margin-top:20px;'>Zmiana ELO w czasie</h4>", unsafe_allow_html=True)
                    df1_elo = df1_c.copy()
                    df2_elo = df2_c.copy()
                    df1_elo["Gracz"] = u1
                    df2_elo["Gracz"] = u2
                    df_elo_comb = pd.concat([df1_elo, df2_elo]).sort_values("Timestamp")
                    
                    for m in ["Rapid", "Blitz", "Bullet"]:
                        mdf = df_elo_comb[df_elo_comb["Tryb"] == m]
                        if not mdf.empty:
                            st.markdown(f"### Ranking {m}")
                            fig_elo_c = px.line(mdf, x="Timestamp", y="ELO", color="Gracz", color_discrete_sequence=[cp1, cp2])
                            fig_elo_c = style_chart(fig_elo_c)
                            st.plotly_chart(fig_elo_c, use_container_width=True)

            with tabs[2]:
                if not df1_c.empty and not df2_c.empty:
                    h_df1 = df1_c.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    h_df1["Win%"] = (h_df1["W"] / h_df1["G"] * 100).round(0).astype(int)
                    h_df1["Gracz"] = u1
                    
                    h_df2 = df2_c.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    h_df2["Win%"] = (h_df2["W"] / h_df2["G"] * 100).round(0).astype(int)
                    h_df2["Gracz"] = u2
                    
                    h_comb = pd.concat([h_df1, h_df2])
                    
                    st.markdown("### Skuteczność wg godzin")
                    fig_h_c = px.bar(h_comb, x="Godzina", y="Win%", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                    fig_h_c.update_yaxes(range=[0, 100])
                    fig_h_c = style_chart(fig_h_c)
                    st.plotly_chart(fig_h_c, use_container_width=True)

                    d_df1 = df1_c.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    d_df1["Win%"] = (d_df1["W"] / d_df1["G"] * 100).round(0).astype(int)
                    d_df1["Gracz"] = u1
                    
                    d_df2 = df2_c.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    d_df2["Win%"] = (d_df2["W"] / d_df2["G"] * 100).round(0).astype(int)
                    d_df2["Gracz"] = u2
                    
                    d_comb = pd.concat([d_df1, d_df2]).sort_values("Dzień_Nr")
                    
                    st.markdown("### Skuteczność wg dni")
                    fig_d_c = px.bar(d_comb, x="Dzień", y="Win%", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                    fig_d_c.update_yaxes(range=[0, 100])
                    fig_d_c = style_chart(fig_d_c)
                    st.plotly_chart(fig_d_c, use_container_width=True)
                    
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
                    
                    st.markdown("### Skuteczność wg długości partii")
                    fig_b_c = px.bar(b_comb.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), 
                                   x="Bin", y="Win%", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2])
                    fig_b_c.update_yaxes(range=[0, 100])
                    fig_b_c = style_chart(fig_b_c)
                    st.plotly_chart(fig_b_c, use_container_width=True)

            with tabs[3]:
                st.write("### 🛡️ Najpopularniejsze Debiuty (Wspólne)")
                
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
                    st.markdown(f"<h5 style='text-align: center; color: {font_color};'>⚪ {t('color_white')}</h5>", unsafe_allow_html=True)
                    st.dataframe(merge_openings("Białe").head(20), use_container_width=True, hide_index=True)
                    
                with c_b_op:
                    st.markdown(f"<h5 style='text-align: center; color: {font_color};'>⚫ {t('color_black')}</h5>", unsafe_allow_html=True)
                    st.dataframe(merge_openings("Czarne").head(20), use_container_width=True, hide_index=True)

            if len(tabs) > 4:
                with tabs[4]:
                    h2 = df1_c[(df1_c['Przeciwnik'].str.lower() == u2.lower()) & (df1_c['Platforma'] == p2_p)].copy().sort_values("Timestamp").reset_index(drop=True)
                    if not h2.empty:
                        h2_w, h2_d, h2_l = (h2["Wynik"] == "Wygrane").sum(), (h2["Wynik"] == "Remisy").sum(), (h2["Wynik"] == "Przegrane").sum()
                        
                        border_css = f"border: 1px solid {grid_color};" if st.session_state.theme != "Chess.com" else "box-shadow: 0 4px 6px rgba(0,0,0,0.3);"
                        h2_html = (
                            f"<div style='background-color: {chart_bg}; padding: 20px; border-radius: 8px; margin-bottom: 30px; {border_css}'>"
                            f"<div style='display: flex; justify-content: space-between; align-items: center; width: 100%; max-width: 600px; margin: 0 auto;'>"
                            f"<div style='text-align: right; width: 33%;'>"
                            f"<div style='color: {cp1}; font-size: 1.1rem; margin-bottom: 5px; font-weight: bold; overflow: hidden; text-overflow: ellipsis;'>{u1}</div>"
                            f"<div style='color: {cp1}; font-size: 2.2rem; font-weight: bold; line-height: 1;'>{h2_w}</div>"
                            f"</div>"
                            f"<div style='text-align: center; width: 33%; border-left: 1px solid {grid_color}; border-right: 1px solid {grid_color}; padding: 0 10px;'>"
                            f"<div style='color: {font_color}; font-size: 0.8rem; font-weight: bold; margin-bottom: 8px;'>REMISY: {h2_d}</div>"
                            f"<div style='color: {font_color}; font-size: 0.8rem; font-weight: bold;'>RAZEM:<br><span style='font-size: 1.1rem; color: {font_color}; display: inline-block; margin-top: 4px;'>{len(h2)}</span></div>"
                            f"</div>"
                            f"<div style='text-align: left; width: 33%;'>"
                            f"<div style='color: {cp2}; font-size: 1.1rem; margin-bottom: 5px; font-weight: bold; overflow: hidden; text-overflow: ellipsis;'>{u2}</div>"
                            f"<div style='color: {cp2}; font-size: 2.2rem; font-weight: bold; line-height: 1;'>{h2_l}</div>"
                            f"</div>"
                            f"</div>"
                            f"</div>"
                        )
                        st.markdown(h2_html, unsafe_allow_html=True)
                        
                        h2["Partia_Nr"] = h2.index + 1
                        h2["Ty"], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                        
                        st.markdown("### Wyścig zwycięstw")
                        fig_h2h = px.line(h2.melt(id_vars=["Partia_Nr"], value_vars=["Ty", u2]), 
                                          x="Partia_Nr", y="value", color="variable", color_discrete_sequence=[cp1, cp2])
                        fig_h2h = style_chart(fig_h2h)
                        st.plotly_chart(fig_h2h, use_container_width=True)
                        
                        st.write("**Historia spotkań:**")
                        st.dataframe(h2[["Data", "Tryb", "Kolor", "Wynik", "Ruchy", "Debiut"]].sort_values("Data", ascending=False), use_container_width=True, hide_index=True)
                    else: 
                        st.info(f"Brak zarejestrowanych bezpośrednich partii pomiędzy **{u1}** a **{u2}** (przy obecnych filtrach).")
