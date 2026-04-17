import streamlit as st  
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, date
import re
import json
from io import BytesIO
import streamlit.components.v1 as components
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

API_TIMEOUT = 10  # seconds for individual API requests
MAX_MOVE_TIME_SECONDS = 300
NUM_DECILES = 10
VIEW_MY = "👤 Moja Analiza"
VIEW_COMPARE = "⚔️ Porównanie Graczy"
SCOPE_SINGLE = "Jeden profil"
SCOPE_MERGE = "Połącz profile (C+L)"
SCOPE_COMPARE = "Porównanie graczy (start)"

# --- KONFIGURACJA STRONY (MUSI BYĆ PIERWSZA) ---
st.set_page_config(page_title="ChessStats", page_icon="♟️", layout="wide")

# --- INICJALIZACJA STANU SESJI (USTAWIENIA) ---
if 'ui_lang' not in st.session_state: st.session_state.ui_lang = "Polski"
if 'op_lang' not in st.session_state: st.session_state.op_lang = "English"
if 'theme' not in st.session_state: st.session_state.theme = "Chess.com"
if 'cw_solo' not in st.session_state: st.session_state.cw_solo = True
if 'cb_solo' not in st.session_state: st.session_state.cb_solo = True
if 'cw_por' not in st.session_state: st.session_state.cw_por = True
if 'cb_por' not in st.session_state: st.session_state.cb_por = True
if 'fetch_args' not in st.session_state: st.session_state.fetch_args = []
if 'default_view' not in st.session_state: st.session_state.default_view = VIEW_MY

bg_dict = {
    "Jasny": "#f3f4f6",
    "Ciemny": "#0e1117",
    "Chess.com": "#312e2b",
    "Neon Retro": "#0a0a14",
    "Morski": "#0d1b2a",
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
elif st.session_state.theme == "Morski":
    cw, cd, cl = "#00b4d8", "#90e0ef", "#ff6b6b"
    cp1, cp2 = "#00b4d8", "#ff6b6b"
    c_scale = "Blues"
    chart_bg = "#1b2838"
    grid_color = "#2a3a4a"
    font_color = "#caf0f8"
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
    "player": {"pl": "Gracz", "en": "Player", "de": "Spieler"},
    "download_raw": {"pl": "Pobierz surowe dane (CSV)", "en": "Download raw data (CSV)", "de": "Rohdaten herunterladen (CSV)"},
    "download_report": {"pl": "Pobierz raport (PDF)", "en": "Download report (PDF)", "de": "Bericht herunterladen (PDF)"},
    "download_menu": {"pl": "Pobierz raporty", "en": "Download reports", "de": "Berichte herunterladen"},
    "download_choose": {"pl": "Wybierz format", "en": "Choose format", "de": "Format wählen"},
    "download_now": {"pl": "Pobierz", "en": "Download", "de": "Herunterladen"},
    "move_pace": {"pl": "Tempo ruchu w trakcie partii", "en": "Move pace during game", "de": "Zugtempo im Spielverlauf"},
    "decile": {"pl": "Segment partii", "en": "Game segment", "de": "Spielsegment"},
    "avg_move_seconds": {"pl": "Śr. sekundy / ruch", "en": "Avg seconds / move", "de": "Ø Sekunden / Zug"},
    "prepare_analysis": {"pl": "Przygotuj analizę (Lichess Engine)", "en": "Prepare analysis (Lichess Engine)", "de": "Analyse vorbereiten (Lichess Engine)"},
    "compare_quick": {"pl": "Porównanie graczy (start)", "en": "Player comparison (start)", "de": "Spielervergleich (Start)"},
    "no_tempo_data": {"pl": "Brak danych zegara do analizy tempa ruchu dla aktualnych partii.", "en": "No clock data available for move-pace analysis in current games.", "de": "Keine Uhrdaten für die Zugtempo-Analyse in den aktuellen Partien verfügbar."}
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

ui_phrases = {
    "⚙️ Ustawienia": {"en": "⚙️ Settings", "de": "⚙️ Einstellungen"},
    "🌍 Język UI": {"en": "🌍 UI Language", "de": "🌍 UI-Sprache"},
    "♟️ Język Debiutów": {"en": "♟️ Openings Language", "de": "♟️ Eröffnungssprache"},
    "🎨 Motyw": {"en": "🎨 Theme", "de": "🎨 Design"},
    "Zasięg:": {"en": "Scope:", "de": "Umfang:"},
    "Jeden profil": {"en": "Single profile", "de": "Ein Profil"},
    "Połącz profile (C+L)": {"en": "Merge profiles (C+L)", "de": "Profile verbinden (C+L)"},
    "Porównanie graczy (start)": {"en": "Player comparison (start)", "de": "Spielervergleich (Start)"},
    "Pobieranie...": {"en": "Downloading...", "de": "Laden..."},
    "Łączenie...": {"en": "Merging...", "de": "Zusammenführen..."},
    "Widok:": {"en": "View:", "de": "Ansicht:"},
    "🔍 Filtry": {"en": "🔍 Filters", "de": "🔍 Filter"},
    "Zakres dat:": {"en": "Date range:", "de": "Datumsbereich:"},
    "Tryb:": {"en": "Mode:", "de": "Modus:"},
    "Godziny:": {"en": "Hours:", "de": "Stunden:"},
    "Dzień do analizy:": {"en": "Day to analyze:", "de": "Tag für Analyse:"},
    "Nick rywala (opcjonalnie):": {"en": "Opponent nickname (optional):", "de": "Gegnername (optional):"},
    "Grupa debiutu:": {"en": "Opening group:", "de": "Eröffnungsgruppe:"},
    "Wszystkie": {"en": "All", "de": "Alle"},
    "Mecz:": {"en": "Game:", "de": "Partie:"},
    "Mecz do tablicy:": {"en": "Game for board:", "de": "Partie fürs Brett:"},
    "Uruchom porównanie": {"en": "Start comparison", "de": "Vergleich starten"},
    "Pobieranie i porównywanie...": {"en": "Downloading and comparing...", "de": "Laden und vergleichen..."},
    "Przesyłanie PGN do analizy...": {"en": "Uploading PGN for analysis...", "de": "PGN zur Analyse wird hochgeladen..."},
    "Przygotowanie interaktywnej analizy...": {"en": "Preparing interactive analysis...", "de": "Interaktive Analyse wird vorbereitet..."},
    "Brak partii do analizy.": {"en": "No games for analysis.", "de": "Keine Partien zur Analyse."},
    "⚔️ Porównanie Graczy": {"en": "⚔️ Player Comparison", "de": "⚔️ Spielervergleich"},
    "👤 Moja Analiza": {"en": "👤 My Analysis", "de": "👤 Meine Analyse"},
}

def t(key, default=""):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return ui_dict.get(key, {}).get(l, default if default else key)

def tu(text):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return ui_phrases.get(text, {}).get(l, text)

def t_reason(reason):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return reason_dict.get(reason.lower(), {}).get(l, reason.capitalize())

def t_op(eng_name):
    if eng_name == "Brak" or not eng_name: return "Brak"
    l = lang_map.get(st.session_state.op_lang, "pl")
    if l == "en": return eng_name
    return op_translations.get(eng_name, {}).get(l, eng_name)

def format_bytes(size):
    value = float(max(size or 0, 0))
    units = ["B", "KB", "MB", "GB"]
    unit_idx = 0
    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024
        unit_idx += 1
    return f"{value:.1f} {units[unit_idx]}"

def parse_san_moves_from_pgn(pgn_text, max_plies=12):
    if not isinstance(pgn_text, str) or not pgn_text.strip():
        return []
    txt = re.sub(r'\[[^\]]*\]', ' ', pgn_text)
    txt = re.sub(r'\{[^}]*\}', ' ', txt)
    txt = re.sub(r'\([^)]*\)', ' ', txt)
    tokens = txt.replace('\n', ' ').split()
    result_tokens = {"1-0", "0-1", "1/2-1/2", "*"}
    moves = []
    for tok in tokens:
        clean = tok.strip()
        if not clean or clean in result_tokens:
            continue
        if re.match(r'^\d+\.+$', clean):
            continue
        if '.' in clean and re.match(r'^\d+\.+', clean):
            clean = clean.split('.')[-1].strip()
            if not clean:
                continue
        clean = re.sub(r'[!?+#]+', '', clean).strip()
        if not clean or clean in result_tokens:
            continue
        moves.append(clean)
        if len(moves) >= max_plies:
            break
    return moves

def build_opening_training_tree(df, max_openings=4, max_lines_per_opening=4, max_plies=12):
    fallback = {
        "name": "Caro-Kann Defense",
        "variants": [
            {"name": "Advance", "line": ["e4", "c6", "d4", "d5", "e5", "Bf5", "Nf3", "e6", "Be2", "c5"]},
            {"name": "Exchange", "line": ["e4", "c6", "d4", "d5", "exd5", "cxd5", "Bd3", "Nc6", "c3", "Nf6"]},
            {"name": "Classical", "line": ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6"]},
        ],
    }
    if df is None or df.empty:
        return fallback
    req_cols = {"PGN_Raw", "Debiut_Grupa", "Kolor"}
    if not req_cols.issubset(df.columns):
        return fallback
    white_games = df[(df["Kolor"] == "Białe") & df["PGN_Raw"].notna()]
    if white_games.empty:
        return fallback
    grouped_lines = {}
    for _, row in white_games.iterrows():
        opening = str(row.get("Debiut_Grupa") or row.get("Debiut") or "Nieznany").strip()
        moves = parse_san_moves_from_pgn(row.get("PGN_Raw", ""), max_plies=max_plies)
        if len(moves) < 4:
            continue
        opening_map = grouped_lines.setdefault(opening, {})
        key = tuple(moves[:max_plies])
        opening_map[key] = opening_map.get(key, 0) + 1
    if not grouped_lines:
        return fallback
    top_openings = sorted(
        grouped_lines.items(),
        key=lambda item: sum(item[1].values()),
        reverse=True
    )[:max_openings]
    variants = []
    for opening_name, lines_map in top_openings:
        top_lines = sorted(lines_map.items(), key=lambda item: item[1], reverse=True)[:max_lines_per_opening]
        for idx, (line_moves, freq) in enumerate(top_lines, start=1):
            variants.append({
                "name": f"{opening_name} #{idx} ({freq} gier)",
                "line": list(line_moves)
            })
    return {"name": "Najczęstsze debiuty gracza", "variants": variants} if variants else fallback

def render_training_component(mode_name, learning_mode, difficulty, opening_tree, player_color):
    cfg = {
        "mode": mode_name,
        "learningMode": learning_mode,
        "difficulty": difficulty,
        "tree": opening_tree,
        "playerColor": player_color,
        "theme": {
            "bg": bg_color,
            "card": chart_bg,
            "text": font_color,
            "accent": cw
        }
    }
    html = """
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/chessboard.js/1.0.0/chessboard-1.0.0.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/chessboard.js/1.0.0/chessboard-1.0.0.min.js"></script>
    <div id="coach-wrap">
        <div id="coach-top">
            <div id="coach-status">Ładowanie modułu...</div>
            <button id="next-line">Następna linia</button>
        </div>
        <div id="board" style="width: 100%; max-width: 660px; margin: 0 auto;"></div>
        <div id="move-score"></div>
    </div>
    <style>
        body { margin: 0; padding: 0; background: transparent; font-family: Inter, sans-serif; }
        #coach-wrap {
            background: __THEME_BG__;
            color: __THEME_TEXT__;
            border: 1px solid rgba(127,127,127,.25);
            border-radius: 12px;
            padding: 12px;
        }
        #coach-top {
            display: flex;
            gap: 8px;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        #coach-status {
            font-weight: 700;
            font-size: 16px;
            color: __THEME_TEXT__;
        }
        #next-line {
            border: 0;
            border-radius: 8px;
            padding: 8px 10px;
            background: __THEME_ACCENT__;
            color: #fff;
            font-weight: 700;
            cursor: pointer;
        }
        #move-score {
            margin-top: 12px;
            min-height: 48px;
            text-align: center;
            font-size: 30px;
            font-weight: 900;
            letter-spacing: .2px;
        }
    </style>
    <script>
        const APP_CONFIG = __APP_CONFIG__;
        const game = new Chess();
        const statusBox = document.getElementById("coach-status");
        const scoreBox = document.getElementById("move-score");
        const nextBtn = document.getElementById("next-line");
        const difficultyMap = {
            "Łatwy": { skill: 4, depth: 8, evalDepth: 10 },
            "Średni": { skill: 12, depth: 12, evalDepth: 12 },
            "Trudny": { skill: 20, depth: 16, evalDepth: 13 }
        };
        const modeOpening = APP_CONFIG.mode === "Trening Debiutów";
        const tree = APP_CONFIG.tree || { variants: [] };
        const variants = tree.variants || [];
        const userTurn = (APP_CONFIG.playerColor === "black") ? "b" : "w";
        const botTurn = userTurn === "w" ? "b" : "w";
        let variantIndex = 0;
        let currentVariant = null;
        let currentPly = 0;
        let board = null;
        const engine = new Worker("https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js");

        const normalizeSan = (san) => (san || "").replace(/[+#?!]/g, "").trim();
        const buildMove = (from, to, promotionHint = null) => {
            const move = { from, to };
            const piece = game.get(from);
            if (promotionHint) move.promotion = promotionHint;
            if (!promotionHint && piece && piece.type === "p" && (to.endsWith("8") || to.endsWith("1"))) {
                move.promotion = "q";
            }
            return move;
        };
        const uciToMove = (uci) => buildMove(uci.slice(0, 2), uci.slice(2, 4), uci[4] || null);
        const scoreToCp = (scoreObj, turn) => {
            if (!scoreObj) return 0;
            if (scoreObj.type === "mate") {
                const base = scoreObj.value > 0 ? 10000 : -10000;
                return turn === "w" ? base : -base;
            }
            return turn === "w" ? scoreObj.value : -scoreObj.value;
        };

        function setStatus(text) { statusBox.textContent = text; }
        function setMoveScore(text, color) {
            scoreBox.textContent = text || "";
            scoreBox.style.color = color || APP_CONFIG.theme.accent;
        }

        function getDifficulty() {
            return difficultyMap[APP_CONFIG.difficulty] || difficultyMap["Średni"];
        }

        function chooseVariant() {
            if (!variants.length) return null;
            if (APP_CONFIG.learningMode === "Losowo") {
                return variants[Math.floor(Math.random() * variants.length)];
            }
            const selected = variants[variantIndex % variants.length];
            variantIndex += 1;
            return selected;
        }

        function resetOpening() {
            game.reset();
            currentPly = 0;
            currentVariant = chooseVariant();
            board.position(game.fen());
            setMoveScore("", APP_CONFIG.theme.accent);
            if (!currentVariant) {
                setStatus("Brak wariantów debiutowych do treningu.");
                return;
            }
            const expected = currentVariant.line?.[currentPly] || "-";
            setStatus(`Wariant: ${currentVariant.name} | Oczekiwany ruch: ${expected}`);
        }

        function classifyMove(delta) {
            if (delta < 25) return { text: "Excellent", color: "#81b64c" };
            if (delta < 75) return { text: "Good", color: "#5ab4ac" };
            if (delta < 150) return { text: "Inaccuracy", color: "#d8b365" };
            if (delta < 300) return { text: "Mistake", color: "#ef553b" };
            return { text: "Blunder", color: "#fa412d" };
        }

        function askEngine(positionFen, goCmd) {
            return new Promise((resolve) => {
                let lastScore = null;
                const handler = (event) => {
                    const line = (event.data || "").trim();
                    const cp = line.match(/score cp (-?[0-9]+)/);
                    const mate = line.match(/score mate (-?[0-9]+)/);
                    if (cp) lastScore = { type: "cp", value: parseInt(cp[1], 10) };
                    if (mate) lastScore = { type: "mate", value: parseInt(mate[1], 10) };
                    if (line.startsWith("bestmove")) {
                        engine.removeEventListener("message", handler);
                        resolve({ line, score: lastScore });
                    }
                };
                engine.addEventListener("message", handler);
                engine.postMessage(`position fen ${positionFen}`);
                engine.postMessage(goCmd);
            });
        }

        async function evaluatePosition(fen, depth) {
            const turn = fen.split(" ")[1] || "w";
            const out = await askEngine(fen, `go depth ${depth}`);
            return scoreToCp(out.score, turn);
        }

        async function getBestMove(fen, depth) {
            const out = await askEngine(fen, `go depth ${depth}`);
            return (out.line.split(" ")[1] || "").trim();
        }

        async function playBotMove() {
            if (game.turn() !== botTurn) return;
            const d = getDifficulty();
            engine.postMessage(`setoption name Skill Level value ${d.skill}`);
            const best = await getBestMove(game.fen(), d.depth);
            if (!best || best === "(none)") return;
            game.move(uciToMove(best));
            board.position(game.fen());
            setStatus("Bot wykonał ruch. Twój ruch.");
        }

        async function handleBotTurn(beforeFen) {
            const d = getDifficulty();
            const movedColor = (beforeFen.split(" ")[1] || "w");
            const evalBefore = await evaluatePosition(beforeFen, d.evalDepth);
            const evalAfter = await evaluatePosition(game.fen(), d.evalDepth);
            const rawDelta = movedColor === "w" ? (evalBefore - evalAfter) : (evalAfter - evalBefore);
            const delta = Math.max(0, Math.round(rawDelta));
            const bucket = classifyMove(delta);
            setMoveScore(`${bucket.text} | Δ ${delta} cp`, bucket.color);
            if (!game.game_over() && game.turn() === botTurn) await playBotMove();
        }

        function onDrop(source, target) {
            if (modeOpening) {
                if (!currentVariant) return "snapback";
                const expected = currentVariant.line?.[currentPly];
                if (!expected || game.turn() !== "w") return "snapback";
                const move = game.move(buildMove(source, target));
                if (!move) return "snapback";
                if (normalizeSan(move.san) !== normalizeSan(expected)) {
                    game.undo();
                    setStatus(`Wariant: ${currentVariant.name} | Zły ruch dla tego debiutu, spróbuj ponownie.`);
                    return "snapback";
                }
                currentPly += 1;
                board.position(game.fen());
                const reply = currentVariant.line?.[currentPly];
                if (reply) {
                    setTimeout(() => {
                        game.move(reply);
                        currentPly += 1;
                        board.position(game.fen());
                        const nextExpected = currentVariant.line?.[currentPly];
                        if (nextExpected) {
                            setStatus(`Wariant: ${currentVariant.name} | Oczekiwany ruch: ${nextExpected}`);
                        } else {
                            setStatus(`Wariant: ${currentVariant.name} ukończony.`);
                        }
                    }, 280);
                } else {
                    setStatus(`Wariant: ${currentVariant.name} ukończony.`);
                }
                return;
            }

            if (game.turn() !== userTurn) return "snapback";
            const beforeFen = game.fen();
            const move = game.move(buildMove(source, target));
            if (!move) return "snapback";
            board.position(game.fen());
            handleBotTurn(beforeFen);
        }

        board = Chessboard("board", {
            draggable: true,
            position: "start",
            orientation: userTurn === "w" ? "white" : "black",
            pieceTheme: "https://cdnjs.cloudflare.com/ajax/libs/chessboard.js/1.0.0/img/chesspieces/wikipedia/{piece}.png",
            onDrop
        });

        engine.postMessage("uci");
        engine.postMessage("isready");
        nextBtn.onclick = () => {
            if (modeOpening) {
                resetOpening();
            } else {
                game.reset();
                board.position(game.fen());
                setMoveScore("", APP_CONFIG.theme.accent);
                if (userTurn === "w") {
                    setStatus("Nowa partia z botem. Twój ruch białymi.");
                } else {
                    setStatus("Nowa partia z botem. Bot rozpoczyna.");
                    setTimeout(() => playBotMove(), 280);
                }
            }
        };

        if (modeOpening) {
            resetOpening();
        } else {
            if (userTurn === "w") {
                setStatus("Tryb sparingu z botem. Twój ruch białymi.");
            } else {
                setStatus("Tryb sparingu z botem. Bot rozpoczyna.");
                setTimeout(() => playBotMove(), 280);
            }
        }
        window.addEventListener("beforeunload", () => engine.terminate());
    </script>
    """
    html = html.replace("__APP_CONFIG__", json.dumps(cfg, ensure_ascii=False))
    html = html.replace("__THEME_BG__", cfg["theme"]["card"])
    html = html.replace("__THEME_TEXT__", cfg["theme"]["text"])
    html = html.replace("__THEME_ACCENT__", cfg["theme"]["accent"])
    components.html(html, height=860, scrolling=False)

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

css_morski = """
    .stApp {
        background-color: #0d1b2a;
        background-image: linear-gradient(160deg, #0d1b2a 0%, #1b2e45 100%);
        background-attachment: fixed;
        color: #caf0f8;
    }
    [data-testid="stHeader"] { background-color: rgba(0, 0, 0, 0); }
    .stMetric, div.row-widget.stRadio > div {
        background-color: #1b2838;
        border: 1px solid #2a3a4a;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    }
    [data-testid="stMetricValue"], [data-testid="stMarkdownContainer"] p, h1, h2, h3, h4, h5 {
        color: #caf0f8 !important;
    }
    [data-testid="stMetricLabel"] { color: #90e0ef !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; }
    .stTabs [data-baseweb="tab-list"] button { color: #486a7a; font-weight: 600; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #00b4d8; border-bottom: 3px solid #00b4d8; }
    .stButton>button[kind="primary"] {
        background-color: #00b4d8;
        color: #0d1b2a;
        border: none;
        border-bottom: 4px solid #0077b6;
        border-radius: 6px;
        font-weight: bold;
        font-size: 1.05rem;
        transition: all 0.1s;
    }
    .stButton>button[kind="primary"]:active { border-bottom: 0px; transform: translateY(4px); }
    .stButton>button[kind="secondary"] {
        background-color: #1b2838;
        color: #90e0ef;
        border: 1px solid #2a3a4a;
        border-radius: 6px;
    }
"""

active_css = css_dark
if st.session_state.theme == "Jasny": active_css = css_light
elif st.session_state.theme == "Chess.com": active_css = css_chesscom
elif st.session_state.theme == "Neon Retro": active_css = css_neon
elif st.session_state.theme == "Morski": active_css = css_morski

st.markdown(f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    [data-testid="stMetricValue"] {{ font-size: 1.1rem !important; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.8rem !important; text-transform: uppercase; }}
    .stMetric {{ padding: 12px; }}
    .block-container {{ padding: 1rem; top: 1rem; }}
    div[data-testid="stExpander"] details {{ padding-bottom: 0 !important; margin-bottom: 0 !important; }}
    
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
    if not match: return "Inny"
    slug = match.group(1)
    # Chess.com URLs encode apostrophes as hyphens (e.g., King-s-Pawn → King's-Pawn)
    slug = re.sub(r'(?<=[A-Za-z])-s(?=-[A-Z]|-$)', "'s", slug)
    result = slug.replace('-', ' ').title()
    # Fix title() incorrectly capitalizing the 's in possessives (King'S → King's)
    return re.sub(r"(?<=[A-Za-z])'S\b", "'s", result)

def extract_moves_count(pgn):
    if not pgn: return 0
    matches = re.findall(r'(\d+)\.', pgn)
    return int(matches[-1]) if matches else 0

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

def extract_move_times_from_pgn(pgn, is_white):
    if not pgn:
        return []
    clocks = re.findall(r'\[%clk ([0-9:\.]+)\]', pgn)
    if not clocks:
        return []
    try:
        sec = [_clock_to_seconds(c) for c in clocks]
    except Exception:
        return []
    my_idx = list(range(0 if is_white else 1, len(sec), 2))
    my_clocks = [sec[i] for i in my_idx]
    if len(my_clocks) < 2:
        return []
    deltas = []
    for i in range(1, len(my_clocks)):
        d = my_clocks[i - 1] - my_clocks[i]
        if 0 <= d <= MAX_MOVE_TIME_SECONDS:
            deltas.append(round(d, 2))
    return deltas

def extract_move_times_from_lichess_clocks(clocks, is_white):
    if not clocks or len(clocks) < 4:
        return []
    my_idx = list(range(0 if is_white else 1, len(clocks), 2))
    my_clocks = [float(clocks[i]) / 100 for i in my_idx]
    deltas = []
    for i in range(1, len(my_clocks)):
        d = my_clocks[i - 1] - my_clocks[i]
        if 0 <= d <= MAX_MOVE_TIME_SECONDS:
            deltas.append(round(d, 2))
    return deltas

def build_move_pace_table(df):
    labels = ["0-10"] + [f"{i*10+1}-{(i+1)*10}" for i in range(1, NUM_DECILES)]
    buckets = {label: [] for label in labels}
    has_data = False
    for arr in df["MoveTimes"]:
        vals = arr if isinstance(arr, list) else []
        if len(vals) < 2:
            continue
        has_data = True
        n = len(vals)
        for i, v in enumerate(vals):
            bucket_idx = min(int((i / n) * NUM_DECILES), NUM_DECILES - 1)
            buckets[labels[bucket_idx]].append(v)
    if not has_data:
        return pd.DataFrame(columns=["Segment", "AvgSec", "Moves"])
    rows = []
    for label in labels:
        data = buckets[label]
        rows.append({
            "Segment": label,
            "AvgSec": round(sum(data) / len(data), 2) if data else None,
            "Moves": len(data),
        })
    return pd.DataFrame(rows)

def build_report_summary(df):
    total_games = len(df)
    w = int((df["Wynik"] == "Wygrane").sum())
    d = int((df["Wynik"] == "Remisy").sum())
    l = int((df["Wynik"] == "Przegrane").sum())
    winp = round((w / total_games) * 100, 1) if total_games else 0.0
    date_from = df["Data"].min() if total_games else "-"
    date_to = df["Data"].max() if total_games else "-"
    mode_stats = (
        df.groupby("Tryb")
        .agg(
            Partie=("Wynik", "count"),
            Wygrane=("Wynik", lambda x: int((x == "Wygrane").sum())),
        )
        .reset_index()
        .sort_values("Partie", ascending=False)
    )
    if not mode_stats.empty:
        mode_stats["Win%"] = (mode_stats["Wygrane"] / mode_stats["Partie"] * 100).round(1)
    color_stats = (
        df.groupby("Kolor")
        .agg(
            Partie=("Wynik", "count"),
            Wygrane=("Wynik", lambda x: int((x == "Wygrane").sum())),
            Remisy=("Wynik", lambda x: int((x == "Remisy").sum())),
            Przegrane=("Wynik", lambda x: int((x == "Przegrane").sum())),
        )
        .reset_index()
        .sort_values("Partie", ascending=False)
    )
    if not color_stats.empty:
        color_stats["Win%"] = (color_stats["Wygrane"] / color_stats["Partie"] * 100).round(1)
    opening_stats = (
        df.groupby("Debiut_Grupa")
        .agg(
            Partie=("Wynik", "count"),
            Wygrane=("Wynik", lambda x: int((x == "Wygrane").sum())),
        )
        .reset_index()
        .sort_values("Partie", ascending=False)
        .head(10)
    )
    if not opening_stats.empty:
        opening_stats["Win%"] = (opening_stats["Wygrane"] / opening_stats["Partie"] * 100).round(1)
    reason_stats = (
        df.groupby("Powod")
        .agg(Partie=("Powod", "count"))
        .reset_index()
        .sort_values("Partie", ascending=False)
        .head(10)
    )
    return {
        "total_games": total_games,
        "w": w,
        "d": d,
        "l": l,
        "winp": winp,
        "date_from": date_from,
        "date_to": date_to,
        "mode_stats": mode_stats,
        "color_stats": color_stats,
        "opening_stats": opening_stats,
        "reason_stats": reason_stats,
        "pace_df": build_move_pace_table(df),
    }

def build_html_report(df, username):
    summary = build_report_summary(df)
    mode_html = summary["mode_stats"].fillna("-").to_html(index=False)
    color_html = summary["color_stats"].fillna("-").to_html(index=False)
    opening_html = summary["opening_stats"].fillna("-").to_html(index=False)
    reason_html = summary["reason_stats"].fillna("-").to_html(index=False)
    pace_html = summary["pace_df"].fillna("-").to_html(index=False)
    return f"""
    <html><head><meta charset='utf-8'>
    <style>
      body {{ font-family: Inter, Arial, sans-serif; background:#14181f; color:#e5e7eb; padding:28px; }}
      .hero {{ background: linear-gradient(135deg,#1f2937,#111827); border-radius:16px; padding:18px 20px; margin-bottom:16px; border:1px solid #374151; }}
      .kpi {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }}
      .chip {{ background:#1f2937; border:1px solid #374151; border-radius:999px; padding:6px 12px; font-size:13px; }}
      .card {{ background:#1f2937; border-radius:12px; padding:14px; margin-bottom:14px; border:1px solid #374151; }}
      h1 {{ color:#81b64c; margin:0 0 6px; }}
      h3 {{ margin:0 0 10px; color:#f3f4f6; }}
      table {{ border-collapse: collapse; width: 100%; background:#1f2937; }}
      th, td {{ border:1px solid #374151; padding:8px; text-align:center; }}
      th {{ background:#111827; }}
    </style></head><body>
      <div class='hero'>
        <h1>ChessStats — {username}</h1>
        <div>Zakres: {summary["date_from"]} ➜ {summary["date_to"]}</div>
        <div class='kpi'>
          <div class='chip'><b>Partie:</b> {summary["total_games"]}</div>
          <div class='chip'><b>W/R/P:</b> {summary["w"]}/{summary["d"]}/{summary["l"]}</div>
          <div class='chip'><b>Win%:</b> {summary["winp"]}%</div>
        </div>
      </div>
      <div class='card'><h3>Tryby gry</h3>{mode_html}</div>
      <div class='card'><h3>Wyniki wg koloru</h3>{color_html}</div>
      <div class='card'><h3>Najważniejsze debiuty</h3>{opening_html}</div>
      <div class='card'><h3>Najczęstsze zakończenia partii</h3>{reason_html}</div>
      <div class='card'><h3>Tempo ruchu (segmenty partii)</h3>{pace_html}</div>
    </body></html>
    """

def build_pdf_report(df, username):
    summary = build_report_summary(df)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
        title=f"ChessStats {username}",
    )
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"<b>ChessStats — {username}</b>", styles["Title"]))
    story.append(Paragraph(f"Zakres: {summary['date_from']} - {summary['date_to']}", styles["Normal"]))
    story.append(Spacer(1, 10))
    kpi_rows = [
        ["Partie", "W/R/P", "Win%"],
        [str(summary["total_games"]), f"{summary['w']}/{summary['d']}/{summary['l']}", f"{summary['winp']}%"],
    ]
    kpi_table = Table(kpi_rows)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    def add_df_table(title, frame):
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading3"]))
        if frame.empty:
            story.append(Paragraph("Brak danych", styles["Normal"]))
            story.append(Spacer(1, 8))
            return
        data = [list(frame.columns)] + frame.astype(str).values.tolist()
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.8),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))

    add_df_table("Tryby gry", summary["mode_stats"])
    add_df_table("Wyniki wg koloru", summary["color_stats"])
    add_df_table("Najważniejsze debiuty", summary["opening_stats"])
    add_df_table("Najczęstsze zakończenia partii", summary["reason_stats"])
    add_df_table("Tempo ruchu (segmenty partii)", summary["pace_df"])

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

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
    except Exception:
        return None

def to_lichess_analysis_url(url):
    if not isinstance(url, str):
        return None
    base = url.strip()
    if not base:
        return None
    if "lichess.org" not in base:
        return base
    base = base.split("?")[0].rstrip("/")
    return base if base.endswith("/analysis") else f"{base}/analysis"

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

def _stream_get_text(url, headers=None, timeout=API_TIMEOUT, progress_cb=None, label=""):
    res = requests.get(url, headers=headers or {}, timeout=timeout, stream=True)
    total = int(res.headers.get("Content-Length", "0") or 0)
    if progress_cb:
        progress_cb(0, total, label, True)
    chunks = []
    for chunk in res.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)
        if progress_cb:
            progress_cb(len(chunk), total, label, False)
    content = b"".join(chunks).decode("utf-8", errors="replace")
    return res.status_code, content

def fetch_data_live(user, platform="Chess.com", progress_callback=None):
    cols = ["Konto", "Platforma", "Timestamp", "Godzina", "Dzień", "Dzień_Nr", "Data", "Miesiąc", "Tryb", "Wynik", "ELO", "Elo_Rywala", "Ruchy", "Debiut", "Debiut_Grupa", "Przeciwnik", "Kolor", "Powod", "PGN_Raw", "Link", "MoveTimes"]
    try:
        headers = {"User-Agent": f"AnalizySzachowe-V30-{user}"}
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        all_games = []
        k_id = f"{user} ({'C' if platform == 'Chess.com' else 'L'})"
        progress_state = {"downloaded": 0, "known_total": 0}

        def push_progress(delta, total, label, is_start):
            if is_start and total > 0:
                progress_state["known_total"] += total
            if not is_start and delta > 0:
                progress_state["downloaded"] += delta
            if progress_callback:
                progress_callback(progress_state["downloaded"], progress_state["known_total"], label)
        
        if platform == "Chess.com":
            p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers, timeout=API_TIMEOUT)
            a_code, a_text = _stream_get_text(
                f"https://api.chess.com/pub/player/{user}/games/archives",
                headers=headers,
                timeout=API_TIMEOUT,
                progress_cb=push_progress,
                label=f"{platform}: lista archiwów"
            )
            if p_res.status_code != 200: return None, pd.DataFrame(columns=cols)
            if a_code != 200: return None, pd.DataFrame(columns=cols)
            archives = json.loads(a_text).get("archives", [])
            for idx, url in enumerate(archives, start=1):
                try:
                    m_code, m_text = _stream_get_text(
                        url,
                        headers=headers,
                        timeout=API_TIMEOUT,
                        progress_cb=push_progress,
                        label=f"{platform}: archiwum {idx}/{len(archives)}"
                    )
                    if m_code == 200:
                        month_games = json.loads(m_text).get("games", [])
                        for g in month_games:
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
                                    "Kolor": "Białe" if is_w else "Czarne", "Powod": my_r if out=="Przegrane" else opp_r, "PGN_Raw": pgn, "Link": "",
                                    "MoveTimes": extract_move_times_from_pgn(pgn, is_w)
                                })
                except Exception:
                    continue 
            return {"avatar": p_res.json().get("avatar", "")}, pd.DataFrame(all_games, columns=cols) if all_games else pd.DataFrame(columns=cols)
            
        elif platform == "Lichess":
            p_res = requests.get(f"https://lichess.org/api/user/{user}", headers=headers, timeout=API_TIMEOUT)
            if p_res.status_code != 200: return None, pd.DataFrame(columns=cols)
            g_code, g_text = _stream_get_text(
                f"https://lichess.org/api/games/user/{user}?opening=true&clocks=true",
                headers={"Accept": "application/x-ndjson"},
                timeout=60,
                progress_cb=push_progress,
                label=f"{platform}: gry użytkownika"
            )
            if g_code != 200:
                return None, pd.DataFrame(columns=cols)
            for line in g_text.strip().split('\n'):
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
                        "Powod": g.get("status"), "PGN_Raw": g.get("moves", ""), "Link": f"https://lichess.org/{g['id']}",
                        "MoveTimes": extract_move_times_from_lichess_clocks(g.get("clocks", []), my_col == "white")
                    })
                except Exception:
                    continue
            return {"avatar": p_res.json().get("profile", {}).get("avatar", "")}, pd.DataFrame(all_games, columns=cols) if all_games else pd.DataFrame(columns=cols)
    except Exception:
        return None, pd.DataFrame(columns=cols)

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user, platform="Chess.com"):
    return fetch_data_live(user, platform, progress_callback=None)

def run_fetch_with_progress(user, platform):
    progress_bar = st.progress(0, text=f"Pobieranie {user} ({platform})...")
    status_box = st.empty()
    started = datetime.now().timestamp()

    def on_progress(downloaded, known_total, label):
        elapsed = max(datetime.now().timestamp() - started, 0.1)
        speed = downloaded / elapsed
        eta = (known_total - downloaded) / speed if known_total > downloaded and speed > 1 else None
        ratio = int(min(100, (downloaded / known_total) * 100)) if known_total > 0 else 0
        eta_text = f" | ETA: {int(eta)}s" if eta is not None else ""
        text = f"{label} | {format_bytes(downloaded)}"
        if known_total > 0:
            text += f" / {format_bytes(known_total)}"
        text += eta_text
        progress_bar.progress(ratio, text=text)
        status_box.caption(text)

    out = fetch_data_live(user, platform, progress_callback=on_progress)
    progress_bar.empty()
    status_box.empty()
    return out

# --- SESSION & START ---
for k in ['data','data2','url', 'user', 'user2', 'plat2']: 
    if k not in st.session_state: st.session_state[k] = None if k in ['data','data2','url'] else ""
if 'platforms' not in st.session_state: st.session_state.platforms = []

if st.session_state.data is None:
    c_l1, c_l2 = st.columns([7, 3])
    c_l1.title(f"♟️ {t('title')}")
    with c_l2.expander(tu("⚙️ Ustawienia")):
        st.selectbox(tu("🌍 Język UI"), ["Polski", "English", "Deutsch"], key="ui_lang")
        st.selectbox(tu("♟️ Język Debiutów"), ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio(tu("🎨 Motyw"), ["Chess.com", "Neon Retro", "Morski", "Ciemny", "Jasny"], key="theme", horizontal=True)

    scope_options = [SCOPE_SINGLE, SCOPE_MERGE, SCOPE_COMPARE]
    log_m = st.radio(tu("Zasięg:"), scope_options, horizontal=True, format_func=tu)
    if log_m == SCOPE_SINGLE:
        c1, c2 = st.columns([1, 4])
        plat = c1.selectbox("Plat:", ["Chess.com", "Lichess"])
        nick = c2.text_input("Nick:")
        if st.button(t("btn_analize"), type="primary", use_container_width=True):
            if nick:
                with st.spinner(tu("Pobieranie...")):
                    f = run_fetch_with_progress(nick, plat)
                    if f[0] is not None and not f[1].empty: 
                        st.session_state.data, st.session_state.user, st.session_state.platforms = f, nick, [plat]
                        st.session_state.fetch_args = [(nick, plat)]
                        st.rerun()
                    else: st.error("Nie znaleziono partii dla tego gracza.")
    elif log_m == SCOPE_MERGE:
        c1, c2 = st.columns(2)
        p1, n1 = c1.selectbox("P1:", ["Chess.com", "Lichess"]), c1.text_input("Nick 1:")
        p2, n2 = c2.selectbox("P2:", ["Lichess", "Chess.com"]), c2.text_input("Nick 2:")
        if st.button(t("btn_connect"), type="primary", use_container_width=True):
            if n1 and n2:
                with st.spinner(tu("Łączenie...")):
                    f1, f2 = run_fetch_with_progress(n1, p1), run_fetch_with_progress(n2, p2)
                    if f1[0] is not None and not f1[1].empty and f2[0] is not None and not f2[1].empty:
                        st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                        st.session_state.user, st.session_state.platforms = f"{n1}+{n2}", list(set([p1, p2]))
                        st.session_state.fetch_args = [(n1, p1), (n2, p2)]
                        st.session_state.default_view = VIEW_MY
                        st.rerun()
                    else: st.error("Błąd pobierania danych. Upewnij się, że oba konta posiadają historię gier.")
    else:
        c1, c2 = st.columns(2)
        p1 = c1.selectbox("Platforma gracza 1:", ["Chess.com", "Lichess"], key="q_p1")
        n1 = c1.text_input("Nick gracza 1:", key="q_n1")
        p2 = c2.selectbox("Platforma gracza 2:", ["Chess.com", "Lichess"], key="q_p2")
        n2 = c2.text_input("Nick gracza 2:", key="q_n2")
        if st.button(tu("Uruchom porównanie"), type="primary", use_container_width=True):
            if n1 and n2:
                with st.spinner(tu("Pobieranie i porównywanie...")):
                    f1, f2 = run_fetch_with_progress(n1, p1), run_fetch_with_progress(n2, p2)
                    if f1[0] is not None and not f1[1].empty and f2[0] is not None and not f2[1].empty:
                        st.session_state.data = f1
                        st.session_state.user = n1
                        st.session_state.platforms = [p1]
                        st.session_state.fetch_args = [(n1, p1)]
                        st.session_state.data2 = f2[1]
                        st.session_state.user2 = n2
                        st.session_state.plat2 = p2
                        st.session_state.default_view = VIEW_COMPARE
                        st.rerun()
                    else:
                        st.error("Nie udało się pobrać danych dla obu graczy.")
else:
    profile, df_raw = st.session_state.data
    df_loc = df_raw.copy()
    if "MoveTimes" not in df_loc.columns:
        df_loc["MoveTimes"] = [[] for _ in range(len(df_loc))]
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
    
    with st.expander(tu("⚙️ Ustawienia")):
        app_options = [VIEW_MY, VIEW_COMPARE]
        default_view = st.session_state.get("default_view", VIEW_MY)
        default_idx = app_options.index(default_view) if default_view in app_options else 0
        app_m = st.radio(tu("Widok:"), app_options, label_visibility="collapsed", horizontal=True, index=default_idx, format_func=tu)
        st.session_state.default_view = app_m
        c_l_ui, c_l_op = st.columns(2)
        c_l_ui.selectbox(tu("🌍 Język UI"), ["Polski", "English", "Deutsch"], key="ui_lang")
        c_l_op.selectbox(tu("♟️ Język Debiutów"), ["Polski", "English", "Deutsch"], key="op_lang")
        st.radio(tu("🎨 Motyw"), ["Chess.com", "Neon Retro", "Morski", "Ciemny", "Jasny"], key="theme", horizontal=True)

        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button(t("btn_refresh"), use_container_width=True):
                with st.spinner("Pobieranie najnowszych partii w tle..."):
                    fetch_data.clear() # czyści cache dla API
                    args = st.session_state.get('fetch_args', [])
                    if len(args) == 1:
                        f = run_fetch_with_progress(args[0][0], args[0][1])
                        if f[0] is not None and not f[1].empty:
                            st.session_state.data = f
                    elif len(args) == 2:
                        f1 = run_fetch_with_progress(args[0][0], args[0][1])
                        f2 = run_fetch_with_progress(args[1][0], args[1][1])
                        if f1[0] is not None and not f1[1].empty and f2[0] is not None and not f2[1].empty:
                            st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                    
                    if st.session_state.data2 is not None and st.session_state.user2 and st.session_state.plat2:
                        f2_rival = run_fetch_with_progress(st.session_state.user2, st.session_state.plat2)
                        if f2_rival[0] is not None and not f2_rival[1].empty:
                            st.session_state.data2 = f2_rival[1]
                st.rerun()
                
        with c_btn2:
            if st.button(t("btn_change"), type="primary", use_container_width=True):
                for k in ['data','data2','url','user','user2','plat2']: st.session_state[k] = None if k in ['data','data2','url'] else ""
                st.session_state.platforms = []
                st.session_state.fetch_args = []
                st.session_state.default_view = VIEW_MY
                st.rerun()

    if app_m == VIEW_MY:
        m1, m2, m3 = st.columns(3)
        p_r, c_r, _ = calc_elo(df_loc, "Rapid")
        p_b, c_b, _ = calc_elo(df_loc, "Blitz")
        p_bl, c_bl, _ = calc_elo(df_loc, "Bullet")
        m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
        m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
        m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")

        with st.expander(tu("🔍 Filtry")):
            f1, f2 = st.columns(2)
            d_r = f1.date_input(tu("Zakres dat:"), value=(df_loc["Data"].min(), df_loc["Data"].max()))
            s_m = f2.selectbox(tu("Tryb:"), [tu("Wszystkie")] + sorted(df_loc["Tryb"].unique().tolist()))
            
            st.markdown("<span style='font-size:0.9rem; font-weight:bold;'>Kolor</span>", unsafe_allow_html=True)
            c_w_btn, c_b_btn, _ = st.columns([1, 1, 4])
            if c_w_btn.button("⚪ Białe", type="primary" if st.session_state.cw_solo else "secondary", use_container_width=True, key="sw_solo"):
                st.session_state.cw_solo = not st.session_state.cw_solo
                st.rerun()
            if c_b_btn.button("⚫ Czarne", type="primary" if st.session_state.cb_solo else "secondary", use_container_width=True, key="sb_solo"):
                st.session_state.cb_solo = not st.session_state.cb_solo
                st.rerun()
            
            s_c = []
            if st.session_state.cw_solo: s_c.append("Białe")
            if st.session_state.cb_solo: s_c.append("Czarne")
            
            s_h = st.slider(tu("Godziny:"), 0, 23, (0, 23))

        df_f = df_loc.copy()
        
        if isinstance(d_r, (list, tuple)):
            if len(d_r) == 2:
                df_f = df_f[(df_f["Data"] >= d_r[0]) & (df_f["Data"] <= d_r[1])]
            elif len(d_r) == 1:
                df_f = df_f[df_f["Data"] == d_r[0]]
        elif isinstance(d_r, date):
            df_f = df_f[df_f["Data"] == d_r]
            
        df_f = df_f[df_f["Kolor"].isin(s_c) & (df_f["Godzina"] >= s_h[0]) & (df_f["Godzina"] <= s_h[1])].copy()
        if s_m != tu("Wszystkie"): df_f = df_f[df_f["Tryb"] == s_m].copy()

        if not df_f.empty:
            raw_df = df_f.copy()
            raw_df["MoveTimes"] = raw_df["MoveTimes"].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else (x if isinstance(x, str) else "[]")
            )
            raw_csv = raw_df.to_csv(index=False).encode("utf-8")
            report_pdf = build_pdf_report(df_loc, username)
            with st.popover(t("download_menu"), use_container_width=True):
                export_choice = st.radio(
                    t("download_choose"),
                    options=["raw", "pdf"],
                    format_func=lambda x: t("download_raw") if x == "raw" else t("download_report"),
                    horizontal=True,
                    key="download_choice"
                )
                is_raw = export_choice == "raw"
                st.download_button(
                    t("download_now"),
                    data=raw_csv if is_raw else report_pdf,
                    file_name=f"chessstats_raw_{username}.csv" if is_raw else f"chessstats_report_{username}.pdf",
                    mime="text/csv" if is_raw else "application/pdf",
                    use_container_width=True,
                    key="download_selected_file"
                )

            t_stat, t_hist, t_czas, t_deb, t_ana, t_trening = st.tabs(["📊 Statystyki", "📅 Historia", "⏳ Czas", "🔬 Debiuty", "🧠 Analiza", "🎯 Trening"])
            
            with t_stat:
                w, d, l = (df_f["Wynik"]=="Wygrane").sum(), (df_f["Wynik"]=="Remisy").sum(), (df_f["Wynik"]=="Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f))
                k2.metric("W/R/P", f"{w}/{d}/{l}")
                k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                
                mod_w = df_f[df_f["Kolor"] == "Białe"]["Debiut_Grupa"].mode()
                fav_w = mod_w.iloc[0] if not mod_w.empty else "Brak"
                mod_b = df_f[df_f["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()
                fav_b = mod_b.iloc[0] if not mod_b.empty else "Brak"
                
                info_html = (
                    f"<div style='background-color: {chart_bg}; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid {cw}; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'>"
                    f"<div style='font-weight: bold; color: {font_color}; margin-bottom: 5px;'>Ulubione debiuty:</div>"
                    f"<div style='font-size: 0.9rem; color: {font_color};'>⚪ <b>{fav_w}</b> &emsp;|&emsp; ⚫ <b>{fav_b}</b></div>"
                    f"</div>"
                )
                st.markdown(info_html, unsafe_allow_html=True)
                
                mode_counts = df_f["Tryb"].value_counts()
                modes_to_plot = [m for m in ["Rapid", "Blitz", "Bullet"] if m in mode_counts.index]
                modes_sorted = sorted(modes_to_plot, key=lambda x: mode_counts[x], reverse=True)
                
                for m in modes_sorted:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.markdown(f"### Ranking {m}")
                        fig_elo = px.line(mdf, x="Timestamp", y="ELO", color="Konto", color_discrete_sequence=[cw])
                        fig_elo.update_layout(xaxis_title=None)
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
                                 category_orders={"Wynik": ["Przegrane", "Remisy", "Wygrane"]})
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
                
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["G"] * 100).round(0).astype(int)
                
                st.markdown(f"### {t('win_by_day')}")
                fig_d = px.bar(d_st, x="Dzień", y="Win%", color="G", color_continuous_scale=c_scale, labels={"Dzień": t("day"), "Win%": t("win_rate"), "G": t("games_count")})
                fig_d.update_layout(coloraxis_showscale=False)
                fig_d.update_yaxes(range=[0, 100])
                fig_d = style_chart(fig_d)
                st.plotly_chart(fig_d, use_container_width=True)
                
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

                pace_df = build_move_pace_table(df_f)
                pace_plot = pace_df.dropna(subset=["AvgSec"])
                st.markdown(f"### {t('move_pace')}")
                if not pace_plot.empty:
                    fig_pace = px.line(
                        pace_plot, x="Segment", y="AvgSec", markers=True,
                        labels={"Segment": t("decile"), "AvgSec": t("avg_move_seconds")}
                    )
                    fig_pace = style_chart(fig_pace)
                    st.plotly_chart(fig_pace, use_container_width=True)
                else:
                    st.info(t("no_tempo_data"))
                
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
                        tot_w = len(df_w)
                        op_g_w = df_w.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        op_g_w["% Całości"] = (op_g_w["Gry"] / tot_w * 100).round(1)
                        op_g_w = op_g_w[["Debiut_Grupa", "Gry", "% Całości", "WinRate"]]
                        
                        st.dataframe(
                            op_g_w.sort_values("Gry", ascending=False).head(15), 
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Gry": st.column_config.NumberColumn("Gry"),
                                "% Całości": st.column_config.NumberColumn("% Całości", format="%.1f%%"),
                                "WinRate": st.column_config.NumberColumn("WinRate (%)", format="%d%%")
                            }
                        )
                        with st.expander(f"Szczegółowe Warianty - ⚪ {t('color_white')}"):
                            op_w = df_w.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            op_w["% Całości"] = (op_w["Gry"] / tot_w * 100).round(1)
                            op_w = op_w[["Debiut", "Gry", "% Całości", "WinRate"]]
                            st.dataframe(
                                op_w.sort_values("Gry", ascending=False).head(20), 
                                use_container_width=True, hide_index=True,
                                column_config={
                                    "Gry": st.column_config.NumberColumn("Gry"),
                                    "% Całości": st.column_config.NumberColumn("% Całości", format="%.1f%%"),
                                    "WinRate": st.column_config.NumberColumn("WinRate (%)", format="%d%%")
                                }
                            )
                    else: st.info("Brak partii")
                        
                with c_b1:
                    st.markdown(f"<h5 style='text-align: center; color: {font_color};'>⚫ {t('color_black')}</h5>", unsafe_allow_html=True)
                    if not df_b.empty:
                        tot_b = len(df_b)
                        op_g_b = df_b.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        op_g_b["% Całości"] = (op_g_b["Gry"] / tot_b * 100).round(1)
                        op_g_b = op_g_b[["Debiut_Grupa", "Gry", "% Całości", "WinRate"]]
                        
                        st.dataframe(
                            op_g_b.sort_values("Gry", ascending=False).head(15), 
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Gry": st.column_config.NumberColumn("Gry"),
                                "% Całości": st.column_config.NumberColumn("% Całości", format="%.1f%%"),
                                "WinRate": st.column_config.NumberColumn("WinRate (%)", format="%d%%")
                            }
                        )
                        with st.expander(f"Szczegółowe Warianty - ⚫ {t('color_black')}"):
                            op_b = df_b.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                            op_b["% Całości"] = (op_b["Gry"] / tot_b * 100).round(1)
                            op_b = op_b[["Debiut", "Gry", "% Całości", "WinRate"]]
                            st.dataframe(
                                op_b.sort_values("Gry", ascending=False).head(20), 
                                use_container_width=True, hide_index=True,
                                column_config={
                                    "Gry": st.column_config.NumberColumn("Gry"),
                                    "% Całości": st.column_config.NumberColumn("% Całości", format="%.1f%%"),
                                    "WinRate": st.column_config.NumberColumn("WinRate (%)", format="%d%%")
                                }
                            )
                    else: st.info("Brak partii")

            with t_ana:
                fa1, fa2, fa3 = st.columns([1,1,1])
                d_val = fa1.date_input(tu("Dzień do analizy:"), value=df_f["Data"].max())
                opp_search = fa2.text_input(tu("Nick rywala (opcjonalnie):"))
                deb_search = fa3.selectbox(tu("Grupa debiutu:"), [tu("Wszystkie")] + sorted(df_f["Debiut_Grupa"].unique().tolist()))
                
                ana = df_f.copy()
                if opp_search or deb_search != tu("Wszystkie"):
                    if opp_search: ana = ana[ana["Przeciwnik"].str.lower().str.contains(opp_search.lower())]
                    if deb_search != tu("Wszystkie"): ana = ana[ana["Debiut_Grupa"] == deb_search]
                else:
                    ana = ana[ana["Data"] == d_val]
                    
                if not ana.empty:
                    def get_res(r):
                        if r == "Wygrane": return "W"
                        if r == "Przegrane": return "L"
                        return "D"
                    
                    ana["label"] = ana.apply(lambda x: f"{x['Data']} {x['Timestamp'].strftime('%H:%M')} | {x['Tryb']} vs {x['Przeciwnik']} ({'C' if x['Platforma'] == 'Chess.com' else 'L'}) ({get_res(x['Wynik'])})", axis=1)
                    sel = st.selectbox(tu("Mecz:"), ana.sort_values("Timestamp", ascending=False)["label"])
                    g_sel = ana[ana["label"] == sel].iloc[0]
                    if st.button(t("prepare_analysis"), type="primary", use_container_width=True):
                        with st.spinner(tu("Przesyłanie PGN do analizy...")):
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

            with t_trening:
                mode_choice = st.radio("Tryb", ["Trening Debiutów", "Zagraj z Botem"], horizontal=True, key="training_mode")
                learning_choice = "Po kolei"
                difficulty_choice = "Średni"
                player_color_choice = "Białe"
                if mode_choice == "Trening Debiutów":
                    learning_choice = st.radio("Sposób nauki", ["Po kolei", "Losowo"], horizontal=True, key="training_learning")
                else:
                    difficulty_choice = st.radio("Poziom trudności", ["Łatwy", "Średni", "Trudny"], horizontal=True, key="training_difficulty")
                    player_color_choice = st.radio("Kolor gracza", ["Białe", "Czarne"], horizontal=True, key="training_player_color")
                opening_tree = build_opening_training_tree(df_loc)
                render_training_component(
                    mode_choice,
                    learning_choice,
                    difficulty_choice,
                    opening_tree,
                    "black" if player_color_choice == "Czarne" else "white"
                )

    elif app_m == VIEW_COMPARE:
        c1, c2 = st.columns(2)
        p2 = c2.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        n2 = c2.text_input("Nick rywala:")
        
        if st.button(t("btn_rival"), type="primary", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie danych dla {n2}..."):
                    f2 = run_fetch_with_progress(n2, p2)
                    if f2[1] is not None and not f2[1].empty: 
                        st.session_state.data2, st.session_state.user2, st.session_state.plat2 = f2[1], n2, p2
                        st.rerun()
                    else:
                        st.error("Nie udało się pobrać danych rywala lub gracz nie ma historii.")

        if st.session_state.data2 is not None:
            df2 = st.session_state.data2.copy()
            if "MoveTimes" not in df2.columns:
                df2["MoveTimes"] = [[] for _ in range(len(df2))]
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
                    st.session_state.cw_por = not st.session_state.cw_por
                    st.rerun()
                if c_b_por.button("⚫ Czarne", type="primary" if st.session_state.cb_por else "secondary", use_container_width=True, key="por_b"):
                    st.session_state.cb_por = not st.session_state.cb_por
                    st.rerun()
                
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
                
            df1_c = df1_c[df1_c["Kolor"].isin(sc_c) & (df1_c["Godzina"] >= sh_c[0]) & (df1_c["Godzina"] <= sh_c[1])].copy()
            df2_c = df2_c[df2_c["Kolor"].isin(sc_c) & (df2_c["Godzina"] >= sh_c[0]) & (df2_c["Godzina"] <= sh_c[1])].copy()
            
            if sm_c != "Wszystkie":
                df1_c = df1_c[df1_c["Tryb"] == sm_c].copy()
                df2_c = df2_c[df2_c["Tryb"] == sm_c].copy()

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
                st.markdown(f"<h4 style='color: {font_color};'>Sposób zakończenia partii</h4>", unsafe_allow_html=True)
                st.divider()
                
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
                        df_win['Razem'] = df_win.groupby('Gracz')['Ilość'].transform('sum')
                        df_win['Tekst'] = df_win['Ilość'].astype(str) + " (" + (df_win['Ilość']/df_win['Razem']*100).round(1).astype(str) + "%)"
                        with c_r1:
                            st.markdown("### Jak wygrywają?")
                            fig_r_w = px.bar(df_win, x="Powod_T", y="Ilość", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2], text="Tekst")
                            fig_r_w.update_traces(textposition='outside')
                            fig_r_w = style_chart(fig_r_w)
                            st.plotly_chart(fig_r_w, use_container_width=True)

                    df_loss = df_r_comb[df_r_comb["Wynik"] == "Przegrane"].groupby(["Powod_T", "Gracz"]).size().reset_index(name="Ilość")
                    if not df_loss.empty:
                        df_loss['Razem'] = df_loss.groupby('Gracz')['Ilość'].transform('sum')
                        df_loss['Tekst'] = df_loss['Ilość'].astype(str) + " (" + (df_loss['Ilość']/df_loss['Razem']*100).round(1).astype(str) + "%)"
                        with c_r2:
                            st.markdown("### Jak przegrywają?")
                            fig_r_l = px.bar(df_loss, x="Powod_T", y="Ilość", color="Gracz", barmode="group", color_discrete_sequence=[cp1, cp2], text="Tekst")
                            fig_r_l.update_traces(textposition='outside')
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
                    
                    st.markdown(f"<h4 style='color: {font_color}; margin-top:20px;'>Zmiana ELO w czasie</h4>", unsafe_allow_html=True)
                    st.divider()
                    
                    df1_elo = df1_c.copy()
                    df2_elo = df2_c.copy()
                    df1_elo["Gracz"] = u1
                    df2_elo["Gracz"] = u2
                    df_elo_comb = pd.concat([df1_elo, df2_elo]).sort_values("Timestamp")
                    
                    mode_counts_c = df_elo_comb["Tryb"].value_counts()
                    modes_to_plot_c = [m for m in ["Rapid", "Blitz", "Bullet"] if m in mode_counts_c.index]
                    modes_sorted_c = sorted(modes_to_plot_c, key=lambda x: mode_counts_c[x], reverse=True)
                    
                    for m in modes_sorted_c:
                        mdf = df_elo_comb[df_elo_comb["Tryb"] == m]
                        if not mdf.empty:
                            st.markdown(f"### Ranking {m}")
                            fig_elo_c = px.line(mdf, x="Timestamp", y="ELO", color="Gracz", color_discrete_sequence=[cp1, cp2])
                            fig_elo_c.update_layout(xaxis_title=None)
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

                    p1_df = build_move_pace_table(df1_c).dropna(subset=["AvgSec"])
                    p2_df = build_move_pace_table(df2_c).dropna(subset=["AvgSec"])
                    if not p1_df.empty or not p2_df.empty:
                        p1_df["Gracz"] = u1
                        p2_df["Gracz"] = u2
                        pace_comp = pd.concat([p1_df, p2_df], ignore_index=True)
                        st.markdown(f"### {t('move_pace')}")
                        fig_pace_c = px.line(
                            pace_comp, x="Segment", y="AvgSec", color="Gracz", markers=True,
                            color_discrete_sequence=[cp1, cp2],
                            labels={"Segment": t("decile"), "AvgSec": t("avg_move_seconds")}
                        )
                        fig_pace_c = style_chart(fig_pace_c)
                        st.plotly_chart(fig_pace_c, use_container_width=True)
                    else:
                        st.info(t("no_tempo_data"))

            with tabs[3]:
                st.write("### 🛡️ Najpopularniejsze Debiuty (Wspólne)")
                
                def merge_openings(color_name):
                    df1_sub = df1_c[df1_c["Kolor"] == color_name]
                    df2_sub = df2_c[df2_c["Kolor"] == color_name]
                    
                    g1_op = df1_sub.groupby("Debiut_Grupa").agg(
                        **{
                            f"Partie [{u1}]": ("Wynik", "count"),
                            f"WinRate [{u1}]": ("Wynik", lambda x: round((x == "Wygrane").sum() / len(x) * 100, 1))
                        }
                    ).reset_index()
                    g2_op = df2_sub.groupby("Debiut_Grupa").agg(
                        **{
                            f"Partie [{u2}]": ("Wynik", "count"),
                            f"WinRate [{u2}]": ("Wynik", lambda x: round((x == "Wygrane").sum() / len(x) * 100, 1))
                        }
                    ).reset_index()
                    
                    m = pd.merge(g1_op, g2_op, on="Debiut_Grupa", how="outer").fillna(0)
                    m[f"Partie [{u1}]"] = m[f"Partie [{u1}]"].astype(int)
                    m[f"Partie [{u2}]"] = m[f"Partie [{u2}]"].astype(int)
                    
                    m["Razem"] = m[f"Partie [{u1}]"] + m[f"Partie [{u2}]"]
                    m = m.sort_values("Razem", ascending=False).reset_index(drop=True)
                    
                    tot1, tot2 = len(df1_sub), len(df2_sub)
                    
                    m[f"% Całości [{u1}]"] = ((m[f"Partie [{u1}]"] / tot1 * 100).round(1) if tot1 else 0.0)
                    m[f"% Całości [{u2}]"] = ((m[f"Partie [{u2}]"] / tot2 * 100).round(1) if tot2 else 0.0)
                    
                    m = m[
                        [
                            "Debiut_Grupa",
                            f"Partie [{u1}]",
                            f"% Całości [{u1}]",
                            f"WinRate [{u1}]",
                            f"Partie [{u2}]",
                            f"% Całości [{u2}]",
                            f"WinRate [{u2}]"
                        ]
                    ]
                    
                    return m

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
                            f"<div style='text-align: center; width: 33%;'>"
                            f"<div style='color: {cp1}; font-size: 1.1rem; margin-bottom: 5px; font-weight: bold; overflow: hidden; text-overflow: ellipsis;'>{u1}</div>"
                            f"<div style='color: {cp1}; font-size: 2.2rem; font-weight: bold; line-height: 1;'>{h2_w}</div>"
                            f"</div>"
                            f"<div style='text-align: center; width: 33%; border-left: 1px solid {grid_color}; border-right: 1px solid {grid_color}; padding: 0 10px;'>"
                            f"<div style='color: {font_color}; font-size: 1.1rem; font-weight: bold; margin-bottom: 5px;'>REMISY</div>"
                            f"<div style='color: {font_color}; font-size: 2.2rem; font-weight: bold; line-height: 1;'>{h2_d}</div>"
                            f"</div>"
                            f"<div style='text-align: center; width: 33%;'>"
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
                                          x="Partia_Nr", y="value", color="variable", color_discrete_sequence=[cp1, cp2],
                                          labels={"value": "Suma Zwycięstw", "Partia_Nr": "Nr Partii", "variable": "Gracz"})
                        fig_h2h = style_chart(fig_h2h)
                        st.plotly_chart(fig_h2h, use_container_width=True)
                        
                        st.write("**Historia spotkań:**")
                        st.dataframe(h2[["Data", "Tryb", "Kolor", "Wynik", "Ruchy", "Debiut"]].sort_values("Data", ascending=False), use_container_width=True, hide_index=True)
                    else: 
                        st.info(f"Brak zarejestrowanych bezpośrednich partii pomiędzy **{u1}** a **{u2}** (przy obecnych filtrach).")
