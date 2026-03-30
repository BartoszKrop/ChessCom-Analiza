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
        height: 100%;
    }
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; color: #ffffff; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    
    .block-container {
        padding: 1rem;
    }
    
    div.row-widget.stRadio > div { flex-direction: row; justify-content: center; background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE ---
def extract_opening(pgn):
    if not pgn: return "Nieznany"
    match = re.search(r'openings/(.*?)"', pgn)
    if match:
        return match.group(1).replace('-', ' ').capitalize()
    return "Inny"

def extract_moves_count(pgn):
    if not pgn: return 0
    matches = re.findall(r'(\d+)\.', pgn)
    if matches:
        return int(matches[-1])
    return 0

def get_duration_bin(moves):
    if moves <= 20: return "0-20"
    elif moves <= 30: return "21-30"
    elif moves <= 40: return "31-40"
    elif moves <= 50: return "41-50"
    elif moves <= 60: return "51-60"
    elif moves <= 70: return "61-70"
    elif moves <= 80: return "71-80"
    elif moves <= 90: return "81-90"
    else: return "90+"

def sort_duration_bins(bins):
    order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71-80", "81-90", "90+"]
    return sorted(bins, key=lambda x: order.index(x) if x in order else 99)

def get_elo_bin(diff):
    if diff >= 50: return "1. Silny Faworyt (+50 ELO)"
    elif diff >= 15: return "2. Faworyt (+15 do +50)"
    elif diff >= -15: return "3. Równy Mecz (+/- 15)"
    elif diff >= -50: return "4. Underdog (-15 do -50)"
    else: return "5. Głęboki Underdog (-50 ELO)"

def get_end_reason(my_res, opp_res, outcome):
    detail = opp_res if outcome == "Wygrane" else my_res
    mapping = {
        "checkmated": "Mat",
        "resigned": "Poddanie",
        "timeout": "Czas",
        "abandoned": "Opuszczenie meczu",
        "agreed": "Remis",
        "repetition": "Remis",
        "stalemate": "Pat",
        "insufficient": "Brak materiału",
        "timevsinsufficient": "Czas",
        "50move": "Remis"
    }
    return mapping.get(detail, "Inne")

def extract_castling(pgn, is_white):
    if not pgn: return "Brak"
    pgn_clean = re.sub(r'\{[^}]*\}', '', pgn)
    pgn_clean = re.sub(r'\[[^\]]*\]', '', pgn_clean)
    if is_white:
        if re.search(r'\b\d+\.\s*O-O-O\b', pgn_clean): return "Długa (O-O-O)"
        if re.search(r'\b\d+\.\s*O-O\b', pgn_clean): return "Krótka (O-O)"
    else:
        if re.search(r'\b\d+\.\s*[^\s]+\s+O-O-O\b', pgn_clean) or re.search(r'\b\d+\.\.\.\s*O-O-O\b', pgn_clean): return "Długa (O-O-O)"
        if re.search(r'\b\d+\.\s*[^\s]+\s+O-O\b', pgn_clean) or re.search(r'\b\d+\.\.\.\s*O-O\b', pgn_clean): return "Krótka (O-O)"
    return "Brak roszady"

def import_to_lichess(pgn_text):
    try:
        url = "https://lichess.org/api/import"
        res = requests.post(url, data={'pgn': pgn_text}, headers={"Accept": "application/json"}, timeout=10)
        if res.status_code == 200: return res.json().get("url")
    except: pass
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    try:
        headers = {"User-Agent": f"ChessApp-V15-{user}"}
        p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
        s_res = requests.get(f"https://api.chess.com/pub/player/{user}/stats", headers=headers)
        a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
        if p_res.status_code != 200: return None, None, None
        p_data, s_data = p_res.json(), s_res.json()
        archives = a_res.json().get("archives", [])
        all_games = []
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        for url in archives:
            m_data = requests.get(url, headers=headers).json()
            for g in m_data.get("games", []):
                if "end_time" in g:
                    ts = datetime.fromtimestamp(g["end_time"])
                    is_w = g["white"]["username"].lower() == user.lower()
                    opp = g["black" if is_w else "white"]["username"]
                    my_res_raw = g["white" if is_w else "black"]["result"]
                    opp_res_raw = g["black" if is_w else "white"]["result"]
                    out = "Wygrane" if my_res_raw == "win" else ("Remisy" if my_res_raw in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                    my_r = g["white" if is_w else "black"].get("rating", 0)
                    opp_r = g["black" if is_w else "white"].get("rating", 0)
                    pgn_raw = g.get("pgn", "")
                    all_games.append({
                        "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc_Klucz": ts.strftime("%Y-%m"), "Miesiąc_Format": ts.strftime("%m/%Y"),
                        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, "Elo_Moje": my_r, "Elo_Rywala": opp_r, 
                        "Ruchy": extract_moves_count(pgn_raw), "Debiut": extract_opening(pgn_raw), "Przeciwnik": opp, "Kolor": "Białe" if is_w else "Czarne",
                        "Powod_Konca": get_end_reason(my_res_raw, opp_res_raw, out), "Roszada": extract_castling(pgn_raw, is_w), "PGN_Raw": pgn_raw
                    })
        return p_data, s_data, pd.DataFrame(all_games)
    except: return None, None, None

# --- SESSION STATE ---
if 'data' not in st.session_state: st.session_state.data = None
if 'user' not in st.session_state: st.session_state.user = ""
if 'current_lichess_url' not in st.session_state: st.session_state.current_lichess_url = None
if 'app_mode' not in st.session_state: st.session_state.app_mode = "👤 Moja Analiza"
if 'data2' not in st.session_state: st.session_state.data2 = None
if 'user2' not in st.session_state: st.session_state.user2 = ""

# --- LOGOWANIE ---
if st.session_state.data is None:
    st.title("♟️ Chess Analytics Pro")
    nick = st.text_input("Nick Chess.com:", value=st.session_state.user, placeholder="np. Hikaru")
    if st.button("Analizuj moje wyniki", use_container_width=True):
        if nick:
            with st.spinner("Pobieranie danych..."):
                fetch_data.clear()
                fetched = fetch_data(nick)
                if fetched[2] is not None and not fetched[2].empty:
                    st.session_state.data, st.session_state.user = fetched, nick
                    st.rerun()
                else: st.error("Błąd pobierania danych.")
else:
    profile, stats, df = st.session_state.data
    username = st.session_state.user
    col_nav1, col_nav2, col_nav3 = st.columns([2, 1, 1])
    with col_nav1:
        new_mode = st.radio("Tryb:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], horizontal=True, label_visibility="collapsed", index=0 if st.session_state.app_mode == "👤 Moja Analiza" else 1)
    with col_nav2:
        if st.button("🔄 Odśwież dane", use_container_width=True):
            with st.spinner("Pobieranie najświeższych partii..."):
                fetch_data.clear()
                fetched = fetch_data(username)
                if fetched[2] is not None:
                    st.session_state.data, st.session_state.current_lichess_url = fetched, None
                    st.rerun()
    with col_nav3:
        if st.button("🚪 Zmień gracza", use_container_width=True):
            st.session_state.data, st.session_state.data2, st.rerun()
            
    if new_mode != st.session_state.app_mode:
        st.session_state.app_mode = new_mode
        st.rerun()
    st.divider()

    if st.session_state.app_mode == "👤 Moja Analiza":
        avatar = profile.get("avatar")
        c_h1, c_h2 = st.columns([1, 4])
        if avatar: c_h1.image(avatar, width=70)
        c_h2.subheader(username)
        def get_elo_v(cat):
            s = stats.get(cat, {})
            return f"{s.get('best', {}).get('rating', '-')} / {s.get('last', {}).get('rating', '-')}"
        m1, m2, m3 = st.columns(3)
        m1.metric("Rapid (Peak / Obecnie)", get_elo_v("chess_rapid"))
        m2.metric("Blitz (Peak / Obecnie)", get_elo_v("chess_blitz"))
        m3.metric("Bullet (Peak / Obecnie)", get_elo_v("chess_bullet"))

        with st.expander("⚙️ Filtry"):
            c_f1, c_f2 = st.columns(2)
            d_range = c_f1.date_input("Zakres dat:", value=(df["Data"].min(), df["Data"].max()))
            s_mode = c_f2.selectbox("Tryb gry:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            s_color = st.multiselect("Kolor gracza:", ["Białe", "Czarne"], default=["Białe", "Czarne"])
            s_days = st.multiselect("Dni tygodnia:", ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'], default=['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'])
            s_hours = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df.copy()
        if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
            df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
        df_f = df_f[df_f["Kolor"].isin(s_color) & df_f["Dzień"].isin(s_days) & (df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1])]
        if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

        if not df_f.empty:
            pgn_exp = "\n\n".join(df_f["PGN_Raw"].dropna().tolist())
            st.download_button(label=f"Pobierz bazę {len(df_f)} partii (Format PGN)", data=pgn_exp, file_name=f"Chess_{username}.pgn", mime="text/plain", use_container_width=True)
            
            t1, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Statystyki", "🏁 Technika", "⏳ Czas gry", "🔬 Debiuty", "⚖️ Asymetria", "🧩 Styl i Psycha", "🧠 Analiza"])
            
            with t1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f))
                k2.metric("W/R/P", f"{w}/{d}/{l}")
                k3.metric("Win%", f"{int(round((w/len(df_f))*100, 0))}%")
                for mode in ["Rapid", "Blitz", "Bullet"]:
                    m_df = df_f[df_f["Tryb"] == mode].sort_values("Timestamp")
                    if not m_df.empty:
                        fig = px.line(m_df, x="Timestamp", y="Elo_Moje", title=f"Ranking: {mode}", color_discrete_sequence=["#1e88e5"])
                        fig.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO")
                        st.plotly_chart(fig, use_container_width=True)

            with t2:
                st.write("### Powody zakończenia")
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    st.write("**Twoje wygrane:**")
                    fig_w = px.pie(df_f[df_f["Wynik"] == "Wygrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                    st.plotly_chart(fig_w, use_container_width=True)
                with c_e2:
                    st.write("**Twoje porażki:**")
                    fig_l = px.pie(df_f[df_f["Wynik"] == "Przegrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Reds)
                    st.plotly_chart(fig_l, use_container_width=True)
                st.write("### Roszady")
                cs = df_f.groupby("Roszada").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                cs["Win%"] = (cs["W"] / cs["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(cs, x="Roszada", y="Win%", color="Gry", color_continuous_scale='Blues'), use_container_width=True)

            with t3:
                st.write("### Skuteczność w czasie")
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="Gry", color_continuous_scale='Blues', title="Wg Dni"), use_container_width=True)
                h_st = df_f.groupby("Godzina").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                h_st["Win%"] = (h_st["W"] / h_st["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(h_st, x="Godzina", y="Win%", color="Gry", color_continuous_scale='Blues', title="Wg Godzin"), use_container_width=True)

            with t4:
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                op["Win%"] = (op["W"] / op["Gry"] * 100).round(0).astype(int)
                st.dataframe(op[["Debiut", "Gry", "Win%"]].rename(columns={"Gry": "Partie"}).sort_values("Partie", ascending=False).head(20), use_container_width=True, hide_index=True)

            with t5:
                st.write("### Białe vs Czarne")
                c_as1, c_as2 = st.columns(2)
                def get_c_s(d_c):
                    if d_c.empty: return None
                    return int(round((d_c["Wynik"] == "Wygrane").sum() / len(d_c) * 100, 0)), len(d_c), int(d_c["Ruchy"].mean())
                sw, sb = get_c_s(df_f[df_f["Kolor"] == "Białe"]), get_c_s(df_f[df_f["Kolor"] == "Czarne"])
                with c_as1:
                    st.info("⬜ **BIAŁE**")
                    if sw: st.metric("Win Rate", f"{sw[0]}%"); st.metric("Partie", sw[1]); st.metric("Śr. ruchów", sw[2])
                with c_as2:
                    st.success("⬛ **CZARNE**")
                    if sb: st.metric("Win Rate", f"{sb[0]}%"); st.metric("Partie", sb[1]); st.metric("Śr. ruchów", sb[2])

            with t6:
                st.write("### Styl i Psycha")
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(dst, x="Bin", y="Win%", color="Gry", title="Długość partii vs Win%"), use_container_width=True)
                df_f["Diff"] = df_f["Elo_Moje"] - df_f["Elo_Rywala"]
                df_f["Presja"] = df_f["Diff"].apply(get_elo_bin)
                pst = df_f.groupby("Presja").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                pst["Win%"] = (pst["W"] / pst["Gry"] * 100).round(0)
                st.plotly_chart(px.bar(pst, x="Win%", y="Presja", orientation='h', color="Gry", title="Gra pod presją ELO"), use_container_width=True)

            with t7:
                st.write("### Analiza partii")
                c1, c2 = st.columns(2)
                s_d = c1.date_input("Dzień:", value=df_f["Data"].max())
                s_o = c2.text_input("Nick rywala (opcjonalnie):").strip()
                df_ana = df_f[df_f["Przeciwnik"].str.lower() == s_o.lower()] if s_o else df_f[df_f["Data"] == s_d]
                if not df_ana.empty:
                    df_ana["L"] = df_ana.apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({x['Wynik']})", axis=1)
                    sel = st.selectbox("Wybierz mecz:", df_ana.sort_values("Timestamp", ascending=False)["L"], key="msel")
                    game = df_ana[df_ana["L"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        with st.spinner("Łączenie z Lichess..."):
                            st.session_state.current_lichess_url = import_to_lichess(game["PGN_Raw"])
                            st.rerun()
                    if st.session_state.current_lichess_url:
                        st.markdown(f'<a href="{st.session_state.current_lichess_url}" target="_blank" style="display: block; width: 100%; text-align: center; background-color: #1e88e5; color: white; padding: 12px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 10px;">ANALIZA: {game["Przeciwnik"]}</a>', unsafe_allow_html=True)
                else: st.warning("Brak partii.")

    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        c_p1, c_p2 = st.columns(2)
        c_p1.info(f"Twoje dane: **{username}**")
        n2 = c_p2.text_input("Nick rywala:", value=st.session_state.user2, placeholder="Wpisz nick")
        if st.button("Pobierz dane rywala", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie {n2}..."):
                    f2 = fetch_data(n2)
                    if f2[2] is not None: st.session_state.data2, st.session_state.user2 = f2, n2; st.rerun()
        if st.session_state.data2:
            p1, s1, d1 = st.session_state.data
            p2, s2, d2 = st.session_state.data2
            u1, u2 = username, st.session_state.user2
            t_o, t_h = st.tabs(["📊 Ogólne", "🥊 H2H"])
            with t_o:
                c1, c2, c3 = st.columns(3)
                def gce(s, m): return s.get(m, {}).get('last', {}).get('rating', 0)
                c1.metric(f"Rapid: {u1} vs {u2}", f"{gce(s1, 'chess_rapid')} / {gce(s2, 'chess_rapid')}", int(gce(s1, 'chess_rapid') - gce(s2, 'chess_rapid')))
                c2.metric(f"Blitz: {u1} vs {u2}", f"{gce(s1, 'chess_blitz')} / {gce(s2, 'chess_blitz')}", int(gce(s1, 'chess_blitz') - gce(s2, 'chess_blitz')))
                c3.metric(f"Bullet: {u1} vs {u2}", f"{gce(s1, 'chess_bullet')} / {gce(s2, 'chess_bullet')}", int(gce(s1, 'chess_bullet') - gce(s2, 'chess_bullet')))
            with t_h:
                h2h = d1[d1['Przeciwnik'].str.lower() == u2.lower()].copy().sort_values("Timestamp").reset_index()
                if not h2h.empty:
                    c_h1, c_h2, c_h3 = st.columns(3)
                    c_h1.metric(u1, (h2h["Wynik"]=="Wygrane").sum()); c_h2.metric("Remisy", (h2h["Wynik"]=="Remisy").sum()); c_h3.metric(u2, (h2h["Wynik"]=="Przegrane").sum())
                    h2h[u1], h2h[u2] = (h2h["Wynik"]=="Wygrane").cumsum(), (h2h["Wynik"]=="Przegrane").cumsum()
                    fig = px.line(h2h.melt(id_vars=["index"], value_vars=[u1, u2]), x="index", y="value", color="variable", title="Wyścig zwycięstw")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("Brak meczów bezpośrednich.")
