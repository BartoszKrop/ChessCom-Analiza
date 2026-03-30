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
        "agreed": "Remis (Zgoda)",
        "repetition": "Remis (Powtórzenie)",
        "stalemate": "Pat",
        "insufficient": "Brak materiału",
        "timevsinsufficient": "Czas vs Brak Mat.",
        "50move": "Zasada 50 ruchów"
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
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
            "Accept": "application/json"
        }
        res = requests.post(url, data={'pgn': pgn_text}, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("url")
    except:
        pass
    return None

def reset_link():
    st.session_state.current_lichess_url = None

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    try:
        headers = {"User-Agent": f"ChessApp-Analytics-Pro-V14-{user}"}
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
                        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, 
                        "Elo_Moje": my_r, "Elo_Rywala": opp_r, "Ruchy": extract_moves_count(pgn_raw),
                        "Debiut": extract_opening(pgn_raw),
                        "Przeciwnik": opp,
                        "Kolor": "Białe" if is_w else "Czarne",
                        "Powod_Konca": get_end_reason(my_res_raw, opp_res_raw, out),
                        "Roszada": extract_castling(pgn_raw, is_w),
                        "PGN_Raw": pgn_raw
                    })
        return p_data, s_data, pd.DataFrame(all_games)
    except:
        return None, None, None

def render_lichess_button(url, label):
    st.markdown(f"""
    <a href="{url}" target="_blank" style="
        display: block; width: 100%; text-align: center; background-color: #1e88e5; 
        color: white; padding: 12px; border-radius: 8px; text-decoration: none; 
        font-weight: bold; font-size: 16px; border: 1px solid #1565c0;
        margin-top: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    ">{label}</a>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if 'data' not in st.session_state: st.session_state.data = None
if 'user' not in st.session_state: st.session_state.user = ""
if 'current_lichess_url' not in st.session_state: st.session_state.current_lichess_url = None
if 'last_selected_label' not in st.session_state: st.session_state.last_selected_label = None
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
                    st.session_state.data = fetched
                    st.session_state.user = nick
                    st.rerun()
                else: st.error("Błąd pobierania danych. Sprawdź poprawność nicku.")
else:
    profile, stats, df = st.session_state.data
    username = st.session_state.user

    # --- NAWIGACJA GŁÓWNA ---
    col_nav1, col_nav2, col_nav3 = st.columns([2, 1, 1])
    
    with col_nav1:
        new_mode = st.radio(
            "Tryb aplikacji:", 
            ["👤 Moja Analiza", "⚔️ Porównanie Graczy"], 
            horizontal=True, 
            label_visibility="collapsed",
            index=0 if st.session_state.app_mode == "👤 Moja Analiza" else 1
        )
        
    with col_nav2:
        if st.button("🔄 Odśwież dane", use_container_width=True):
            with st.spinner("Pobieranie najnowszych partii..."):
                fetch_data.clear()
                fetched = fetch_data(username)
                if fetched[2] is not None and not fetched[2].empty:
                    st.session_state.data = fetched
                    st.session_state.current_lichess_url = None
                    st.rerun()
                else:
                    st.error("Wystąpił błąd podczas odświeżania.")

    with col_nav3:
        if st.button("🚪 Zmień gracza", use_container_width=True):
            st.session_state.data = None
            st.session_state.data2 = None
            st.session_state.current_lichess_url = None
            st.rerun()
            
    if new_mode != st.session_state.app_mode:
        st.session_state.app_mode = new_mode
        st.session_state.current_lichess_url = None
        st.rerun()
        
    st.divider()

    # ==========================================
    # TRYB 1: MOJA ANALIZA
    # ==========================================
    if st.session_state.app_mode == "👤 Moja Analiza":
        avatar = profile.get("avatar")
        c_h1, c_h2 = st.columns([1, 4])
        if avatar: c_h1.image(avatar, width=70)
        c_h2.subheader(username)

        def get_elo_v(cat):
            s = stats.get(cat, {})
            return f"{s.get('best', {}).get('rating', '-')} / {s.get('last', {}).get('rating', '-')}"

        m1, m2, m3 = st.columns(3)
        m1.metric("Rapid (Peak vs Obecnie)", get_elo_v("chess_rapid"))
        m2.metric("Blitz (Peak vs Obecnie)", get_elo_v("chess_blitz"))
        m3.metric("Bullet (Peak vs Obecnie)", get_elo_v("chess_bullet"))

        with st.expander("⚙️ Filtry"):
            col_f1, col_f2 = st.columns(2)
            d_range = col_f1.date_input("Zakres dat:", value=(df["Data"].min(), df["Data"].max()))
            s_mode = col_f2.selectbox("Tryb gry:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            
            s_color = st.multiselect("Kolor gracza:", ["Białe", "Czarne"], default=["Białe", "Czarne"])
            
            days_list = ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd']
            s_days = st.multiselect("Dni tygodnia:", days_list, default=days_list)
            s_hours = st.slider("Godziny:", 0, 23, (0, 23))

        df_f = df.copy()
        if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
            df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
        df_f = df_f[df_f["Kolor"].isin(s_color)]
        df_f = df_f[df_f["Dzień"].isin(s_days)]
        df_f = df_f[(df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1])]
        if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

        # EKSPORT PGN
        if not df_f.empty:
            pgn_export = "\n\n".join(df_f["PGN_Raw"].dropna().tolist())
            st.download_button(
                label=f"📥 Pobierz bazę {len(df_f)} partii (Format PGN)",
                data=pgn_export,
                file_name=f"Chess_Export_{username}_{datetime.now().strftime('%Y%m%d')}.pgn",
                mime="text/plain",
                use_container_width=True
            )

        if not df_f.empty:
            # Aktualizacja struktury zakładek
            tab1, tab_tech, tab3, tab4, tab_asym, tab_styl, tab5 = st.tabs(["📊 Statystyki", "🏁 Technika", "⏳ Czas gry", "🔬 Debiuty", "⚖️ Asymetria", "🧩 Styl & Tilt", "🧠 Analiza partii"])
            
            with tab1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Ilość rozegranych partii", len(df_f))
                k2.metric("W/R/P", f"{w}/{d}/{l}")
                k3.metric("Win%", f"{int(round((w/len(df_f))*100, 0))}%")
                
                st.write("#### Historia rankingu i Bieżąca Forma")
                st.caption("Linia przerywana to tzw. Średnia Krocząca (SMA) z 10 ostatnich gier.")
                
                for mode in ["Rapid", "Blitz", "Bullet"]:
                    m_df = df_f[df_f["Tryb"] == mode].sort_values("Timestamp").copy()
                    if not m_df.empty:
                        m_df['Trend (10 gier)'] = m_df['Elo_Moje'].rolling(window=10, min_periods=1).mean()
                        fig_elo = px.line(m_df, x="Timestamp", y=["Elo_Moje", "Trend (10 gier)"], title=f"Tryb: {mode}",
                                          color_discrete_map={"Elo_Moje": "#1e88e5", "Trend (10 gier)": "#00cc96"})
                        fig_elo.update_traces(line=dict(dash="dash"), selector=dict(name="Trend (10 gier)"))
                        fig_elo.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO", legend_title_text="")
                        st.plotly_chart(fig_elo, use_container_width=True)

            with tab_tech:
                st.write("### 🛑 Powody zakończenia partii")
                c_end1, c_end2 = st.columns(2)
                
                with c_end1:
                    st.write("**Gdy WYGRYWASZ:**")
                    df_win = df_f[df_f["Wynik"] == "Wygrane"]
                    if not df_win.empty:
                        fig_w = px.pie(df_win, names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                        fig_w.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                        st.plotly_chart(fig_w, use_container_width=True)
                    else:
                        st.info("Brak wygranych w wybranym filtrze.")

                with c_end2:
                    st.write("**Gdy PRZEGRYWASZ:**")
                    df_lose = df_f[df_f["Wynik"] == "Przegrane"]
                    if not df_lose.empty:
                        fig_l = px.pie(df_lose, names="Powod_Konca", hole=0.4, color_discrete_sequence=px.colors.sequential.Reds)
                        fig_l.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                        st.plotly_chart(fig_l, use_container_width=True)
                    else:
                        st.info("Brak przegranych w wybranym filtrze.")

                st.divider()
                st.write("### 🏰 Strategia Roszady")
                cast_stats = df_f.groupby("Roszada").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                cast_stats["Win%"] = (cast_stats["W"] / cast_stats["Gry"] * 100).round(0).astype(int)
                
                fig_cast = px.bar(cast_stats, x="Roszada", y="Win%", color="Gry", 
                               labels={"Gry": "Ilość partii", "Roszada": "Typ roszady"},
                               color_continuous_scale=['#ffffff', '#000080'])
                fig_cast.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_cast, use_container_width=True)

            with tab3:
                st.write("### 🗺️ Heatmapa Godzin Chwały (Kiedy idzie najlepiej?)")
                st.caption("Ciemnoniebieski kolor oznacza wyższy Win Rate.")
                
                hm_df = df_f.groupby(["Dzień", "Dzień_Nr", "Godzina"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                hm_df["Win%"] = (hm_df["W"] / hm_df["Gry"] * 100).round(0)
                
                pivot_hm = hm_df.pivot(index="Dzień_Nr", columns="Godzina", values="Win%").reindex(range(7)).reindex(columns=range(24))
                pivot_hm.index = ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd']
                
                fig_hm = px.imshow(pivot_hm, text_auto=True, color_continuous_scale="Blues", 
                                   labels=dict(x="Godzina (0-23)", y="Dzień", color="Win%"), aspect="auto")
                fig_hm.update_xaxes(side="top", dtick=1)
                fig_hm.update_layout(margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_hm, use_container_width=True)

            with tab4:
                st.write("### 📖 Ogólna skuteczność debiutów")
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                op["Win%"] = (op["W"] / op["Gry"] * 100).round(0).astype(int)
                st.dataframe(op[["Debiut", "Gry", "Win%"]].rename(columns={"Gry": "Ilość partii"}).sort_values("Ilość partii", ascending=False).head(15), use_container_width=True, hide_index=True)
                
                st.divider()

                # --- NOWOŚĆ: Ewolucja Repertuaru ---
                st.write("### 🧬 Ewolucja Repertuaru w czasie")
                st.caption("Jak często wybierałeś swoje najpopularniejsze debiuty z biegiem miesięcy.")
                top_openings = op.sort_values("Gry", ascending=False).head(7)["Debiut"].tolist()
                
                df_evo = df_f.copy()
                df_evo["Grupa_Debiutow"] = df_evo["Debiut"].apply(lambda x: x if x in top_openings else "Inne")
                evo_stats = df_evo.groupby(["Miesiąc_Klucz", "Grupa_Debiutow"]).size().reset_index(name="Ilość partii")
                
                fig_evo = px.bar(evo_stats, x="Miesiąc_Klucz", y="Ilość partii", color="Grupa_Debiutow", 
                                 title="Twój styl na osi czasu", color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_evo.update_layout(xaxis_title="Miesiąc", yaxis_title="Rozegrane gry", margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_evo, use_container_width=True)

                st.divider()
                
                c_deb1, c_deb2 = st.columns(2)
                with c_deb1:
                    st.write("### 🔥 Killer Openings")
                    st.caption("Masakrujesz rywala w **poniżej 25 ruchów**.")
                    killer_df = df_f[(df_f["Wynik"] == "Wygrane") & (df_f["Ruchy"] <= 25)]
                    if not killer_df.empty:
                        kop = killer_df.groupby("Debiut").size().reset_index(name="Ilość masakr")
                        kop = kop.sort_values("Ilość masakr", ascending=False).head(10)
                        st.dataframe(kop, use_container_width=True, hide_index=True)
                    else:
                        st.info("Brak tak szybkich zwycięstw.")

                with c_deb2:
                    st.write("### 💀 Kryptonit (Słabe punkty)")
                    st.caption("Twój Win Rate wynosi **40% lub mniej** (min. 3 partie).")
                    krypt_df = op[(op["Gry"] >= 3) & (op["Win%"] <= 40)].sort_values(["Win%", "Gry"], ascending=[True, False]).head(10)
                    if not krypt_df.empty:
                        st.dataframe(krypt_df[["Debiut", "Gry", "Win%"]].rename(columns={"Gry": "Ilość partii"}), use_container_width=True, hide_index=True)
                    else:
                        st.success("Brak kryptonitu! Ze wszystkim radzisz sobie powyżej 40%.")

            # --- NOWA ZAKŁADKA: ASYMETRIA ---
            with tab_asym:
                st.write("### ⚖️ Asymetria Kolorów: Białe vs Czarne")
                st.caption("Czy istnieje u Ciebie przepaść między graniem białymi bierkami a czarnymi?")
                
                c_asym_w, c_asym_b = st.columns(2)
                df_w = df_f[df_f["Kolor"] == "Białe"]
                df_b = df_f[df_f["Kolor"] == "Czarne"]
                
                def get_color_stats(d_col):
                    if d_col.empty: return None
                    w_count = (d_col["Wynik"] == "Wygrane").sum()
                    wr = int(round(w_count / len(d_col) * 100, 0))
                    avg_moves = int(d_col["Ruchy"].mean())
                    top_loses = d_col[d_col["Wynik"] == "Przegrane"]
                    top_end = top_loses["Powod_Konca"].mode().iloc[0] if not top_loses.empty else "Brak porażek!"
                    return wr, len(d_col), avg_moves, top_end

                sw = get_color_stats(df_w)
                sb = get_color_stats(df_b)

                with c_asym_w:
                    st.info("⬜ **BIAŁE BIERKI**")
                    if sw:
                        st.metric("Win Rate Białymi", f"{sw[0]}%")
                        st.metric("Rozegrane partie", sw[1])
                        st.metric("Średnia długość gry", f"{sw[2]} ruchów")
                        st.metric("Najczęstsza porażka przez", sw[3])
                    else:
                        st.write("Brak danych dla białych w tym filtrze.")

                with c_asym_b:
                    # Używamy success dla innego koloru wizualnego
                    st.success("⬛ **CZARNE BIERKI**")
                    if sb:
                        st.metric("Win Rate Czarnymi", f"{sb[0]}%")
                        st.metric("Rozegrane partie", sb[1])
                        st.metric("Średnia długość gry", f"{sb[2]} ruchów")
                        st.metric("Najczęstsza porażka przez", sb[3])
                    else:
                        st.write("Brak danych dla czarnych w tym filtrze.")

                st.divider()
                st.write("### 📈 Wyścig Skuteczności (Białe vs Czarne w czasie)")
                st.caption("Zobacz, którym kolorem szło Ci lepiej w poszczególnych miesiącach.")
                
                color_monthly = df_f.groupby(["Miesiąc_Klucz", "Kolor"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x=='Wygrane').sum())).reset_index()
                color_monthly["Win%"] = (color_monthly["W"] / color_monthly["Gry"] * 100).round(0).astype(int)
                
                # Zastosowałem specjalne, ostre kolory, żeby dobrze wyglądało na ciemnym tle Streamlita
                fig_c_month = px.line(color_monthly, x="Miesiąc_Klucz", y="Win%", color="Kolor", markers=True, 
                                      color_discrete_map={"Białe": "#e0e0e0", "Czarne": "#636efa"})
                fig_c_month.update_layout(xaxis_title="Miesiąc", yaxis_title="Win Rate (%)", margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_c_month, use_container_width=True)

            with tab_styl:
                st.write("### ⏱️ Długodystansowiec czy Sprinter?")
                df_f["Przedział_Ruchów"] = df_f["Ruchy"].apply(get_duration_bin)
                dur_stats = df_f.groupby("Przedział_Ruchów").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                dur_stats["Win%"] = (dur_stats["W"] / dur_stats["Gry"] * 100).round(0).astype(int)
                
                dur_stats["SortKey"] = dur_stats["Przedział_Ruchów"].apply(lambda x: sort_duration_bins([x])[0])
                dur_stats = dur_stats.sort_values(by="SortKey", key=lambda col: [sort_duration_bins(list(col)).index(x) for x in col]).drop("SortKey", axis=1)

                fig_dur = px.bar(dur_stats, x="Przedział_Ruchów", y="Win%", color="Gry", 
                               labels={"Gry": "Ilość partii", "Przedział_Ruchów": "Ilość ruchów w meczu"},
                               color_continuous_scale=['#ffffff', '#000080'])
                fig_dur.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_dur, use_container_width=True)

                st.divider()

                st.write("### 🥊 Gra pod presją (Underdog vs Faworyt)")
                df_f["Roznica_ELO"] = df_f["Elo_Moje"] - df_f["Elo_Rywala"]
                df_f["Kategoria_Presji"] = df_f["Roznica_ELO"].apply(get_elo_bin)
                
                pres_stats = df_f.groupby("Kategoria_Presji").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                pres_stats["Win%"] = (pres_stats["W"] / pres_stats["Gry"] * 100).round(0).astype(int)
                pres_stats = pres_stats.sort_values("Kategoria_Presji")

                fig_pres = px.bar(pres_stats, x="Win%", y="Kategoria_Presji", color="Gry", orientation='h',
                               labels={"Gry": "Ilość partii", "Kategoria_Presji": "Klasyfikacja meczu"},
                               color_continuous_scale=['#ffffff', '#000080'])
                fig_pres.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_pres, use_container_width=True)

                st.divider()

                st.write("### 📉 Analiza Tiltu i Momentum")
                
                df_tilt = df_f.sort_values('Timestamp').copy()
                
                streaks_type = []
                streaks_count = []
                c_type = None
                c_count = 0
                
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
                            wr = int(round((w_count / len(subset)) * 100, 0))
                            tilt_stats.append({"Typ": nazwa, "Długość serii (przed meczem)": f"{count} z rzędu", "Win%": wr, "Gry": len(subset)})
                    
                    subset_4 = df_tilt[(df_tilt['Seria_Typ'] == stype) & (df_tilt['Seria_Dlugosc'] >= 4)]
                    if len(subset_4) > 0:
                        w_count = (subset_4['Wynik'] == 'Wygrane').sum()
                        wr = int(round((w_count / len(subset_4)) * 100, 0))
                        tilt_stats.append({"Typ": nazwa, "Długość serii (przed meczem)": "4+ z rzędu", "Win%": wr, "Gry": len(subset_4)})

                if tilt_stats:
                    df_tilt_res = pd.DataFrame(tilt_stats)
                    fig_tilt = px.bar(df_tilt_res, x="Długość serii (przed meczem)", y="Win%", color="Typ", barmode='group',
                                     text="Win%",
                                     color_discrete_map={"Po serii Wygranych":"#00cc96", "Po serii Porażek":"#ef553b"})
                    fig_tilt.update_traces(textposition='outside')
                    fig_tilt.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig_tilt, use_container_width=True)
                else:
                    st.info("Za mało gier do narysowania wykresu serii.")

            with tab5:
                st.write("### 🧠 Analiza partii")
                
                c1, c2 = st.columns(2)
                with c1: 
                    search_date = st.date_input("Dzień partii (jeśli nick pusty):", value=df_f["Data"].max() if not df_f.empty else df["Data"].max())
                with c2: 
                    search_opp = st.text_input("Nick przeciwnika (override daty):").strip()

                if search_opp:
                    df_ana = df_f[df_f["Przeciwnik"].str.lower() == search_opp.lower()]
                else:
                    df_ana = df_f[df_f["Data"] == search_date]

                if not df_ana.empty:
                    df_ana["Label"] = df_ana.apply(lambda x: f"{x['Data']} | {x['Godzina']}:00 | {x['Tryb']} vs {x['Przeciwnik']} ({x['Wynik']})", axis=1)
                    sel_label = st.selectbox("Wybierz partię z listy:", df_ana.sort_values("Timestamp", ascending=False)["Label"], key="main_game_select", on_change=reset_link)
                    sel_game = df_ana[df_ana["Label"] == sel_label].iloc[0]
                    
                    st.info(f"Grasz jako: **{sel_game['Kolor']}** | Debiut: **{sel_game['Debiut']}**")
                    st.divider()
                    
                    if st.button("🚀 Przygotuj analizę", use_container_width=True):
                        with st.spinner("Łączenie z Lichess..."):
                            link = import_to_lichess(sel_game["PGN_Raw"])
                            if link:
                                st.session_state.current_lichess_url = link
                                st.rerun() 
                            else:
                                st.error("Wystąpił błąd połączenia. Lichess odrzucił żądanie.")

                    if st.session_state.current_lichess_url:
                        btn_label = f"➡️ ANALIZA PARTII: {sel_game['Przeciwnik']} ({sel_game['Data']})"
                        render_lichess_button(st.session_state.current_lichess_url, btn_label)
                else:
                    st.warning("Nie znaleziono partii.")

    # ==========================================
    # TRYB 2: PORÓWNANIE GRACZY
    # ==========================================
    elif st.session_state.app_mode == "⚔️ Porównanie Graczy":
        
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            st.info(f"**Twój profil:** {username}")
        with c_p2:
            nick2 = st.text_input("Wpisz nick rywala:", value=st.session_state.user2, placeholder="Wpisz nick znajomego", label_visibility="collapsed")
            if st.button("🚀 Pobierz dane rywala", use_container_width=True):
                if nick2:
                    with st.spinner(f"Pobieranie historii gier dla {nick2}..."):
                        f2 = fetch_data(nick2)
                        if f2[2] is not None and not f2[2].empty:
                            st.session_state.data2 = f2
                            st.session_state.user2 = nick2
                            st.rerun()
                        else:
                            st.error(f"Nie udało się pobrać danych dla {nick2}. Sprawdź poprawność nicku.")

        if st.session_state.data2 is not None:
            p1, s1, d1 = st.session_state.data
            p2, s2, d2 = st.session_state.data2
            u1 = username
            u2 = st.session_state.user2

            with st.expander("⚙️ Filtry"):
                col_c1, col_c2 = st.columns(2)
                d_range_c = col_c1.date_input("Zakres dat:", value=(d1["Data"].min(), d1["Data"].max()), key="c_date")
                s_mode_c = col_c2.selectbox("Tryb gry:", ["Wszystkie"] + sorted(d1["Tryb"].unique().tolist()), key="c_mode")
                
                s_color_c = st.multiselect("Kolor gracza:", ["Białe", "Czarne"], default=["Białe", "Czarne"], key="c_color")
                
                days_list_c = ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd']
                s_days_c = st.multiselect("Dni tygodnia:", days_list_c, default=days_list_c, key="c_days")
                s_hours_c = st.slider("Godziny:", 0, 23, (0, 23), key="c_hours")

            d1_f = d1.copy()
            d2_f = d2.copy()
            
            if isinstance(d_range_c, (list, tuple)) and len(d_range_c) == 2:
                d1_f = d1_f[(d1_f["Data"] >= d_range_c[0]) & (d1_f["Data"] <= d_range_c[1])]
                d2_f = d2_f[(d2_f["Data"] >= d_range_c[0]) & (d2_f["Data"] <= d_range_c[1])]
                
            d1_f = d1_f[d1_f["Kolor"].isin(s_color_c)]
            d2_f = d2_f[d2_f["Kolor"].isin(s_color_c)]
            
            d1_f = d1_f[d1_f["Dzień"].isin(s_days_c)]
            d2_f = d2_f[d2_f["Dzień"].isin(s_days_c)]
            
            d1_f = d1_f[(d1_f["Godzina"] >= s_hours_c[0]) & (d1_f["Godzina"] <= s_hours_c[1])]
            d2_f = d2_f[(d2_f["Godzina"] >= s_hours_c[0]) & (d2_f["Godzina"] <= s_hours_c[1])]
            
            if s_mode_c != "Wszystkie": 
                d1_f = d1_f[d1_f["Tryb"] == s_mode_c]
                d2_f = d2_f[d2_f["Tryb"] == s_mode_c]

            t_ogolne, t_h2h = st.tabs(["📊 Ogólne Informacje", "🥊 Head-to-Head"])

            with t_ogolne:
                st.write("### 🏆 Aktualne ELO")
                
                def get_curr_elo(stat_dict, mode):
                    return stat_dict.get(mode, {}).get('last', {}).get('rating', 0)

                c1, c2, c3 = st.columns(3)
                r1, r2 = get_curr_elo(s1, "chess_rapid"), get_curr_elo(s2, "chess_rapid")
                b1, b2 = get_curr_elo(s1, "chess_blitz"), get_curr_elo(s2, "chess_blitz")
                bl1, bl2 = get_curr_elo(s1, "chess_bullet"), get_curr_elo(s2, "chess_bullet")
                
                c1.metric(f"Rapid: {u1} vs {u2}", f"{r1} / {r2}", int(r1 - r2) if r1 and r2 else None)
                c2.metric(f"Blitz: {u1} vs {u2}", f"{b1} / {b2}", int(b1 - b2) if b1 and b2 else None)
                c3.metric(f"Bullet: {u1} vs {u2}", f"{bl1} / {bl2}", int(bl1 - bl2) if bl1 and bl2 else None)

                st.write("### 📊 Ogólny Win Rate")
                wr1 = int(round(((d1_f["Wynik"] == "Wygrane").sum() / len(d1_f)) * 100, 0)) if len(d1_f) > 0 else 0
                wr2 = int(round(((d2_f["Wynik"] == "Wygrane").sum() / len(d2_f)) * 100, 0)) if len(d2_f) > 0 else 0
                
                c4, c5 = st.columns(2)
                c4.metric(f"Win Rate: {u1} vs {u2}", f"{wr1}% / {wr2}%", f"{wr1 - wr2}%" if len(d2_f) > 0 else None)
                c5.metric("Ilość rozegranych partii", f"{len(d1_f)} / {len(d2_f)}")

                st.write("### 📈 Wyścig ELO w czasie")
                
                d1_copy = d1_f.copy()
                d1_copy['Gracz'] = u1
                d2_copy = d2_f.copy()
                d2_copy['Gracz'] = u2
                df_comp = pd.concat([d1_copy, d2_copy])

                for mode in ["Rapid", "Blitz", "Bullet"]:
                    m_df = df_comp[df_comp["Tryb"] == mode].sort_values("Timestamp")
                    if not m_df.empty:
                        fig_comp = px.line(m_df, x="Timestamp", y="Elo_Moje", color="Gracz", title=f"Porównanie: {mode}")
                        fig_comp.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None, yaxis_title="ELO")
                        st.plotly_chart(fig_comp, use_container_width=True)

            with t_h2h:
                h2h_df = d1_f[d1_f['Przeciwnik'].str.lower() == u2.lower()].copy()
                
                if h2h_df.empty:
                    st.info(f"Brak zarejestrowanych partii bezpośrednich pomiędzy **{u1}** a **{u2}** (sprawdź filtry wyżej).")
                else:
                    h2h_df = h2h_df.sort_values("Timestamp").reset_index(drop=True)
                    h2h_df["Numer partii"] = h2h_df.index + 1
                    
                    h2h_w = (h2h_df["Wynik"] == "Wygrane").sum()
                    h2h_d = (h2h_df["Wynik"] == "Remisy").sum()
                    h2h_l = (h2h_df["Wynik"] == "Przegrane").sum()
                    
                    st.write("### 🥊 Bilans bezposredni")
                    c_h1, c_h2, c_h3 = st.columns(3)
                    c_h1.metric(f"Wygrane ({u1})", h2h_w)
                    c_h2.metric("Remisy", h2h_d)
                    c_h3.metric(f"Wygrane ({u2})", h2h_l)
                    
                    st.write("### 📈 Wyścig Zwycięstw")
                    h2h_df[f"Zwycięstwa {u1}"] = (h2h_df["Wynik"] == "Wygrane").cumsum()
                    h2h_df[f"Zwycięstwa {u2}"] = (h2h_df["Wynik"] == "Przegrane").cumsum() 
                    
                    chart_df = h2h_df[["Numer partii", f"Zwycięstwa {u1}", f"Zwycięstwa {u2}"]].melt(
                        id_vars=["Numer partii"], var_name="Gracz", value_name="Suma Zwycięstw"
                    )
                    
                    fig_h2h = px.line(chart_df, x="Numer partii", y="Suma Zwycięstw", color="Gracz", markers=True)
                    fig_h2h.update_layout(
                        xaxis_title="Ilość rozegranych partii", 
                        yaxis_title="Liczba Zwycięstw",
                        height=350,
                        margin=dict(l=0, r=0, t=30, b=0)
                    )
                    st.plotly_chart(fig_h2h, use_container_width=True)

                    st.divider()
                    st.write("### 🔬 Przeanalizuj wasze starcie")
                    h2h_df["Label"] = h2h_df.apply(lambda x: f"{x['Data']} | {x['Tryb']} ({x['Wynik']})", axis=1)
                    
                    sel_h2h_label = st.selectbox("Wybierz partię z historii H2H:", h2h_df.sort_values("Timestamp", ascending=False)["Label"], key="h2h_game_select", on_change=reset_link)
                    sel_h2h_game = h2h_df[h2h_df["Label"] == sel_h2h_label].iloc[0]
                    
                    if st.button("🚀 Przygotuj analizę H2H", use_container_width=True):
                        with st.spinner("Łączenie z Lichess..."):
                            link = import_to_lichess(sel_h2h_game["PGN_Raw"])
                            if link:
                                st.session_state.current_lichess_url = link
                                st.rerun()
                            else:
                                st.error("Wystąpił błąd połączenia.")
                    
                    if st.session_state.current_lichess_url:
                        btn_label = f"➡️ ANALIZA H2H: {u1} vs {u2} ({sel_h2h_game['Data']})"
                        render_lichess_button(st.session_state.current_lichess_url, btn_label)
