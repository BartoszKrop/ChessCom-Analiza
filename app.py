import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Chess Analytics Pro", page_icon="♟️", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .stMetric { 
        background-color: #161b22; 
        padding: 10px; 
        border-radius: 10px; 
        border: 1px solid #30363d;
        margin-bottom: 10px;
    }
    [data-testid="stMetricValue"] { font-size: 1.2rem !important; color: #ffffff; }
    
    .block-container { padding: 1rem; }
    
    /* Styl dla przełącznika trybów */
    div.row-widget.stRadio > div { 
        flex-direction: row; justify-content: center; 
        background-color: #161b22; padding: 10px; 
        border-radius: 10px; border: 1px solid #30363d;
    }

    /* Karty Black & White dla Asymetrii */
    .white-card {
        background-color: #ffffff;
        color: #161b22;
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #30363d;
        text-align: center;
    }
    .black-card {
        background-color: #000000;
        color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #30363d;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE ---
def extract_opening(pgn):
    if not pgn: return "Nieznany"
    match = re.search(r'openings/(.*?)"', pgn)
    if match: return match.group(1).replace('-', ' ').capitalize()
    return "Inny"

def extract_moves_count(pgn):
    if not pgn: return 0
    matches = re.findall(r'(\d+)\.', pgn)
    return int(matches[-1]) if matches else 0

def get_duration_bin(moves):
    if moves <= 20: return "0-20"
    elif moves <= 30: return "21-30"
    elif moves <= 40: return "31-40"
    elif moves <= 50: return "41-50"
    elif moves <= 60: return "51-60"
    elif moves <= 70: return "61-70"
    elif moves <= 80: return "71-80"
    else: return "81+"

def get_elo_bin(diff):
    if diff >= 50: return "1. Silny Faworyt (+50 ELO)"
    elif diff >= 15: return "2. Faworyt (+15 do +50)"
    elif diff >= -15: return "3. Równy Mecz (+/- 15)"
    elif diff >= -50: return "4. Underdog (-15 do -50)"
    else: return "5. Głęboki Underdog (-50 ELO)"

def get_end_reason(my_res, opp_res, outcome):
    detail = opp_res if outcome == "Wygrane" else my_res
    mapping = {"checkmated": "Mat", "resigned": "Poddanie", "timeout": "Czas", "abandoned": "Opuszczenie", "agreed": "Remis", "repetition": "Remis", "stalemate": "Pat", "insufficient": "Materiał", "timevsinsufficient": "Czas"}
    return mapping.get(detail, "Inne")

def extract_castling(pgn, is_white):
    if not pgn: return "Brak"
    pgn_c = re.sub(r'\{[^}]*\}', '', pgn)
    if is_white:
        if "O-O-O" in pgn_c.split('1...')[0]: return "Długa (O-O-O)"
        if "O-O" in pgn_c.split('1...')[0]: return "Krótka (O-O)"
    else:
        if "O-O-O" in pgn_c: return "Długa (O-O-O)"
        if "O-O" in pgn_c: return "Krótka (O-O)"
    return "Brak roszady"

def import_to_lichess(pgn_text):
    try:
        res = requests.post("https://lichess.org/api/import", data={'pgn': pgn_text}, headers={"Accept": "application/json"}, timeout=10)
        if res.status_code == 200: return res.json().get("url")
    except: pass
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    try:
        headers = {"User-Agent": f"ChessApp-V16-{user}"}
        p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
        s_res = requests.get(f"https://api.chess.com/pub/player/{user}/stats", headers=headers)
        a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
        if p_res.status_code != 200: return None, None, None
        p_data, s_data = p_res.json(), s_res.json()
        archives = a_res.json().get("archives", [])
        all_games = []
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        for url in archives[-12:]: # Ostatnie 12 miesięcy dla szybkości
            m_data = requests.get(url, headers=headers).json()
            for g in m_data.get("games", []):
                if "end_time" in g:
                    ts = datetime.fromtimestamp(g["end_time"])
                    is_w = g["white"]["username"].lower() == user.lower()
                    my_res = g["white" if is_w else "black"]["result"]
                    opp_res = g["black" if is_w else "white"]["result"]
                    out = "Wygrane" if my_res == "win" else ("Remisy" if my_res in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                    pgn = g.get("pgn", "")
                    all_games.append({
                        "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                        "Elo_Moje": g["white" if is_w else "black"].get("rating", 0),
                        "Elo_Rywala": g["black" if is_w else "white"].get("rating", 0),
                        "Ruchy": extract_moves_count(pgn), "Debiut": extract_opening(pgn), "Przeciwnik": g["black" if is_w else "white"]["username"],
                        "Kolor": "Białe" if is_w else "Czarne", "Powod_Konca": get_end_reason(my_res, opp_res, out),
                        "Roszada": extract_castling(pgn, is_w), "PGN_Raw": pgn
                    })
        return p_data, s_data, pd.DataFrame(all_games)
    except: return None, None, None

# --- SESSION STATE ---
if 'data' not in st.session_state: st.session_state.data = None
if 'user' not in st.session_state: st.session_state.user = ""
if 'app_mode' not in st.session_state: st.session_state.app_mode = "👤 Moja Analiza"

# --- LOGIN ---
if st.session_state.data is None:
    st.title("♟️ Chess Analytics Pro")
    nick = st.text_input("Nick Chess.com:", value=st.session_state.user, placeholder="np. Hikaru")
    if st.button("Analizuj moje wyniki", use_container_width=True):
        if nick:
            with st.spinner("Pobieranie danych z Chess.com..."):
                fetch_data.clear()
                fetched = fetch_data(nick)
                if fetched[2] is not None and not fetched[2].empty:
                    st.session_state.data, st.session_state.user = fetched, nick
                    st.rerun()
                else: st.error("Nie znaleziono danych gracza.")
else:
    profile, stats, df = st.session_state.data
    username = st.session_state.user
    
    c_nav1, c_nav2, c_nav3 = st.columns([2, 1, 1])
    with c_nav1:
        new_mode = st.radio("Tryb:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], horizontal=True, label_visibility="collapsed", index=0 if st.session_state.app_mode == "👤 Moja Analiza" else 1)
    with c_nav2:
        if st.button("🔄 Odśwież dane", use_container_width=True):
            with st.spinner("Aktualizacja historii gier..."):
                fetch_data.clear()
                fetched = fetch_data(username)
                if fetched[2] is not None: st.session_state.data = fetched; st.rerun()
    with c_nav3:
        if st.button("🚪 Zmień gracza", use_container_width=True):
            st.session_state.data = None; st.rerun()

    if new_mode != st.session_state.app_mode:
        st.session_state.app_mode = new_mode; st.rerun()
    st.divider()

    if st.session_state.app_mode == "👤 Moja Analiza":
        c_h1, c_h2 = st.columns([1, 4])
        if profile.get("avatar"): c_h1.image(profile.get("avatar"), width=70)
        c_h2.subheader(username)
        
        def gv(cat): s = stats.get(cat, {}); return f"{s.get('best', {}).get('rating', '-')} / {s.get('last', {}).get('rating', '-')}"
        m1, m2, m3 = st.columns(3)
        m1.metric("Rapid (Peak / Teraz)", gv("chess_rapid"))
        m2.metric("Blitz (Peak / Teraz)", gv("chess_blitz"))
        m3.metric("Bullet (Peak / Teraz)", gv("chess_bullet"))

        with st.expander("⚙️ Filtry"):
            f1, f2 = st.columns(2)
            d_range = f1.date_input("Zakres:", value=(df["Data"].min(), df["Data"].max()))
            s_mode = f2.selectbox("Tryb:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            s_color = st.multiselect("Kolor:", ["Białe", "Czarne"], default=["Białe", "Czarne"])
            s_days = st.multiselect("Dni:", ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'], default=['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'])
            s_hours = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df.copy()
        if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
            df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
        df_f = df_f[df_f["Kolor"].isin(s_color) & df_f["Dzień"].isin(s_days) & (df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1])]
        if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

        if not df_f.empty:
            pgn_b = "\n\n".join(df_f["PGN_Raw"].dropna().tolist())
            st.download_button(f"Pobierz bazę {len(df_f)} partii (Format PGN)", data=pgn_b, file_name="chess_export.pgn", use_container_width=True)
            
            t1, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Statystyki", "🏁 Technika", "⏳ Czas gry", "🔬 Debiuty", "⚖️ Black & White", "🧩 Styl i Psycha", "🧠 Analiza"])
            
            with t1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        fig = px.line(mdf, x="Timestamp", y="Elo_Moje", title=f"Ranking {m}", color_discrete_sequence=["#1e88e5"])
                        fig.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO")
                        st.plotly_chart(fig, use_container_width=True)

            with t2:
                st.write("### Powody zakończenia")
                c1, c2 = st.columns(2)
                with c1: st.write("**Twoje wygrane:**"); st.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Wygrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Teal), use_container_width=True)
                with c2: st.write("**Twoje porażki:**"); st.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Przegrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Reds), use_container_width=True)
                st.write("### Skuteczność Roszady")
                cs = df_f.groupby("Roszada").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                cs["Win%"] = (cs["W"] / cs["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(cs, x="Roszada", y="Win%", color="Gry", color_continuous_scale='Blues'), use_container_width=True)

            with t3:
                st.write("### Skuteczność czasowa")
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="Gry", color_continuous_scale='Blues', title="Dni tygodnia"), use_container_width=True)
                h_st = df_f.groupby("Godzina").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                h_st["Win%"] = (h_st["W"] / h_st["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(h_st, x="Godzina", y="Win%", color="Gry", color_continuous_scale='Blues', title="Godziny dnia"), use_container_width=True)

            with t4:
                st.write("### Twoje Debiuty")
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                st.dataframe(op.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)

            with t5:
                st.write("### Asymetria: Białe vs Czarne")
                def get_c_data(c):
                    sub = df_f[df_f["Kolor"] == c]
                    if sub.empty: return "0%", 0, 0, "-"
                    wr = f"{int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0))}%"
                    be = sub[sub["Wynik"]=="Przegrane"]["Powod_Konca"].mode().iloc[0] if not sub[sub["Wynik"]=="Przegrane"].empty else "Brak"
                    return wr, len(sub), int(sub["Ruchy"].mean()), be
                
                wwr, wcnt, wmov, wbad = get_c_data("Białe")
                bwr, bcnt, bmov, bbad = get_c_data("Czarne")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"""<div class="white-card">
                        <h2 style="color:#161b22; margin-bottom:0;">BIAŁE</h2>
                        <hr style="border: 0.5px solid #161b22;">
                        <p style="font-size:1.5rem; font-weight:bold; margin:0;">{wwr}</p><p style="margin:0;">Win Rate</p>
                        <br><p style="font-size:1.2rem; font-weight:bold; margin:0;">{wcnt}</p><p style="margin:0;">Partii</p>
                        <br><p style="font-size:1.2rem; font-weight:bold; margin:0;">{wmov}</p><p style="margin:0;">Śr. ruchów</p>
                        <br><p style="font-size:0.9rem; margin:0;">Najczęstsza porażka: <b>{wbad}</b></p>
                    </div>""", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"""<div class="black-card">
                        <h2 style="color:#ffffff; margin-bottom:0;">CZARNE</h2>
                        <hr style="border: 0.5px solid #ffffff;">
                        <p style="font-size:1.5rem; font-weight:bold; margin:0;">{bwr}</p><p style="margin:0;">Win Rate</p>
                        <br><p style="font-size:1.2rem; font-weight:bold; margin:0;">{bcnt}</p><p style="margin:0;">Partii</p>
                        <br><p style="font-size:1.2rem; font-weight:bold; margin:0;">{bmov}</p><p style="margin:0;">Śr. ruchów</p>
                        <br><p style="font-size:0.9rem; margin:0;">Najczęstsza porażka: <b>{bbad}</b></p>
                    </div>""", unsafe_allow_html=True)

            with t6:
                st.write("### Styl i Psycha")
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(dst, x="Bin", y="Win%", color="Gry", color_continuous_scale='Blues', title="Długość partii vs Win%"), use_container_width=True)
                df_f["Presja"] = (df_f["Elo_Moje"] - df_f["Elo_Rywala"]).apply(get_elo_bin)
                pst = df_f.groupby("Presja").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                pst["Win%"] = (pst["W"] / pst["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(pst, x="Win%", y="Presja", orientation='h', color="Gry", color_continuous_scale='Blues', title="Gra pod presją ELO"), use_container_width=True)

            with t7:
                st.write("### Analiza partii")
                f1, f2 = st.columns(2)
                sd = f1.date_input("Dzień:", value=df_f["Data"].max())
                so = f2.text_input("Nick rywala (opcjonalnie):").strip()
                ana = df_f[df_f["Przeciwnik"].str.lower() == so.lower()] if so else df_f[df_f["Data"] == sd]
                if not ana.empty:
                    ana["L"] = ana.apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({x['Wynik']})", axis=1)
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False)["L"])
                    g = ana[ana["L"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        st.session_state.url = import_to_lichess(g["PGN_Raw"]); st.rerun()
                    if 'url' in st.session_state and st.session_state.url:
                        st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:#1e88e5; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold;">ANALIZA: {g["Przeciwnik"]}</a>', unsafe_allow_html=True)
                else: st.warning("Brak partii.")

    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        c1.info(f"Gracz 1: **{username}**")
        n2 = c2.text_input("Nick rywala:", placeholder="Wpisz nick")
        if st.button("Pobierz dane rywala", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie {n2}..."):
                    f2 = fetch_data(n2)
                    if f2[2] is not None: st.session_state.data2, st.session_state.user2 = f2, n2; st.rerun()
        if st.session_state.data2:
            s1, s2 = stats, st.session_state.data2[1]
            u1, u2 = username, st.session_state.user2
            t_o, t_h = st.tabs(["📊 Ogólne", "🥊 H2H"])
            with t_o:
                c1, c2, c3 = st.columns(3)
                def gc(s, m): return s.get(m, {}).get('last', {}).get('rating', 0)
                c1.metric(f"Rapid: {u1} vs {u2}", f"{gc(s1, 'chess_rapid')} / {gc(s2, 'chess_rapid')}", int(gc(s1, 'chess_rapid')-gc(s2, 'chess_rapid')))
                c2.metric(f"Blitz: {u1} vs {u2}", f"{gc(s1, 'chess_blitz')} / {gc(s2, 'chess_blitz')}", int(gc(s1, 'chess_blitz')-gc(s2, 'chess_blitz')))
                c3.metric(f"Bullet: {u1} vs {u2}", f"{gc(s1, 'chess_bullet')} / {gc(s2, 'chess_bullet')}", int(gc(s1, 'chess_bullet')-gc(s2, 'chess_bullet')))
            with t_h:
                h2 = df[df['Przeciwnik'].str.lower() == u2.lower()].copy().sort_values("Timestamp").reset_index()
                if not h2.empty:
                    c1, c2, c3 = st.columns(3)
                    c1.metric(u1, (h2["Wynik"]=="Wygrane").sum()); c2.metric("Remisy", (h2["Wynik"]=="Remisy").sum()); c3.metric(u2, (h2["Wynik"]=="Przegrane").sum())
                    h2[u1], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                    st.plotly_chart(px.line(h2.melt(id_vars=["index"], value_vars=[u1, u2]), x="index", y="value", color="variable", title="Wyścig zwycięstw"), use_container_width=True)
                else: st.info("Brak meczów bezpośrednich.")
