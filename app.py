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
st.set_page_config(page_title="ChessStats Pro", page_icon="♟️", layout="wide")

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
    </script>
    """, height=0, width=0
)

# --- KOLORYSTYKA I STYLE WYKRESÓW ---
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
    fig.update_layout(template="plotly_dark" if st.session_state.theme != "Jasny" else "plotly_white")
    return fig

# --- TŁUMACZENIA UI ---
lang_map = {"Polski": "pl", "English": "en", "Deutsch": "de"}
ui_dict = {
    "title": {"pl": "ChessStats Pro", "en": "ChessStats Pro", "de": "ChessStats Pro"},
    "btn_analize": {"pl": "Analizuj", "en": "Analyze", "de": "Analysieren"},
    "btn_connect": {"pl": "Połącz i Analizuj", "en": "Merge & Analyze", "de": "Zusammenführen & Analysieren"},
    "btn_refresh": {"pl": "Odśwież", "en": "Refresh", "de": "Aktualisieren"},
    "btn_change": {"pl": "Zmień gracza", "en": "Change player", "de": "Spieler wechseln"},
    "win_reason": {"pl": "Sposób wygranej", "en": "Win reason", "de": "Gewinngrund"},
    "loss_reason": {"pl": "Sposób porażki", "en": "Loss reason", "de": "Verlustgrund"},
    "color_white": {"pl": "Białe", "en": "White", "de": "Weiß"},
    "color_black": {"pl": "Czarne", "en": "Black", "de": "Schwarz"}
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

def t(key, default=""):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return ui_dict.get(key, {}).get(l, default if default else key)

def t_reason(reason):
    l = lang_map.get(st.session_state.ui_lang, "pl")
    return reason_dict.get(str(reason).lower(), {}).get(l, str(reason).capitalize())

# --- STYLE CSS ---
css_chesscom = """
    .stApp { background-color: #312e2b; color: #ffffff; }
    .stMetric, div.row-widget.stRadio > div { background-color: #262421; border-radius: 5px; }
    .stButton>button[kind="primary"] { background-color: #81b64c; color: white; border-bottom: 4px solid #537b2f; font-weight: bold; }
"""
css_neon = """
    .stApp { background-color: #0a0a14; color: #e0e0ff; }
    .stMetric, div.row-widget.stRadio > div { background-color: rgba(18, 18, 38, 0.85); border: 1px solid #8c43ff; border-radius: 12px; }
    .stButton>button[kind="primary"] { background-color: rgba(0, 255, 255, 0.1); color: #00ffff; border: 1px solid #00ffff; }
"""

active_css = css_chesscom if st.session_state.theme == "Chess.com" else css_neon
st.markdown(f"<style>{active_css}</style>", unsafe_allow_html=True)

# --- FUNKCJE DANYCH ---
def get_opening_group(opening_name):
    name = str(opening_name).lower()
    if "sicilian" in name: return "Sicilian Defense"
    if "french" in name: return "French Defense"
    if "caro-kann" in name: return "Caro-Kann Defense"
    if "london" in name: return "London System"
    return opening_name.split(':')[0].strip().title()

def extract_opening(pgn):
    match = re.search(r'openings/(.*?)"', pgn)
    return match.group(1).replace('-', ' ').title() if match else "Inny"

def extract_moves_count(pgn):
    matches = re.findall(r'(\d+)\.', pgn)
    return int(matches[-1]) if matches else 0

def get_duration_bin(moves):
    if moves <= 20: return "0-20"
    elif moves <= 40: return "21-40"
    elif moves <= 60: return "41-60"
    else: return "61+"

def import_to_lichess(pgn_text):
    try:
        res = requests.post("https://lichess.org/api/import", data={'pgn': pgn_text}, timeout=10)
        return res.json().get("url") if res.status_code == 200 else None
    except: return None

@st.cache_data(ttl=3600)
def fetch_data(user, platform="Chess.com"):
    headers = {"User-Agent": "ChessStatsPro-App"}
    all_games = []
    try:
        if platform == "Chess.com":
            p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
            a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
            if p_res.status_code != 200: return None, pd.DataFrame()
            for url in a_res.json().get("archives", [])[-3:]: # Ostatnie 3 miesiące dla szybkości
                m_res = requests.get(url, headers=headers)
                for g in m_res.json().get("games", []):
                    ts = datetime.fromtimestamp(g["end_time"])
                    is_w = g["white"]["username"].lower() == user.lower()
                    my_r = g["white" if is_w else "black"]["result"]
                    opp_r = g["black" if is_w else "white"]["result"]
                    out = "Wygrane" if my_r == "win" else ("Remisy" if my_r in ["agreed", "repetition", "stalemate"] else "Przegrane")
                    pgn = g.get("pgn", "")
                    deb = extract_opening(pgn)
                    all_games.append({
                        "Platforma": "Chess.com", "Timestamp": ts, "Godzina": ts.hour, "Data": ts.date(),
                        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                        "ELO": g["white" if is_w else "black"].get("rating", 0),
                        "Ruchy": extract_moves_count(pgn), "Debiut": deb, "Debiut_Grupa": get_opening_group(deb),
                        "Przeciwnik": g["black" if is_w else "white"]["username"], "Kolor": "Białe" if is_w else "Czarne",
                        "Powod": my_r if out=="Przegrane" else opp_r, "PGN_Raw": pgn, "Link": ""
                    })
            return {"avatar": p_res.json().get("avatar", "")}, pd.DataFrame(all_games)
        else: # Lichess
            p_res = requests.get(f"https://lichess.org/api/user/{user}")
            if p_res.status_code != 200: return None, pd.DataFrame()
            g_res = requests.get(f"https://lichess.org/api/games/user/{user}?max=100&opening=true", headers={"Accept": "application/x-ndjson"})
            for line in g_res.text.strip().split('\n'):
                g = json.loads(line)
                ts = datetime.fromtimestamp(g["createdAt"] / 1000.0)
                my_col = "white" if g["players"]["white"].get("user", {}).get("name", "").lower() == user.lower() else "black"
                out = "Wygrane" if g.get("winner") == my_col else ("Przegrane" if "winner" in g else "Remisy")
                all_games.append({
                    "Platforma": "Lichess", "Timestamp": ts, "Godzina": ts.hour, "Data": ts.date(),
                    "Tryb": g.get("speed", "Inne").capitalize(), "Wynik": out, 
                    "ELO": g["players"][my_col].get("rating", 0), "Ruchy": len(g.get("moves", "").split())//2,
                    "Debiut": g.get("opening", {}).get("name", "Nieznany"), "Debiut_Grupa": get_opening_group(g.get("opening", {}).get("name", "")),
                    "Przeciwnik": g["players"]["black" if my_col=="white" else "white"].get("user", {}).get("name", "Anonim"),
                    "Kolor": "Białe" if my_col=="white" else "Czarne", "Powod": g.get("status"), "PGN_Raw": g.get("moves", ""), "Link": f"https://lichess.org/{g['id']}"
                })
            return {"avatar": p_res.json().get("profile", {}).get("avatar", "")}, pd.DataFrame(all_games)
    except: return None, pd.DataFrame()

# --- LOGIKA APLIKACJI ---
if 'data' not in st.session_state: st.session_state.data = None
if 'data2' not in st.session_state: st.session_state.data2 = None

if st.session_state.data is None:
    st.title("♟️ ChessStats Pro")
    c1, c2 = st.columns([1, 3])
    plat = c1.selectbox("Platforma:", ["Chess.com", "Lichess"])
    nick = c2.text_input("Twój Nick:")
    if st.button("Analizuj"):
        with st.spinner("Pobieranie..."):
            res = fetch_data(nick, plat)
            if res[0]: 
                st.session_state.data = res
                st.session_state.user = nick
                st.rerun()
else:
    profile, df = st.session_state.data
    u1 = st.session_state.user
    
    st.sidebar.image(profile.get("avatar", "https://www.chess.com/bundles/web/images/noavatar_l.84a92b24.gif"), width=100)
    st.sidebar.title(u1)
    app_mode = st.sidebar.radio("Tryb:", ["Moje Staty", "Porównanie H2H"])
    
    if st.sidebar.button("Wyloguj / Zmień"):
        st.session_state.data = None
        st.rerun()

    if app_mode == "Moje Staty":
        st.title(f"Statystyki: {u1}")
        w, r, p = (df["Wynik"]=="Wygrane").sum(), (df["Wynik"]=="Remisy").sum(), (df["Wynik"]=="Przegrane").sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Gry", len(df))
        c2.metric("Winrate", f"{int(w/len(df)*100)}%")
        c3.metric("Ostatnie ELO", df.iloc[0]["ELO"])
        
        st.plotly_chart(style_chart(px.line(df, x="Timestamp", y="ELO", title="Progres Rankingu")), use_container_width=True)

    elif app_mode == "Porównanie H2H":
        st.title("⚔️ Pojedynek Gigantów")
        c1, c2 = st.columns([1, 3])
        p2_plat = c1.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        u2 = c2.text_input("Nick rywala:")
        
        if st.button("Pobierz dane rywala"):
            res2 = fetch_data(u2, p2_plat)
            if res2[0]:
                st.session_state.data2 = res2[1]
                st.session_state.user2 = u2
                st.session_state.plat2 = p2_plat
                st.rerun()
        
        if st.session_state.data2 is not None:
            df2 = st.session_state.data2
            u2 = st.session_state.user2
            p2_p = st.session_state.plat2
            
            # FILTRACJA MECZÓW BEZPOŚREDNICH
            h2 = df[(df['Przeciwnik'].str.lower() == u2.lower())].copy()
            
            if not h2.empty:
                h2_w = (h2["Wynik"] == "Wygrane").sum()
                h2_d = (h2["Wynik"] == "Remisy").sum()
                h2_l = (h2["Wynik"] == "Przegrane").sum()
                
                # --- TABLICA WYNIKÓW PRO ---
                h2_html = f"""
                <div style="
                    background-color: {chart_bg}; 
                    padding: 40px; 
                    border-radius: 20px; 
                    margin: 20px 0; 
                    border: 1px solid {grid_color};
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; max-width: 900px; margin: 0 auto;">
                        <div style="text-align: center; flex: 1;">
                            <div style="color: {font_color}; font-size: 1rem; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 15px; font-weight: 600;">{u1}</div>
                            <div style="color: {cp1}; font-size: 6rem; font-weight: 900; line-height: 1; text-shadow: 0 0 20px {cp1}55;">{h2_w}</div>
                        </div>

                        <div style="text-align: center; padding: 0 50px; border-left: 2px solid {grid_color}55; border-right: 2px solid {grid_color}55; margin: 0 30px;">
                            <div style="color: {font_color}; font-size: 0.8rem; font-weight: bold; text-transform: uppercase; letter-spacing: 3px; opacity: 0.5; margin-bottom: 10px;">DRAW</div>
                            <div style="color: {font_color}; font-size: 2.5rem; font-weight: 700;">{h2_d}</div>
                        </div>

                        <div style="text-align: center; flex: 1;">
                            <div style="color: {font_color}; font-size: 1rem; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 15px; font-weight: 600;">{u2}</div>
                            <div style="color: {cp2}; font-size: 6rem; font-weight: 900; line-height: 1; text-shadow: 0 0 20px {cp2}55;">{h2_l}</div>
                        </div>
                    </div>
                </div>
                """
                st.markdown(h2_html, unsafe_allow_html=True)
                
                # --- WYKRES WYŚCIGU ---
                h2 = h2.sort_values("Timestamp").reset_index()
                h2["Nr"] = h2.index + 1
                h2[u1] = (h2["Wynik"]=="Wygrane").cumsum()
                h2[u2] = (h2["Wynik"]=="Przegrane").cumsum()
                
                st.subheader("📈 Przebieg rywalizacji (Wyścig zwycięstw)")
                fig = px.line(h2, x="Nr", y=[u1, u2], 
                              color_discrete_map={u1: cp1, u2: cp2},
                              labels={"value": "Zwycięstwa", "Nr": "Kolejne partie"})
                st.plotly_chart(style_chart(fig), use_container_width=True)
                
                # --- LISTA GIER ---
                with st.expander("📜 Szczegóły rozegranych partii"):
                    st.table(h2[["Data", "Tryb", "Kolor", "Wynik", "Ruchy"]].sort_index(ascending=False))
            else:
                st.warning(f"Nie znaleziono bezpośrednich meczów między {u1} a {u2} w pobranej historii.")
