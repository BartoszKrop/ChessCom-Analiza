import streamlit as st 
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re
import json

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="ChessStats", page_icon="♟️", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Mała czcionka metryk dla agregacji */
    [data-testid="stMetricValue"] { font-size: 0.9rem !important; color: #ffffff; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    
    .stMetric { background-color: #161b22; padding: 8px; border-radius: 10px; border: 1px solid #30363d; }
    .block-container { padding: 1rem; }
    
    /* Tagi w Lichess/Chess.com selection */
    span[data-baseweb="tag"] {
        background-color: rgba(88, 166, 255, 0.15) !important;
        color: #58a6ff !important;
        border: 1px solid rgba(88, 166, 255, 0.3) !important;
        border-radius: 12px !important;
    }
    
    .asym-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #30363d; text-align: center; }
    .asym-val-w { width: 35%; font-size: 1.2rem; font-weight: bold; color: #ffffff; }
    .asym-label { width: 30%; font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .asym-val-b { width: 35%; font-size: 1.2rem; font-weight: bold; color: #58a6ff; }
    .asym-header { display: flex; justify-content: space-between; padding: 8px; background-color: #161b22; border-radius: 8px; font-weight: bold; margin-bottom: 5px; font-size: 0.8rem;}
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
        if idx != -1:
            return fallback[:idx + len(keyword)].title()
            
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

# --- SESSION ---
for k in ['data','data2','url']: 
    if k not in st.session_state: st.session_state[k] = None
for k in ['user','user2','plat2']: 
    if k not in st.session_state: st.session_state[k] = ""
if 'platforms' not in st.session_state: st.session_state.platforms = []

# --- LOGIN ---
if st.session_state.data is None:
    st.title("♟️ ChessStats")
    log_m = st.radio("Zasięg:", ["Jeden profil", "Połącz profile (C+L)"], horizontal=True)
    if log_m == "Jeden profil":
        c1, c2 = st.columns([1, 4])
        plat = c1.selectbox("Plat:", ["Chess.com", "Lichess"])
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
                with st.spinner("Łączenie..."):
                    f1, f2 = fetch_data(n1, p1), fetch_data(n2, p2)
                    if f1[1] is not None and f2[1] is not None:
                        st.session_state.data = (f1[0], pd.concat([f1[1], f2[1]], ignore_index=True))
                        st.session_state.user, st.session_state.platforms = f"{n1}+{n2}", list(set([p1, p2]))
                        st.rerun()
else:
    profile, df = st.session_state.data
    username, user_plats = st.session_state.user, st.session_state.platforms
    
    # --- HEADER ---
    ch1, ch2, ch3, _ = st.columns([0.8, 4, 1, 3])
    with ch1:
        if profile.get("avatar"): 
            st.markdown(f'<img src="{profile.get("avatar")}" style="border-radius: 8px; width: 45px; margin-top: 5px;">', unsafe_allow_html=True)
    with ch2:
        st.markdown(f"<h3 style='margin-top: 5px; margin-bottom: 0px;'>{username}</h3>", unsafe_allow_html=True)
    with ch3:
        st.markdown("<div style='margin-top: 10px;'>", unsafe_allow_html=True)
        with st.popover("⚙️"):
            app_m = st.radio("Widok:", ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], label_visibility="collapsed")
            
            if st.button("🔄 Odśwież dane", use_container_width=True):
                fetch_data.clear() 
                with st.spinner("Pobieranie..."):
                    nowe_dane, nowy_profil = [], profile
                    for konto in df["Konto"].unique():
                        u_nick, u_plat = konto[:-4], "Chess.com" if konto[-2] == 'C' else "Lichess"
                        f_res = fetch_data(u_nick, u_plat)
                        if f_res[1] is not None:
                            nowe_dane.append(f_res[1]); nowy_profil = f_res[0]
                    if nowe_dane: st.session_state.data = (nowy_profil, pd.concat(nowe_dane, ignore_index=True))
                st.rerun()
                
            if st.button("🚪 Zmień gracza", use_container_width=True):
                for k in ['data','data2','url','user','user2','plat2']: st.session_state[k] = None if k in ['data','data2','url'] else ""
                st.session_state.platforms = []; st.rerun()
                
            st.divider()
            
            d_r = st.date_input("Zakres dat:", value=(df["Data"].min(), df["Data"].max()))
            s_m = st.selectbox("Tryb gry:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            
            st.write("Kolor:")
            col_w, col_b = st.columns(2)
            w_on = col_w.checkbox("⚪ Białe", value=True)
            b_on = col_b.checkbox("⚫ Czarne", value=True)
            s_c = []
            if w_on: s_c.append("Białe")
            if b_on: s_c.append("Czarne")
            
            s_h = st.slider("Godziny:", 0, 23, (0, 23))
            
            s_a = df["Konto"].unique().tolist()
            if len(s_a) > 1:
                s_a = st.multiselect("Konto:", s_a, default=s_a)
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # --- APLIKACJA FILTRÓW (Globalnie dla df1) ---
    df_f = df.copy()
    if isinstance(d_r, (list, tuple)) and len(d_r) == 2:
        df_f = df_f[(df_f["Data"] >= d_r[0]) & (df_f["Data"] <= d_r[1])]
    df_f = df_f[df_f["Kolor"].isin(s_c) & (df_f["Godzina"] >= s_h[0]) & (df_f["Godzina"] <= s_h[1]) & df_f["Konto"].isin(s_a)]
    if s_m != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_m]

    if app_m == "👤 Moja Analiza":
        if not df_f.empty:
            t1, t_h, t_c, t_d, t_a = st.tabs(["📊 Stat", "📅 Hist", "⏳ Czas", "🔬 Debiut", "🧠 Analiza"])
            
            with t1:
                m1, m2, m3 = st.columns(3)
                p_r, c_r, _ = calc_elo(df_f, "Rapid"); p_b, c_b, _ = calc_elo(df_f, "Blitz"); p_bl, c_bl, _ = calc_elo(df_f, "Bullet")
                m1.metric("Rapid (Peak / Teraz)", f"{p_r} / {c_r}")
                m2.metric("Blitz (Peak / Teraz)", f"{p_b} / {c_b}")
                m3.metric("Bullet (Peak / Teraz)", f"{p_bl} / {c_bl}")
                
                st.write("")
                w, d, l = (df_f["Wynik"]=="Wygrane").sum(), (df_f["Wynik"]=="Remisy").sum(), (df_f["Wynik"]=="Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Partie", len(df_f)); k2.metric("W/R/P", f"{w}/{d}/{l}"); k3.metric("Win%", f"{int(round(w/len(df_f)*100,0))}%")
                
                fav_w = df_f[df_f["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Białe"].empty else "Brak"
                fav_b = df_f[df_f["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Czarne"].empty else "Brak"
                
                st.markdown(f"""
                <div style="padding: 12px; border-radius: 8px; background-color: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; margin-bottom: 16px;">
                    <div style="font-size: 0.95rem; color: #e6edf3;">⚪ <b>{fav_w}</b> &emsp;|&emsp; ⚫ <b>{fav_b}</b></div>
                </div>
                """, unsafe_allow_html=True)
                
                for m in ["Rapid", "Blitz", "Bullet"]:
                    mdf = df_f[df_f["Tryb"] == m].sort_values("Timestamp")
                    if not mdf.empty:
                        fig = px.line(mdf, x="Timestamp", y="ELO", color="Konto", title=f"Ranking {m}", markers=True)
                        fig.update_traces(marker=dict(size=4, line=dict(width=0))) # Tyci kropki
                        fig.update_layout(xaxis_title="", yaxis_title="ELO", height=300, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None))
                        st.plotly_chart(fig, use_container_width=True)
                
                st.write("---")
                c_p1, c_p2 = st.columns(2)
                c_p1.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Wygrane"], names="Powod", hole=0.4, title="Wygrane (Jak?)", color_discrete_sequence=px.colors.sequential.Teal), use_container_width=True)
                c_p2.plotly_chart(px.pie(df_f[df_f["Wynik"]=="Przegrane"], names="Powod", hole=0.4, title="Porażki (Jak?)", color_discrete_sequence=px.colors.sequential.Reds), use_container_width=True)

            with t_h:
                st.write("### Aktywność i wyniki dzienne")
                act_df = df_f.groupby(["Data", "Wynik"]).size().reset_index(name="Partie")
                fig_act = px.bar(act_df, x="Data", y="Partie", color="Wynik", color_discrete_map={"Wygrane":"#1e88e5", "Remisy":"#8b949e", "Przegrane":"#ef553b"})
                fig_act.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None), barmode='stack')
                st.plotly_chart(fig_act, use_container_width=True)
                
                mon = df_f.groupby("Miesiąc").agg(G=('Wynik','count'), W=('Wynik',lambda x:(x=='Wygrane').sum()), R=('Wynik',lambda x:(x=='Remisy').sum()), L=('Wynik',lambda x:(x=='Przegrane').sum())).reset_index().sort_values("Miesiąc", ascending=False)
                mon["Win%"] = (mon["W"]/mon["G"]*100).round(0).astype(int)
                st.dataframe(mon.rename(columns={"G":"Gry"}), use_container_width=True, hide_index=True)

            with t_c:
                c_d, c_h_col = st.columns(2)
                with c_d:
                    d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                    d_st["Win%"] = (d_st["W"] / d_st["G"] * 100).round(0).astype(int)
                    st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="G", color_continuous_scale='Blues', title="Skuteczność wg Dni").update_layout(coloraxis_showscale=False), use_container_width=True)
                with c_h_col:
                    h_st = df_f.groupby("Godzina").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                    h_st["Win%"] = (h_st["W"] / h_st["G"] * 100).round(0).astype(int)
                    st.plotly_chart(px.bar(h_st, x="Godzina", y="Win%", color="G", color_continuous_scale='Blues', title="Skuteczność wg Godzin").update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1), coloraxis_showscale=False), use_container_width=True)

                st.write("---")
                
                st.subheader("Długość partii vs Win%", help="Kolor słupka oznacza ilość rozegranych partii w danym przedziale ruchów.")
                df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                dst = df_f.groupby("Bin").agg(G=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dst["Win%"] = (dst["W"] / dst["G"] * 100).round(0).astype(int)
                order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
                fig_dur = px.bar(dst.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), x="Bin", y="Win%", color="G", color_continuous_scale='Blues')
                fig_dur.update_layout(coloraxis_showscale=False, xaxis_title="")
                st.plotly_chart(fig_dur, use_container_width=True)
                
                st.subheader("Wpływ serii", help="Seria jest liczona w obrębie jednej ciągłej sesji gry. Sesja zostaje uznana za zakończoną, jeżeli przerwa pomiędzy partiami wyniesie więcej niż 2 godziny.")
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
                if t_res: st.plotly_chart(px.bar(pd.DataFrame(t_res), x="Seria", y="Win%", color="Typ", barmode='group', text="Win%", hover_data=["Partie"], color_discrete_map={"Po serii Wygranych":"#1e88e5", "Po serii Porażek":"#ef553b"}).update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None)), use_container_width=True)

            with t_d:
                st.write("### 🛡️ Główne Grupy Debiutów")
                c_w1, c_b1 = st.columns(2)
                df_w = df_f[df_f["Kolor"] == "Białe"]
                df_b = df_f[df_f["Kolor"] == "Czarne"]
                
                with c_w1:
                    st.markdown("<h5 style='text-align: center; color: #ffffff;'>⚪ Białe</h5>", unsafe_allow_html=True)
                    if not df_w.empty:
                        op_g_w = df_w.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_w.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii białymi w wybranym filtrze.")
                        
                with c_b1:
                    st.markdown("<h5 style='text-align: center; color: #58a6ff;'>⚫ Czarne</h5>", unsafe_allow_html=True)
                    if not df_b.empty:
                        op_g_b = df_b.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g_b.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii czarnymi w wybranym filtrze.")

                st.divider()
                
                st.write("### 🔬 Szczegółowe Warianty")
                c_w2, c_b2 = st.columns(2)
                
                with c_w2:
                    st.markdown("<h5 style='text-align: center; color: #ffffff;'>⚪ Białe</h5>", unsafe_allow_html=True)
                    if not df_w.empty:
                        op_w = df_w.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_w.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii białymi w wybranym filtrze.")
                        
                with c_b2:
                    st.markdown("<h5 style='text-align: center; color: #58a6ff;'>⚫ Czarne</h5>", unsafe_allow_html=True)
                    if not df_b.empty:
                        op_b = df_b.groupby("Debiut").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_b.sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
                    else: st.info("Brak partii czarnymi w wybranym filtrze.")

            with t_a:
                f1, f2 = st.columns(2)
                opp_search = f2.text_input("Nick rywala:")
                ana = df_f[df_f["Przeciwnik"].str.lower() == opp_search.lower()].copy() if opp_search else df_f[df_f["Data"] == f1.date_input("Dzień:", value=df_f["Data"].max())].copy()
                if not ana.empty:
                    ana["label"] = ana.apply(lambda x: f"{x['Data']} | {x['Tryb']} vs {x['Przeciwnik']} ({'C' if x['Platforma'] == 'Chess.com' else 'L'})", axis=1)
                    sel = st.selectbox("Mecz:", ana.sort_values("Timestamp", ascending=False)["label"])
                    g_sel = ana[ana["label"] == sel].iloc[0]
                    if st.button("Przygotuj analizę", use_container_width=True):
                        st.session_state.url = g_sel["Link"] if g_sel["Platforma"]=="Lichess" else import_to_lichess(g_sel["PGN_Raw"]); st.rerun()
                    if st.session_state.url: st.markdown(f'<a href="{st.session_state.url}" target="_blank" style="display:block; width:100%; text-align:center; background-color:#1e88e5; color:white; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:10px;">ANALIZA ➡️</a>', unsafe_allow_html=True)

    elif app_m == "⚔️ Porównanie Graczy":
        st.write("Wybierz rywala do porównania:")
        c1, c2 = st.columns([1, 2])
        p2 = c1.selectbox("Platforma rywala:", ["Chess.com", "Lichess"], label_visibility="collapsed")
        n2 = c2.text_input("Nick rywala:", label_visibility="collapsed", placeholder="Wpisz nick rywala...")
        
        if st.button("Pobierz dane", use_container_width=True):
            if n2:
                with st.spinner(f"Pobieranie danych dla {n2}..."):
                    f2 = fetch_data(n2, p2)
                    if f2[1] is not None: 
                        st.session_state.data2, st.session_state.user2, st.session_state.plat2 = f2[1], n2, p2
                        st.rerun()
                    else: st.error("Nie udało się pobrać danych rywala. Sprawdź nick i platformę.")

        if st.session_state.data2 is not None:
            df2 = st.session_state.data2
            u1, u2, p2_p = username, st.session_state.user2, st.session_state.plat2
            
            df2_c = df2.copy()
            if isinstance(d_r, (list, tuple)) and len(d_r) == 2:
                df2_c = df2_c[(df2_c["Data"] >= d_r[0]) & (df2_c["Data"] <= d_r[1])]
                
            df2_c = df2_c[df2_c["Kolor"].isin(s_c) & (df2_c["Godzina"] >= s_h[0]) & (df2_c["Godzina"] <= s_h[1])]
            if s_m != "Wszystkie": df2_c = df2_c[df2_c["Tryb"] == s_m]

            tabs_names = ["📊 Stat", "📅 Hist", "⏳ Czas", "🔬 Debiut"]
            if p2_p in user_plats: tabs_names.append("🥊 H2H")
            tabs = st.tabs(tabs_names)

            with tabs[0]:
                st.markdown(f"### 🏆 {u1} vs {u2}")
                
                g1, g2 = len(df_f), len(df2_c)
                w1 = int(round((df_f["Wynik"]=="Wygrane").sum()/g1*100,0)) if g1 > 0 else 0
                w2 = int(round((df2_c["Wynik"]=="Wygrane").sum()/g2*100,0)) if g2 > 0 else 0
                d1 = int(round((df_f["Wynik"]=="Remisy").sum()/g1*100,0)) if g1 > 0 else 0
                d2 = int(round((df2_c["Wynik"]=="Remisy").sum()/g2*100,0)) if g2 > 0 else 0
                m1 = int(df_f["Ruchy"].mean()) if g1 > 0 else 0
                m2 = int(df2_c["Ruchy"].mean()) if g2 > 0 else 0
                
                fav_op1_w = df_f[df_f["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Białe"].empty else "Brak"
                fav_op1_b = df_f[df_f["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df_f[df_f["Kolor"] == "Czarne"].empty else "Brak"
                
                fav_op2_w = df2_c[df2_c["Kolor"] == "Białe"]["Debiut_Grupa"].mode()[0] if not df2_c[df2_c["Kolor"] == "Białe"].empty else "Brak"
                fav_op2_b = df2_c[df2_c["Kolor"] == "Czarne"]["Debiut_Grupa"].mode()[0] if not df2_c[df2_c["Kolor"] == "Czarne"].empty else "Brak"

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Liczba partii", f"{g1} / {g2}", g1 - g2)
                k2.metric("Win Rate (%)", f"{w1}% / {w2}%", w1 - w2)
                k3.metric("Draw Rate (%)", f"{d1}% / {d2}%", d1 - d2)
                k4.metric("Średnio ruchów", f"{m1} / {m2}", m1 - m2)

                st.divider()
                st.markdown("**Aktualny Ranking:**")
                cx1, cx2, cx3 = st.columns(3)
                df1_p = df_f[df_f["Platforma"] == p2_p] if not df_f[df_f["Platforma"] == p2_p].empty else df_f
                _, r1_s, r1_i = calc_elo(df1_p, "Rapid"); _, r2_s, r2_i = calc_elo(df2_c, "Rapid")
                cx1.metric(f"Rapid", f"{r1_s} / {r2_s}", r1_i - r2_i if r1_i and r2_i else None)
                
                _, b1_s, b1_i = calc_elo(df1_p, "Blitz"); _, b2_s, b2_i = calc_elo(df2_c, "Blitz")
                cx2.metric(f"Blitz", f"{b1_s} / {b2_s}", b1_i - b2_i if b1_i and b2_i else None)
                
                _, l1_s, l1_i = calc_elo(df1_p, "Bullet"); _, l2_s, l2_i = calc_elo(df2_c, "Bullet")
                cx3.metric(f"Bullet", f"{l1_s} / {l2_s}", l1_i - l2_i if l1_i and l2_i else None)
                
                st.divider()
                o1, o2 = st.columns(2)
                
                o1.markdown(f"""
                <div style="padding: 12px; border-radius: 8px; background-color: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; margin-bottom: 16px;">
                    <div style="font-weight: bold; margin-bottom: 6px; color: #58a6ff;">Ulubione debiuty ({u1}):</div>
                    <div style="font-size: 0.85rem; color: #e6edf3;">⚪ <b>{fav_op1_w}</b><br>⚫ <b>{fav_op1_b}</b></div>
                </div>
                """, unsafe_allow_html=True)
                
                o2.markdown(f"""
                <div style="padding: 12px; border-radius: 8px; background-color: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; margin-bottom: 16px;">
                    <div style="font-weight: bold; margin-bottom: 6px; color: #58a6ff;">Ulubione debiuty ({u2}):</div>
                    <div style="font-size: 0.85rem; color: #e6edf3;">⚪ <b>{fav_op2_w}</b><br>⚫ <b>{fav_op2_b}</b></div>
                </div>
                """, unsafe_allow_html=True)

            with tabs[1]:
                if not df_f.empty and not df2_c.empty:
                    st.write("### Aktywność dzienna")
                    act_df1 = df_f.groupby("Data").size().reset_index(name="Partie")
                    act_df1["Gracz"] = u1
                    act_df2 = df2_c.groupby("Data").size().reset_index(name="Partie")
                    act_df2["Gracz"] = u2
                    act_comb = pd.concat([act_df1, act_df2])
                    
                    fig_act_c = px.bar(act_comb, x="Data", y="Partie", color="Gracz", barmode="group", color_discrete_sequence=["#1e88e5", "#ef553b"])
                    fig_act_c.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title=None))
                    st.plotly_chart(fig_act_c, use_container_width=True)

            with tabs[2]:
                c_t1, c_t2 = st.columns(2)
                if not df_f.empty and not df2_c.empty:
                    h_df1 = df_f.groupby("Godzina").size().reset_index(name="Partie")
                    h_df1["Gracz"] = u1
                    h_df2 = df2_c.groupby("Godzina").size().reset_index(name="Partie")
                    h_df2["Gracz"] = u2
                    h_comb = pd.concat([h_df1, h_df2])
                    
                    fig_h = px.bar(h_comb, x="Godzina", y="Partie", color="Gracz", barmode="group", title="O jakich porach najczęściej gracie?", color_discrete_sequence=["#1e88e5", "#ef553b"])
                    fig_h.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
                    c_t1.plotly_chart(fig_h, use_container_width=True)
                
                if not df_f.empty and not df2_c.empty:
                    df_f["Bin"] = df_f["Ruchy"].apply(get_duration_bin)
                    df2_c["Bin"] = df2_c["Ruchy"].apply(get_duration_bin)
                    
                    b_df1 = df_f.groupby("Bin").size().reset_index(name="Ilość")
                    b_df1["Gracz"] = u1
                    b_df2 = df2_c.groupby("Bin").size().reset_index(name="Ilość")
                    b_df2["Gracz"] = u2
                    b_comb = pd.concat([b_df1, b_df2])
                    
                    order = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
                    fig_b = px.bar(b_comb.sort_values("Bin", key=lambda x: [order.index(i) for i in x]), x="Bin", y="Ilość", color="Gracz", barmode="group", title="Jak długie partie rozgrywacie?", color_discrete_sequence=["#1e88e5", "#ef553b"])
                    c_t2.plotly_chart(fig_b, use_container_width=True)

            with tabs[3]:
                c_o1, c_o2 = st.columns(2)
                with c_o1:
                    st.write(f"### 🛡️ Grupy Debiutów: {u1}")
                    if not df_f.empty:
                        st.info(f"**Rozegrane unikalne grupy:** {df_f['Debiut_Grupa'].nunique()}")
                        op_g1 = df_f.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g1.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)
                with c_o2:
                    st.write(f"### 🛡️ Grupy Debiutów: {u2}")
                    if not df2_c.empty:
                        st.info(f"**Rozegrane unikalne grupy:** {df2_c['Debiut_Grupa'].nunique()}")
                        op_g2 = df2_c.groupby("Debiut_Grupa").agg(Gry=('Wynik', 'count'), WinRate=('Wynik', lambda x: int(round((x == 'Wygrane').sum()/len(x)*100,0)))).reset_index()
                        st.dataframe(op_g2.sort_values("Gry", ascending=False).head(15), use_container_width=True, hide_index=True)

            if len(tabs) > 4:
                with tabs[4]:
                    h2 = df_f[(df_f['Przeciwnik'].str.lower() == u2.lower()) & (df_f['Platforma'] == p2_p)].copy().sort_values("Timestamp").reset_index(drop=True)
                    if not h2.empty:
                        h2_w, h2_d, h2_l = (h2["Wynik"] == "Wygrane").sum(), (h2["Wynik"] == "Remisy").sum(), (h2["Wynik"] == "Przegrane").sum()
                        
                        st.markdown(f"""
                        <div class="asym-header" style="font-size:1.1rem;">
                            <div style="width:30%; text-align:center; color:#1e88e5;">{u1} ({h2_w})</div>
                            <div style="width:40%; text-align:center; color:#8b949e;">REMISY: {h2_d} | RAZEM: {len(h2)}</div>
                            <div style="width:30%; text-align:center; color:#ef553b;">{u2} ({h2_l})</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.write("")
                        
                        h2["Partia_Nr"] = h2.index + 1
                        h2["Ty"], h2[u2] = (h2["Wynik"]=="Wygrane").cumsum(), (h2["Wynik"]=="Przegrane").cumsum()
                        
                        fig_h2h = px.line(h2.melt(id_vars=["Partia_Nr"], value_vars=["Ty", u2]), x="Partia_Nr", y="value", color="variable", title="Wyścig zwycięstw H2H", color_discrete_sequence=["#1e88e5", "#ef553b"])
                        fig_h2h.update_layout(xaxis_title="Numer partii", yaxis_title="Suma wygranych", legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, title=None))
                        st.plotly_chart(fig_h2h, use_container_width=True)
                        
                        st.write("**Historia spotkań:**")
                        st.dataframe(h2[["Data", "Tryb", "Kolor", "Wynik", "Ruchy", "Debiut"]].sort_values("Data", ascending=False), use_container_width=True, hide_index=True)
                    else: st.info(f"Brak zarejestrowanych bezpośrednich partii pomiędzy **{u1}** a **{u2}** (przy obecnych filtrach).")
