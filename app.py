import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re
import json

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Chess Analytics Pro", page_icon="♟️", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stMetric { background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
    .block-container { padding: 1rem; }
    div.row-widget.stRadio > div { flex-direction: row; justify-content: center; background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
    .asym-row { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #30363d; text-align: center; }
    .asym-val-w { width: 35%; font-size: 1.4rem; font-weight: bold; color: #ffffff; }
    .asym-label { width: 30%; font-size: 0.9rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .asym-val-b { width: 35%; font-size: 1.4rem; font-weight: bold; color: #58a6ff; }
    .asym-header { display: flex; justify-content: space-between; padding: 10px; background-color: #161b22; border-radius: 8px; font-weight: bold; margin-bottom: 5px; }
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

# DYNAMICZNY KALKULATOR ELO (Rozwiązuje problem Peak Lichess)
def calc_elo(df, mode):
    mdf = df[df["Tryb"] == mode]
    if mdf.empty: return "-", "-"
    peak = int(mdf["Elo_Moje"].max())
    curr = int(mdf.sort_values("Timestamp").iloc[-1]["Elo_Moje"])
    return peak, curr

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user, platform="Chess.com"):
    try:
        headers = {"User-Agent": f"ChessApp-V25-{user}"}
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        all_games = []
        konto_id = f"{user} ({platform})"

        if platform == "Chess.com":
            p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
            a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
            if p_res.status_code != 200: return None, None
            
            archives = a_res.json().get("archives", [])
            for url in archives:
                try:
                    m_res = requests.get(url, headers=headers, timeout=10)
                    if m_res.status_code == 200:
                        for g in m_res.json().get("games", []):
                            if "end_time" in g:
                                ts = datetime.fromtimestamp(g["end_time"])
                                is_w = g["white"]["username"].lower() == user.lower()
                                my_res = g["white" if is_w else "black"]["result"]
                                opp_res = g["black" if is_w else "white"]["result"]
                                out = "Wygrane" if my_res == "win" else ("Remisy" if my_res in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                                pgn = g.get("pgn", "")
                                all_games.append({
                                    "Konto": konto_id, "Platforma": platform,
                                    "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                                    "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"),
                                    "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                                    "Elo_Moje": g["white" if is_w else "black"].get("rating", 0),
                                    "Elo_Rywala": g["black" if is_w else "white"].get("rating", 0),
                                    "Ruchy": extract_moves_count(pgn), "Debiut": extract_opening(pgn), "Przeciwnik": g["black" if is_w else "white"]["username"],
                                    "Kolor": "Białe" if is_w else "Czarne", "Powod_Konca": get_end_reason(my_res, opp_res, out), 
                                    "PGN_Raw": pgn, "Link_Direct": ""
                                })
                except: continue 
            if not all_games: return None, None
            return {"avatar": p_res.json().get("avatar", "")}, pd.DataFrame(all_games)

        elif platform == "Lichess":
            p_res = requests.get(f"https://lichess.org/api/user/{user}", headers=headers)
            if p_res.status_code != 200: return None, None
            p_data = {"avatar": p_res.json().get("profile", {}).get("avatar", "")}

            g_res = requests.get(f"https://lichess.org/api/games/user/{user}?opening=true", headers={"Accept": "application/x-ndjson"})
            lines = g_res.text.strip().split('\n')
            
            for line in lines:
                if not line: continue
                try:
                    g = json.loads(line)
                    ts = datetime.fromtimestamp(g["createdAt"] / 1000.0)
                    my_col = "white" if g["players"]["white"].get("user", {}).get("name", "").lower() == user.lower() else "black"
                    opp_col = "black" if my_col == "white" else "white"
                    is_w = (my_col == "white")
                    
                    winner = g.get("winner")
                    out = "Wygrane" if winner == my_col else ("Przegrane" if winner == opp_col else "Remisy")

                    moves_list = g.get("moves", "").split()
                    ruchy = len(moves_list) // 2 + (1 if len(moves_list) % 2 != 0 else 0)
                    
                    l_status = g.get("status")
                    if l_status in ["mate"]: pk = "Mat"
                    elif l_status in ["resign"]: pk = "Poddanie"
                    elif l_status in ["outoftime"]: pk = "Czas"
                    elif l_status in ["timeout"]: pk = "Opuszczenie"
                    elif l_status in ["draw", "stalemate", "repetition"]: pk = "Remis"
                    else: pk = "Inne"

                    all_games.append({
                        "Konto": konto_id, "Platforma": platform,
                        "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"),
                        "Tryb": g.get("speed", "Inne").capitalize(), "Wynik": out, 
                        "Elo_Moje": g["players"][my_col].get("rating", 0),
                        "Elo_Rywala": g["players"][opp_col].get("rating", 0),
                        "Ruchy": ruchy, "Debiut": g.get("opening", {}).get("name", "Nieznany").split(':')[0], 
                        "Przeciwnik": g["players"][opp_col].get("user", {}).get("name", "Anonim"),
                        "Kolor": "Białe" if is_w else "Czarne", "Powod_Konca": pk, 
                        "PGN_Raw": g.get("moves", ""), "Link_Direct": f"https://lichess.org/{g['id']}"
                    })
                except: continue
                
            if not all_games: return None, None
            return p_data, pd.DataFrame(all_games)

    except: return None, None

# --- SESSION STATE ---
if 'data' not in st.session_state: st.session_state.data = None
if 'user' not in st.session_state: st.session_state.user = ""
if 'platforms' not in st.session_state: st.session_state.platforms = []
if 'app_mode' not in st.session_state: st.session_state.app_mode = "👤 Moja Analiza"

# --- LOGIN ---
if st.session_state.data is None:
    st.title("♟️ Chess Analytics Pro")
    
    log_mode = st.radio("Zasięg analizy:", ["Jeden profil", "Połącz dwa profile (Agregacja kont)"], horizontal=True)
    
    if log_mode == "Jeden profil":
        c1, c2 = st.columns([1, 4])
        with c1: plat = st.selectbox("Platforma:", ["Chess.com", "Lichess"])
        with c2: nick = st.text_input("Nick gracza:", placeholder="np. Hikaru")
        
        if st.button("Rozpocznij analizę", use_container_width=True):
            if nick:
                with st.spinner(f"Pobieranie historii z {plat}..."):
                    fetch_data.clear()
                    fetched = fetch_data(nick, plat)
                    if fetched[1] is not None:
                        st.session_state.data, st.session_state.user, st.session_state.platforms = fetched, nick, [plat]
                        st.rerun()
                    else: st.error("Nie znaleziono gracza lub brak gier.")
    else:
        st.info("Pobierzemy partie z obu kont i połączymy je w jedną wielką bazę statystyk!")
        c1, c2 = st.columns(2)
        with c1:
            p1 = st.selectbox("Platforma 1:", ["Chess.com", "Lichess"], key="p1")
            n1 = st.text_input("Nick 1:", key="n1")
        with c2:
            p2 = st.selectbox("Platforma 2:", ["Lichess", "Chess.com"], key="p2")
            n2 = st.text_input("Nick 2:", key="n2")
            
        if st.button("Agreguj konta", use_container_width=True):
            if n1 and n2:
                with st.spinner("Pobieranie i łączenie danych z obu kont..."):
                    fetch_data.clear()
                    prof1, df1 = fetch_data(n1, p1)
                    prof2, df2 = fetch_data(n2, p2)
                    
                    if df1 is not None and df2 is not None:
                        combined_df = pd.concat([df1, df2], ignore_index=True)
                        st.session_state.data = (prof1, combined_df)
                        st.session_state.user = f"{n1} & {n2}"
                        st.session_state.platforms = list(set([p1, p2]))
                        st.rerun()
                    else: st.error("Nie udało się pobrać danych z jednego z kont. Sprawdź nicki.")

else:
    profile, df = st.session_state.data
    username = st.session_state.user
    user_plats = st.session_state.platforms
    
    c_nav1, c_nav2, c_nav3 = st.columns([2, 1, 1])
    with c_nav1: new_mode = st.radio("Tryb:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], horizontal=True, label_visibility="collapsed")
    with c_nav2:
        if st.button("Odśwież dane", use_container_width=True):
            st.session_state.data = None; st.rerun() # Prosty wylog, bo refresh podwójnego konta wymagałby zapamiętania nicków
    with c_nav3:
        if st.button("Zmień gracza", use_container_width=True):
            st.session_state.data = None; st.rerun()

    if new_mode != st.session_state.app_mode: st.session_state.app_mode = new_mode; st.rerun()
    st.divider()

    if st.session_state.app_mode == "👤 Moja Analiza":
        c_h1, c_h2 = st.columns([1, 4])
        if profile.get("avatar"): c_h1.image(profile.get("avatar"), width=70)
        c_h2.subheader(username)
        
        m1, m2, m3 = st.columns(3)
        p_r, c_r = calc_elo(df, "Rapid")
        p_b, c_b = calc_elo(df, "Blitz")
        p_bl, c_bl = calc_elo(df, "Bullet")
        m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
        m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
        m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")

        with st.expander("⚙️ Filtry"):
            f1, f2, f3 = st.columns(3)
            d_range = f1.date_input("Zakres:", value=(df["Data"].min(), df["Data"].max()))
            s_mode = f2.selectbox("Tryb:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            s_acc = f3.multiselect("Konto:", df["Konto"].unique().tolist(), default=df["Konto"].unique().tolist())
            
            s_color = st.multiselect("Kolor:", ["Białe", "Czarne"], default=["Białe", "Czarne"])
            s_days = st.multiselect("Dni:", ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'], default=['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd'])
            s_hours = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df.copy()
        if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
            df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
        df_f = df_f[df_f["Kolor"].isin(s_color) & df_f["Dzień"].isin(s_days) & (df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1]) & df_f["Konto"].isin(s_acc)]
        if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

        if not df_f.empty:
            pgn_b = "\n\n".join(df_f["PGN_Raw"].dropna().tolist())
            st.download_button("Pobierz wybrane partie (PGN)", data=pgn_b, file_name="agregacja_szachy.pgn", use_container_width=True)
            
            t1, t_hist, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Statystyki", "📅 Historia", "🏁 Technika", "⏳ Czas gry", "🔬 Debiuty", "⚖️ Black & White", "🧩 Styl i Psycha", "🧠 Analiza"])
            
            with t1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.plotly_chart(px.line(mdf, x="Timestamp", y="Elo_Moje", color="Konto", title=f"Ranking {m}", markers=True).update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO"), use_container_width=True)

            with t_hist:
                st.write("### Podsumowanie miesięczne")
                monthly = df_f.groupby("Miesiąc").agg(
                    Partie=('Wynik', 'count'), Wygrane=('Wynik', lambda x: (x == 'Wygrane').sum()),
                    Remisy=('Wynik', lambda x: (x == 'Remisy').sum()), Przegrane=('Wynik', lambda x: (x == 'Przegrane').sum()),
                    Elo=('Elo_Moje', 'mean')
                ).reset_index().sort_values("Miesiąc", ascending=False)
                
                monthly["Win%"] = (monthly["Wygrane"] / monthly["Partie"] * 100).round(0).astype(int)
                monthly["Bilans"] = monthly.apply(lambda x: f"{int(x['Wygrane'])}/{int(x['Remisy'])}/{int(x['Przegrane'])}", axis=1)
                st.dataframe(monthly[["Miesiąc", "Partie", "Bilans", "Win%"]], use_container_width=True, hide_index=True)
                
                st.divider()
                sel_m = st.selectbox("Wybierz miesiąc do analizy:", monthly["Miesiąc"].unique())
                daily = df_f[df_f["Miesiąc"] == sel_m].groupby("Data").agg(
                    Gry=('Wynik', 'count'), Wygrane=('Wynik', lambda x: (x == 'Wygrane').sum()),
                    Remisy=('Wynik', lambda x: (x == 'Remisy').sum()), Przegrane=('Wynik', lambda x: (x == 'Przegrane').sum()),
                    Elo_Sr=('Elo_Moje', 'mean')
                ).reset_index().sort_values("Data", ascending=False)
                daily["Bilans"] = daily.apply(lambda x: f"{int(x['Wygrane'])}/{int(x['Remisy'])}/{int(x['Przegrane'])}", axis=1)
                daily["Data_F"] = daily["Data"].apply(lambda x: x.strftime("%Y-%m-%d (%a)"))
                st.dataframe(daily[["Data_F", "Gry", "Bilans", "Elo_Sr"]].rename(columns={"Data_F": "Dzień", "Gry": "Partie", "Elo_Sr": "Śr. ELO"}), use_container_width=True, hide_index=True)

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
                def get_stats(c):
                    sub = df_f[df_f["Kolor"] == c]
                    if sub.empty: return "0%", 0, 0
                    return f"{int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0))}%", len(sub), int(sub["Ruchy"].mean())
                ws, bs = get_stats("Białe"), get_stats("Czarne")
                st.markdown(f"""
                <div class="asym-header"><div style="width:35%; text-align:center;">⬜ BIAŁE</div><div style="width:30%; text-align:center; color:#8b949e;">STATYSTYKA</div><div style="width:35%; text-align:center;">⬛ CZARNE</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[0]}</div><div class="asym-label">Win Rate</div><div class="asym-val-b">{bs[0]}</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[1]}</div><div class="asym-label">Partie</div><div class="asym-val-b">{bs[1]}</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[2]}</div><div class="asym-label">Śr. ruchów</div><div class="asym-val-b">{bs[2]}</div></div>
                """, unsafe_allow_html=True)

            with t6:
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["Gry"] * 100).round(0).astype(int)
                dst = dst.sort_values(by="Bin", key=lambda col: [sort_duration_bins(list(col)).index(x) for x in col])
                st.plotly_chart(px.bar(dst, x="Bin", y="Win%", color="Gry", color_continuous_scale='Blues', title="Długość partii vs Win%"), use_container_width=True)
                df_f["Presja"] = (df_f["Elo_Moje"] - df_f["Elo_Rywala"]).apply(get_elo_bin)
                pst = df_f.groupby("Presja").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                pst["Win%"] = (pst["W"] / pst["Gry"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(pst.sort_values("Presja"), x="Win%", y="Presja", orientation='h', color="Gry", color_continuous_scale='Blues', title="Gra pod presją ELO"), use_container_width=True)
                st.write("### Wpływ serii (Sesja 2h)")
                df_tilt = df_f.sort_values('Timestamp').copy()
                stype_l, scount_l, last_ts = [], [], None
                ct, cc = None, 0
                for _, row in df_tilt.iterrows():
                    if last_ts and (row['Timestamp'] - last_ts).total_seconds() > 7200: ct, cc = None, 0
                    stype_l.append(ct); scount_l.append(cc)
                    if row['Wynik'] == 'Wygrane':
                        if ct == 'W': cc += 1
                        else: ct, cc = 'W', 1
                    elif row['Wynik'] == 'Przegrane':
                        if ct == 'L': cc += 1
                        else: ct, cc = 'L', 1
                    else: ct, cc = None, 0
                    last_ts = row['Timestamp']
                df_tilt['ST'], df_tilt['SC'] = stype_l, scount_l
                tilt_res = []
                for s, n in [('W', 'Po serii Wygranych'), ('L', 'Po serii Porażek')]:
                    for c in [1, 2, 3, 4]:
                        sub = df_tilt[(df_tilt['ST'] == s) & (df_tilt['SC'] == c)]
                        if not sub.empty: tilt_res.append({"Typ": n, "Seria": f"{c} z rzędu", "Win%": int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0)), "Partie": len(sub)})
                    sub5 = df_tilt[(df_tilt['ST'] == s) & (df_tilt['SC'] >= 5)]
                    if not sub5.empty: tilt_res.append({"Typ": n, "Seria": "5+ z rzędu", "Win%": int(round((sub5['Wynik']=='Wygrane').sum()/len(sub5)*100,0)), "Partie": len(sub5)})
                if tilt_res: st.plotly_chart(px.bar(pd.DataFrame(tilt_res), x="Seria", y="Win%", color="Typ", barmode='group', text="Win%", hover_data=["Partie"], color_discrete_map={"Po serii Wygranych":"#1e88e5", "Po serii Porażek":"#ef553b"}), use_container_width=True)

            with t7:
                f1, f2 = st.columns(2)
                sd = f1.date_input("Dzień:", value=df_f["Data"].max())
                so = f2.text_input("Nick rywala:").strip()
                ana = df_f[df_f["Przeciwnik"].str.lower() == so.lower()].copy() if so else df_f[df_f["Data"] == sd].copy()
                if not ana.empty:
                    ana["L"] = ana.apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({x['Platforma']})", axis=1)
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False)["L"])
                    g = ana[ana["L"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        if g["Platforma"] == "Lichess": st.session_state.url = g["Link_Direct"]; st.rerun()
                        else:
                            with st.spinner("Przekazywanie na serwer Lichess..."):
                                st.session_state.url = import_to_lichess(g["PGN_Raw"]); st.rerun()
                    if 'url' in st.session_state and st.session_state.url:
                        st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:#1e88e5; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:10px;">ANALIZA {g["Platforma"].upper()} ➡️</a>', unsafe_allow_html=True)
                else: st.warning("Brak partii.")

    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        c1.info(f"Twoje aktywne platformy: **{', '.join(user_plats)}**")
        p2 = c2.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        n2 = c2.text_input("Nick rywala:")
        
        if st.button("Pobierz dane", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie z {p2}..."):
                    fetch_data.clear()
                    prof2, df2 = fetch_data(n2, p2)
                    if df2 is not None: st.session_state.data2, st.session_state.user2, st.session_state.plat2 = df2, n2, p2; st.rerun()
                    else: st.error("Nie znaleziono gracza.")
                    
        if st.session_state.data2 is not None:
            df2 = st.session_state.data2
            u1, u2 = username, st.session_state.user2
            p2_plat = st.session_state.plat2
            
            # Decyzja o wyświetleniu H2H
            show_h2h = p2_plat in user_plats
            tabs = st.tabs(["📊 Ogólne", "🥊 H2H"]) if show_h2h else st.tabs(["📊 Ogólne"])
            
            with tabs[0]:
                c1, c2, c3 = st.columns(3)
                p_r1, c_r1 = calc_elo(df[df["Platforma"] == p2_plat] if not df[df["Platforma"] == p2_plat].empty else df, "Rapid")
                p_r2, c_r2 = calc_elo(df2, "Rapid")
                c1.metric(f"Rapid: Ty vs {u2}", f"{c_r1} / {c_r2}", c_r1 - c_r2 if isinstance(c_r1, int) and isinstance(c_r2, int) else None)
                
                p_b1, c_b1 = calc_elo(df[df["Platforma"] == p2_plat] if not df[df["Platforma"] == p2_plat].empty else df, "Blitz")
                p_b2, c_b2 = calc_elo(df2, "Blitz")
                c2.metric(f"Blitz: Ty vs {u2}", f"{c_b1} / {c_b2}", c_b1 - c_b2 if isinstance(c_b1, int) and isinstance(c_b2, int) else None)
                
                p_bl1, c_bl1 = calc_elo(df[df["Platforma"] == p2_plat] if not df[df["Platforma"] == p2_plat].empty else df, "Bullet")
                p_bl2, c_bl2 = calc_elo(df2, "Bullet")
                c3.metric(f"Bullet: Ty vs {u2}", f"{c_bl1} / {c_bl2}", c_bl1 - c_bl2 if isinstance(c_bl1, int) and isinstance(c_bl2, int) else None)
                
            if show_h2h:
                with tabs[1]:
                    h2 = df[(df['Przeciwnik'].str.lower() == u2.lower()) & (df['Platforma'] == p2_plat)].copy().sort_values("Timestamp").reset_index(drop=True)
                    if not h2.empty:
                        h2["Partia_Nr"] = h2.index + 1
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Ty (Wygrane)", (h2["Wynik"]=="Wygrane").sum()); c2.metric("Remisy", (h2["Wynik"]=="Remisy").sum()); c3.metric(u2, (h2["Wynik"]=="Przegrane").sum())
                        h2["Ty"] = (h2["Wynik"]=="Wygrane").cumsum()
                        h2[u2] = (h2["Wynik"]=="Przegrane").cumsum()
                        
                        chart_df = h2.melt(id_vars=["Partia_Nr"], value_vars=["Ty", u2])
                        st.plotly_chart(px.line(chart_df, x="Partia_Nr", y="value", color="variable", title="Wyścig zwycięstw (H2H)").update_layout(xaxis_title="Numer Partii", yaxis_title="Suma Zwycięstw"), use_container_width=True)
                    else: st.info("Brak bezpośrednich partii między wami na tej platformie.")
