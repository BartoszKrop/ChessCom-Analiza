import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re
import json

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Analizy Szachowe", page_icon="♟️", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Metryki z małą czcionką dla agregacji */
    [data-testid="stMetricValue"] { font-size: 0.95rem !important; color: #ffffff; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
    
    .stMetric { background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
    .block-container { padding: 1rem; }
    
    div.row-widget.stRadio > div { flex-direction: row; justify-content: center; background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
    
    .asym-row { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #30363d; text-align: center; }
    .asym-val-w { width: 35%; font-size: 1.3rem; font-weight: bold; color: #ffffff; }
    .asym-label { width: 30%; font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .asym-val-b { width: 35%; font-size: 1.3rem; font-weight: bold; color: #58a6ff; }
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

def calc_elo(df, mode):
    mdf = df[df["Tryb"] == mode]
    if mdf.empty: return "-", "-", None
    best_peak, best_curr = -1, -1
    best_peak_plat, best_curr_plat = "", ""
    for plat in mdf["Platforma"].unique():
        plat_df = mdf[mdf["Platforma"] == plat]
        if not plat_df.empty:
            peak = int(plat_df["Elo_Moje"].max())
            curr = int(plat_df.sort_values("Timestamp").iloc[-1]["Elo_Moje"])
            if peak > best_peak: best_peak, best_peak_plat = peak, plat
            if curr > best_curr: best_curr, best_curr_plat = curr, plat
    is_multi = len(df["Platforma"].unique()) > 1
    p_s = "C" if best_peak_plat == "Chess.com" else "L"
    c_s = "C" if best_curr_plat == "Chess.com" else "L"
    pk_str = f"{best_peak} ({p_s})" if is_multi else str(best_peak)
    cr_str = f"{best_curr} ({c_s})" if is_multi else str(best_curr)
    return pk_str, cr_str, best_curr

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user, platform="Chess.com"):
    try:
        headers = {"User-Agent": f"AnalizySzachowe-V29-{user}"}
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        all_games = []
        konto_id = f"{user} ({'C' if platform == 'Chess.com' else 'L'})"
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
                                my_res, opp_res = g["white" if is_w else "black"]["result"], g["black" if is_w else "white"]["result"]
                                out = "Wygrane" if my_res == "win" else ("Remisy" if my_res in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                                pgn = g.get("pgn", "")
                                all_games.append({
                                    "Konto": konto_id, "Platforma": platform, "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                                    "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"), "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                                    "Elo_Moje": g["white" if is_w else "black"].get("rating", 0), "Elo_Rywala": g["black" if is_w else "white"].get("rating", 0),
                                    "Ruchy": extract_moves_count(pgn), "Debiut": extract_opening(pgn), "Przeciwnik": g["black" if is_w else "white"]["username"],
                                    "Kolor": "Białe" if is_w else "Czarne", "Powod_Konca": get_end_reason(my_res, opp_res, out), "PGN_Raw": pgn, "Link_Direct": ""
                                })
                except: continue 
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
                    out = "Wygrane" if g.get("winner") == my_col else ("Przegrane" if g.get("winner") == opp_col else "Remisy")
                    m_l = g.get("moves", "").split()
                    all_games.append({
                        "Konto": konto_id, "Platforma": platform, "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc": ts.strftime("%Y-%m"), "Tryb": g.get("speed", "Inne").capitalize(), "Wynik": out, 
                        "Elo_Moje": g["players"][my_col].get("rating", 0), "Elo_Rywala": g["players"][opp_col].get("rating", 0),
                        "Ruchy": len(m_l) // 2 + (len(m_l) % 2), "Debiut": g.get("opening", {}).get("name", "Nieznany").split(':')[0], 
                        "Przeciwnik": g["players"][opp_col].get("user", {}).get("name", "Anonim"), "Kolor": "Białe" if my_col == "white" else "Czarne",
                        "Powod_Konca": "Mat" if g.get("status")=="mate" else ("Poddanie" if g.get("status")=="resign" else ("Czas" if g.get("status")=="outoftime" else "Inne")),
                        "PGN_Raw": g.get("moves", ""), "Link_Direct": f"https://lichess.org/{g['id']}"
                    })
                except: continue
            return p_data, pd.DataFrame(all_games)
    except: return None, None

# --- SESSION STATE ---
for k in ['data', 'data2', 'url']: 
    if k not in st.session_state: st.session_state[k] = None
for k in ['user', 'user2', 'plat2']: 
    if k not in st.session_state: st.session_state[k] = ""
if 'platforms' not in st.session_state: st.session_state.platforms = []
if 'app_mode' not in st.session_state: st.session_state.app_mode = "👤 Moja Analiza"

# --- UI LOGIN ---
if st.session_state.data is None:
    st.title("♟️ Analizy Szachowe")
    log_m = st.radio("Zasięg:", ["Jeden profil", "Połącz profile"], horizontal=True)
    if log_m == "Jeden profil":
        c1, c2 = st.columns([1, 4])
        plat = c1.selectbox("Platforma:", ["Chess.com", "Lichess"])
        nick = c2.text_input("Nick:")
        if st.button("Analizuj", use_container_width=True):
            if nick:
                with st.spinner("Pobieranie..."):
                    f = fetch_data(nick, plat)
                    if f[1] is not None: st.session_state.data, st.session_state.user, st.session_state.platforms = f, nick, [plat]; st.rerun()
    else:
        c1, c2 = st.columns(2)
        p1, n1 = c1.selectbox("P1:", ["Chess.com", "Lichess"]), c1.text_input("Nick 1:")
        p2, n2 = c2.selectbox("P2:", ["Lichess", "Chess.com"]), c2.text_input("Nick 2:")
        if st.button("Połącz i Analizuj", use_container_width=True):
            if n1 and n2:
                with st.spinner("Łączenie danych..."):
                    f1, f2 = fetch_data(n1, p1), fetch_data(n2, p2)
                    if f1[1] is not None and f2[1] is not None:
                        st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                        st.session_state.user, st.session_state.platforms = f"{n1} + {n2}", list(set([p1, p2]))
                        st.rerun()
else:
    profile, df = st.session_state.data
    username, user_plats = st.session_state.user, st.session_state.platforms
    
    c_n1, c_n2, c_n3 = st.columns([2, 1, 1])
    with c_n1: new_m = st.radio("T:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], horizontal=True, label_visibility="collapsed")
    with c_n2: 
        if st.button("Odśwież", use_container_width=True): st.session_state.data = None; st.rerun()
    with c_n3:
        if st.button("Zmień gracza", use_container_width=True):
            for k in ['data','data2','url','user','user2','plat2']: st.session_state[k] = None if k in ['data','data2','url'] else ""
            st.session_state.platforms = []; st.rerun()

    if new_m != st.session_state.app_mode: st.session_state.app_mode = new_m; st.rerun()
    st.divider()

    if st.session_state.app_mode == "👤 Moja Analiza":
        c_h1, c_h2 = st.columns([1, 4])
        if profile.get("avatar"): c_h1.image(profile.get("avatar"), width=70)
        c_h2.subheader(username)
        
        m1, m2, m3 = st.columns(3)
        p_r, c_r, _ = calc_elo(df, "Rapid"); p_b, c_b, _ = calc_elo(df, "Blitz"); p_bl, c_bl, _ = calc_elo(df, "Bullet")
        m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
        m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
        m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")

        with st.expander("⚙️ Filtry"):
            f1, f2, f3 = st.columns(3)
            d_r = f1.date_input("Zakres:", value=(df["Data"].min(), df["Data"].max()))
            s_m = f2.selectbox("Tryb:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            s_a = f3.multiselect("Konto:", df["Konto"].unique().tolist(), default=df["Konto"].unique().tolist())
            s_c = st.multiselect("Kolor:", ["Białe", "Czarne"], default=["Białe", "Czarne"])
            s_h = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df.copy()
        if isinstance(d_r, (list, tuple)) and len(d_r) == 2:
            df_f = df_f[(df_f["Data"] >= d_r[0]) & (df_f["Data"] <= d_r[1])]
        df_f = df_f[df_f["Kolor"].isin(s_c) & (df_f["Godzina"] >= s_h[0]) & (df_f["Godzina"] <= s_h[1]) & df_f["Konto"].isin(s_a)]
        if s_m != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_m]

        if not df_f.empty:
            t1, t_h, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Stat", "📅 Hist", "🏁 Tech", "⏳ Czas", "🔬 Debiut", "⚖️ B&W", "🧩 Styl", "🧠 Analiza"])
            
            with t1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        st.plotly_chart(px.line(mdf, x="Timestamp", y="Elo_Moje", color="Konto", title=f"Ranking {m}", markers=True).update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0), xaxis_title=None, yaxis_title="ELO", legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None)), use_container_width=True)

            with t_h:
                monthly = df_f.groupby("Miesiąc").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum()), R=('Wynik', lambda x: (x == 'Remisy').sum()), L=('Wynik', lambda x: (x == 'Przegrane').sum())).reset_index().sort_values("Miesiąc", ascending=False)
                monthly["Win%"] = (monthly["W"] / monthly["G"] * 100).round(0).astype(int)
                st.dataframe(monthly.rename(columns={"G":"Gry"}), use_container_width=True, hide_index=True)

            with t2:
                c1, c2 = st.columns(2)
                c1.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Wygrane"], names="Powod_Konca", hole=0.4, title="Wygrane", color_discrete_sequence=px.colors.sequential.Teal), use_container_width=True)
                c2.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Przegrane"], names="Powod_Konca", hole=0.4, title="Porażki", color_discrete_sequence=px.colors.sequential.Reds), use_container_width=True)

            with t3:
                d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_st["Win%"] = (d_st["W"] / d_st["G"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="G", color_continuous_scale='Blues', title="Skuteczność wg Dni").update_layout(coloraxis_showscale=False), use_container_width=True)

            with t4:
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                st.dataframe(op.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)

            with t5:
                def get_s(c):
                    sub = df_f[df_f["Kolor"] == c]
                    if sub.empty: return "0%", 0, 0
                    return f"{int(round((sub['Wynik']=='Wygrane').sum()/len(sub)*100,0))}%", len(sub), int(sub["Ruchy"].mean())
                ws, bs = get_s("Białe"), get_s("Czarne")
                st.markdown(f"""
                <div class="asym-header"><div style="width:35%; text-align:center;">⬜ BIAŁE</div><div style="width:30%; text-align:center; color:#8b949e;">STATYSTYKA</div><div style="width:35%; text-align:center;">⬛ CZARNE</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[0]}</div><div class="asym-label">Win Rate</div><div class="asym-val-b">{bs[0]}</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[1]}</div><div class="asym-label">Partie</div><div class="asym-val-b">{bs[1]}</div></div>
                <div class="asym-row"><div class="asym-val-w">{ws[2]}</div><div class="asym-label">Śr. ruchów</div><div class="asym-val-b">{bs[2]}</div></div>
                """, unsafe_allow_html=True)

            with t6:
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["G"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(dst.sort_values("Bin", key=lambda x: [sort_duration_bins(list(x)).index(i) for i in x]), x="Bin", y="Win%", color="G", color_continuous_scale='Blues', title="Długość partii vs Win%").update_layout(coloraxis_showscale=False), use_container_width=True)
                
                st.write("### Wpływ serii (Sesja 2h)")
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
                if t_res: st.plotly_chart(px.bar(pd.DataFrame(t_res), x="Seria", y="Win%", color="Typ", barmode='group', text="Win%", hover_data=["Partie"], color_discrete_map={"Po serii Wygranych":"#1e88e5", "Po serii Porażek":"#ef553b"}), use_container_width=True)

            with t7:
                f1, f2 = st.columns(2)
                ana = df_f[df_f["Przeciwnik"].str.lower() == f2.text_input("Nick rywala:").lower()].copy() if f2.text_input("Nick rywala:") else df_f[df_f["Data"] == f1.date_input("Dzień:", value=df_f["Data"].max())].copy()
                if not ana.empty:
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False).apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({'C' if x['Platforma'] == 'Chess.com' else 'L'})", axis=1))
                    g = ana.iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        st.session_state.url = g["Link_Direct"] if g["Platforma"]=="Lichess" else import_to_lichess(g["PGN_Raw"]); st.rerun()
                    if st.session_state.url: st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:#1e88e5; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:10px;">ANALIZA ➡️</a>', unsafe_allow_html=True)

    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        c1, c2 = st.columns(2)
        p2 = c2.selectbox("Platforma rywala:", ["Chess.com", "Lichess"])
        n2 = c2.text_input("Nick rywala:")
        if st.button("Pobierz dane rywala", use_container_width=True):
            if n2:
                with st.spinner("Pobieranie..."):
                    f2 = fetch_data(n2, p2)
                    if f2[1] is not None: st.session_state.data2, st.session_state.user2, st.session_state.plat2 = f2[1], n2, p2; st.rerun()
        if st.session_state.data2 is not None:
            df2 = st.session_state.data2; u1, u2, p2_p = username, st.session_state.user2, st.session_state.plat2
            with st.expander("⚙️ Filtry"):
                fx1, fx2 = st.columns(2)
                dr_c = fx1.date_input("Daty:", value=(min(df["Data"].min(), df2["Data"].min()), max(df["Data"].max(), df2["Data"].max())), key="c_dr")
                sc_c = fx2.multiselect("Kolor:", ["Białe", "Czarne"], default=["Białe", "Czarne"], key="c_sc")
            df1_c, df2_c = df.copy(), df2.copy()
            df1_c = df1_c[df1_c["Kolor"].isin(sc_c)]; df2_c = df2_c[df2_c["Kolor"].isin(sc_c)]
            tabs = st.tabs(["📊 Ogólne", "🥊 H2H"]) if p2_p in user_plats else st.tabs(["📊 Ogólne"])
            with tabs[0]:
                wr1 = int(round((df1_c["Wynik"]=="Wygrane").sum()/len(df1_c)*100,0)) if not df1_c.empty else 0
                wr2 = int(round((df2_c["Wynik"]=="Wygrane").sum()/len(df2_c)*100,0)) if not df2_c.empty else 0
                c_m1, c_m2 = st.columns(2)
                c_m1.metric(f"Partie", f"{len(df1_c)} / {len(df2_c)}")
                c_m2.metric(f"Win Rate", f"{wr1}% / {wr2}%", wr1 - wr2)
                st.divider()
                cx1, cx2, cx3 = st.columns(3)
                df1_p = df1_c[df1_c["Platforma"] == p2_p] if not df1_c[df1_c["Platforma"] == p2_p].empty else df1_c
                _, r1_s, r1_i = calc_elo(df1_p, "Rapid"); _, r2_s, r2_i = calc_elo(df2_c, "Rapid"); cx1.metric(f"Rapid", f"{r1_s} / {r2_s}", r1_i - r2_i if r1_i and r2_i else None)
                _, b1_s, b1_i = calc_elo(df1_p, "Blitz"); _, b2_s, b2_i = calc_elo(df2_c, "Blitz"); cx2.metric(f"Blitz", f"{b1_s} / {b2_s}", b1_i - b2_i if b1_i and b2_i else None)
                _, l1_s, l1_i = calc_elo(df1_p, "Bullet"); _, l2_s, l2_i = calc_elo(df2_c, "Bullet"); cx3.metric(f"Bullet", f"{l1_s} / {l2_s}", l1_i - l2_i if l1_i and l2_i else None)
            if len(tabs) > 1:
                with tabs[1]:
                    h2 = df1_c[(df1_c['Przeciwnik'].str.lower() == u2.lower()) & (df1_c['Platforma'] == p2_p)].copy().sort_values("Timestamp").reset_index(drop=True)
                    if not h2.empty:
                        h2["Partia_Nr"] = h2.index + 1
                        h2["Ty"], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                        st.plotly_chart(px.line(h2.melt(id_vars=["Partia_Nr"], value_vars=["Ty", u2]), x="Partia_Nr", y="value", color="variable", title="Wyścig zwycięstw").update_layout(xaxis_title="Nr Partii", yaxis_title="Wygrane", legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None)), use_container_width=True)
                    else: st.info("Brak partii.")
