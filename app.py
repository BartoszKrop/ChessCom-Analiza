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
    }
    
    .block-container { padding: 1rem; }
    
    /* Nawigacja */
    div.row-widget.stRadio > div { 
        flex-direction: row; justify-content: center; 
        background-color: #161b22; padding: 10px; 
        border-radius: 10px; border: 1px solid #30363d;
    }

    /* Tabela Asymetrii */
    .asym-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 15px;
        border-bottom: 1px solid #30363d;
        text-align: center;
    }
    .asym-val-w { width: 35%; font-size: 1.4rem; font-weight: bold; color: #ffffff; }
    .asym-label { width: 30%; font-size: 0.9rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .asym-val-b { width: 35%; font-size: 1.4rem; font-weight: bold; color: #58a6ff; }
    
    .asym-header {
        display: flex;
        justify-content: space-between;
        padding: 10px;
        background-color: #161b22;
        border-radius: 8px;
        font-weight: bold;
        margin-bottom: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE ---
def extract_opening(pgn):
    if not pgn: return "Nieznany"
    match = re.search(r'openings/(.*?)"', pgn)
    return match.group(1).replace('-', ' ').capitalize() if match else "Inny"

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
    else: return "71+"

def sort_duration_bins(bins):
    order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
    return sorted(bins, key=lambda x: order.index(x) if x in order else 99)

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

def import_to_lichess(pgn_text):
    try:
        res = requests.post("https://lichess.org/api/import", data={'pgn': pgn_text}, headers={"Accept": "application/json"}, timeout=10)
        return res.json().get("url") if res.status_code == 200 else None
    except: return None

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    try:
        headers = {"User-Agent": f"ChessApp-V19-{user}"}
        p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
        s_res = requests.get(f"https://api.chess.com/pub/player/{user}/stats", headers=headers)
        a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
        if p_res.status_code != 200: return None, None, None
        
        archives = a_res.json().get("archives", [])
        all_games = []
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        
        for url in archives:
            try:
                m_res = requests.get(url, headers=headers, timeout=10)
                if m_res.status_code == 200:
                    m_data = m_res.json()
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
                                "Kolor": "Białe" if is_w else "Czarne", "Powod_Konca": get_end_reason(my_res, opp_res, out), "PGN_Raw": pgn
                            })
            except Exception:
                continue 

        if not all_games:
            return None, None, None
            
        return p_res.json(), s_res.json(), pd.DataFrame(all_games)
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
            with st.spinner("Pobieranie całej historii partii..."):
                fetched = fetch_data(nick)
                if fetched[2] is not None and not fetched[2].empty:
                    st.session_state.data, st.session_state.user = fetched, nick
                    st.rerun()
                else: st.error("Błąd pobierania danych. Spróbuj odświeżyć stronę lub sprawdź poprawność nicku.")
else:
    profile, stats, df = st.session_state.data
    username = st.session_state.user
    
    # --- NAWIGACJA GÓRNA ---
    c_nav1, c_nav2, c_nav3 = st.columns([2, 1, 1])
    with c_nav1:
        new_mode = st.radio("Tryb:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], horizontal=True, label_visibility="collapsed")
    with c_nav2:
        if st.button("🔄 Odśwież dane", use_container_width=True):
            with st.spinner("Wymuszam pobranie najnowszych partii..."):
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
        
        m1, m2, m3 = st.columns(3)
        def gv(c): s = stats.get(c, {}); return f"{s.get('best', {}).get('rating', '-')} / {s.get('last', {}).get('rating', '-')}"
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
            st.download_button("Pobierz bazę partii (Format PGN)", data=pgn_b, file_name=f"chess_{username}.pgn", use_container_width=True)
            
            t1, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Ogólne", "🏁 Technika", "⏳ Czas gry", "🔬 Debiuty", "⚖️ Black & White", "🧩 Styl i Psycha", "🧠 Analiza"])
            
            with t1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.plotly_chart(px.line(mdf, x="Timestamp", y="Elo_Moje", title=f"Ranking {m}", color_discrete_sequence=["#1e88e5"]).update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO"), use_container_width=True)

            with t2:
                c1, c2 = st.columns(2)
                with c1: st.write("**Wygrane:**"); st.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Wygrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Teal), use_container_width=True)
                with c2: st.write("**Porażki:**"); st.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Przegrane"], names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Reds), use_container_width=True)

            with t3:
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["Gry"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="Gry", color_continuous_scale='Blues', title="Skuteczność wg Dni"), use_container_width=True)
                
                h_st = df_f.groupby("Godzina").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                h_st["Win%"] = (h_st["W"] / h_st["Gry"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(h_st, x="Godzina", y="Win%", color="Gry", color_continuous_scale='Blues', title="Skuteczność wg Godzin"), use_container_width=True)

            with t4:
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                st.dataframe(op.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)

            with t5:
                st.write("### Bezpośrednie porównanie kolorów")
                def get_stats(c):
                    sub = df_f[df_f["Kolor"] == c]
                    if sub.empty: return "0%", 0, 0
                    wr = f"{int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0))}%"
                    return wr, len(sub), int(sub["Ruchy"].mean())
                
                ws, bs = get_stats("Białe"), get_stats("Czarne")
                
                st.markdown(f"""
                <div class="asym-header">
                    <div style="width:35%; text-align:center;">⬜ BIAŁE</div>
                    <div style="width:30%; text-align:center; color:#8b949e;">STATYSTYKA</div>
                    <div style="width:35%; text-align:center;">⬛ CZARNE</div>
                </div>
                <div class="asym-row">
                    <div class="asym-val-w">{ws[0]}</div>
                    <div class="asym-label">Win Rate</div>
                    <div class="asym-val-b">{bs[0]}</div>
                </div>
                <div class="asym-row">
                    <div class="asym-val-w">{ws[1]}</div>
                    <div class="asym-label">Liczba partii</div>
                    <div class="asym-val-b">{bs[1]}</div>
                </div>
                <div class="asym-row">
                    <div class="asym-val-w">{ws[2]}</div>
                    <div class="asym-label">Śr. ruchów</div>
                    <div class="asym-val-b">{bs[2]}</div>
                </div>
                """, unsafe_allow_html=True)

            with t6:
                st.write("### ⏱️ Długość partii a Win Rate")
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["Gry"] * 100).round(0).astype(int)
                dst["SortKey"] = dst["Bin"].apply(lambda x: sort_duration_bins([x])[0])
                dst = dst.sort_values(by="SortKey", key=lambda col: [sort_duration_bins(list(col)).index(x) for x in col]).drop("SortKey", axis=1)
                st.plotly_chart(px.bar(dst, x="Bin", y="Win%", color="Gry", color_continuous_scale='Blues', title="Skuteczność wg długości partii"), use_container_width=True)
                
                st.write("### 🥊 Gra pod presją ELO")
                df_f["Presja"] = (df_f["Elo_Moje"] - df_f["Elo_Rywala"]).apply(get_elo_bin)
                pst = df_f.groupby("Presja").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                pst["Win%"] = (pst["W"] / pst["Gry"] * 100).round(0).astype(int)
                pst = pst.sort_values("Presja")
                st.plotly_chart(px.bar(pst, x="Win%", y="Presja", orientation='h', color="Gry", color_continuous_scale='Blues', title="Skuteczność wg ELO rywala"), use_container_width=True)

                st.write("### 📉 Analiza Tiltu (Wpływ serii)")
                df_tilt = df_f.sort_values('Timestamp').copy()
                streaks_type, streaks_count = [], []
                c_type, c_count = None, 0
                
                for res in df_tilt['Wynik']:
                    streaks_type.append(c_type)
                    streaks_count.append(c_count)
                    if res == 'Wygrane':
                        if c_type == 'W': c_count += 1
                        else: c_type = 'W'; c_count = 1
                    elif res == 'Przegrane':
                        if c_type == 'L': c_count += 1
                        else: c_type = 'L'; c_count = 1
                    else: 
                        c_type = None; c_count = 0
                        
                df_tilt['Seria_Typ'] = streaks_type
                df_tilt['Seria_Dlugosc'] = streaks_count
                
                tilt_stats = []
                for stype, nazwa in [('W', 'Po serii Wygranych'), ('L', 'Po serii Porażek')]:
                    for count in [1, 2, 3]:
                        subset = df_tilt[(df_tilt['Seria_Typ'] == stype) & (df_tilt['Seria_Dlugosc'] == count)]
                        if len(subset) > 0:
                            w_count = (subset['Wynik'] == 'Wygrane').sum()
                            tilt_stats.append({"Typ": nazwa, "Długość serii (przed meczem)": f"{count} z rzędu", "Win%": int(round((w_count / len(subset)) * 100, 0)), "Gry": len(subset)})
                    
                    subset_4 = df_tilt[(df_tilt['Seria_Typ'] == stype) & (df_tilt['Seria_Dlugosc'] >= 4)]
                    if len(subset_4) > 0:
                        w_count = (subset_4['Wynik'] == 'Wygrane').sum()
                        tilt_stats.append({"Typ": nazwa, "Długość serii (przed meczem)": "4+ z rzędu", "Win%": int(round((w_count / len(subset_4)) * 100, 0)), "Gry": len(subset_4)})

                if tilt_stats:
                    df_tilt_res = pd.DataFrame(tilt_stats)
                    fig_tilt = px.bar(df_tilt_res, x="Długość serii (przed meczem)", y="Win%", color="Typ", barmode='group',
                                     text="Win%", color_discrete_map={"Po serii Wygranych":"#1e88e5", "Po serii Porażek":"#ef553b"})
                    fig_tilt.update_traces(textposition='outside')
                    fig_tilt.update_layout(margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_tilt, use_container_width=True)
                else:
                    st.info("Za mało gier do analizy tiltu.")

            with t7:
                f1, f2 = st.columns(2)
                sd = f1.date_input("Dzień:", value=df_f["Data"].max())
                so = f2.text_input("Nick rywala:").strip()
                ana = df_f[df_f["Przeciwnik"].str.lower() == so.lower()] if so else df_f[df_f["Data"] == sd]
                if not ana.empty:
                    ana["L"] = ana.apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({x['Wynik']})", axis=1)
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False)["L"])
                    g = ana[ana["L"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        with st.spinner("Przekazywanie na serwer Lichess..."):
                            st.session_state.url = import_to_lichess(g["PGN_Raw"]); st.rerun()
                    if 'url' in st.session_state and st.session_state.url:
                        st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:#1e88e5; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:10px;">ANALIZA: {g["Przeciwnik"]}</a>', unsafe_allow_html=True)
                else: st.warning("Brak partii.")

    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        c1.info(f"Gracz 1: **{username}**")
        n2 = c2.text_input("Rywal:", placeholder="Wpisz nick")
        if st.button("Pobierz dane", use_container_width=True):
            if n2:
                with st.spinner("Pobieranie historii rywala..."):
                    fetch_data.clear()
                    f2 = fetch_data(n2)
                    if f2[2] is not None: st.session_state.data2, st.session_state.user2 = f2, n2; st.rerun()
                    else: st.error("Nie znaleziono gracza.")
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
                h2 = df[df['Przeciwnik'].str.lower() == u2.lower()].copy().sort_values("Timestamp").reset_index(drop=True)
                h2["Partia_Nr"] = h2.index + 1
                if not h2.empty:
                    c1, c2, c3 = st.columns(3)
                    c1.metric(u1, (h2["Wynik"]=="Wygrane").sum()); c2.metric("Remisy", (h2["Wynik"]=="Remisy").sum()); c3.metric(u2, (h2["Wynik"]=="Przegrane").sum())
                    h2[u1], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                    st.plotly_chart(px.line(h2.melt(id_vars=["Partia_Nr"], value_vars=[u1, u2]), x="Partia_Nr", y="value", color="variable", title="Wyścig zwycięstw").update_layout(xaxis_title="Numer Partii", yaxis_title="Suma Zwycięstw"), use_container_width=True)
                else: st.info("Brak meczów bezpośrednich pomiędzy wami.")
