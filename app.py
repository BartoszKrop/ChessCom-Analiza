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

bg_color = "#ffffff" if st.session_state.theme == "Jasny" else "#0e1117"
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
    
    /* Wymuszenie poziomej linii dla nagłówka */
    div[data-testid="stHorizontalBlock"]:has(.profile-nick) {{
        flex-wrap: nowrap !important;
        align-items: center !important;
    }}
    img[src^="http"] {{ border-radius: 50%; }}
    
    {css_light if st.session_state.theme == "Jasny" else css_dark}
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

def get_opening_group(
