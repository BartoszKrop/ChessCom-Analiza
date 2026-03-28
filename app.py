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
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POMOCNICZE ---
def extract_opening(pgn):
    if not pgn: return "Nieznany"
    match = re.search(r'openings/(.*?)"', pgn)
    if match:
        return match.group(1).replace('-', ' ').capitalize()
    return "Inny"

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    try:
        headers = {"User-Agent": f"ChessApp-Final-v4-{user}"}
        p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers)
        s_res = requests.get(f"https://api.chess.com/pub/player/{user}/stats", headers=headers)
        a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers)
        
        if p_res.status_code != 200: return None, None, None
        
        p_data, s_data = p_res.json(), s_res.json()
        archives = a_res.json().get("archives", [])
        all_games = []
        
        days_map = {0: 'Poniedziałek', 1: 'Wtorek', 2: 'Środa', 3: 'Czwartek', 4: 'Piątek', 5: 'Sobota', 6: 'Niedziela'}

        for url in archives:
            m_data = requests.get(url, headers=headers).json()
            for g in m_data.get("games", []):
                if "end_time" in g:
                    ts = datetime.fromtimestamp(g["end_time"])
                    is_w = g["white"]["username"].lower() == user.lower()
                    res = g["white" if is_w else "black"]["result"]
                    my_r = g["white" if is_w else "black"].get("rating", 0)
                    out = "Wygrane" if res == "win" else ("Remisy" if res in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"] else "Przegrane")
                    
                    all_games.append({
                        "Timestamp": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc_Klucz": ts.strftime("%Y-%m"), "Miesiąc_Format": ts.strftime("%m/%Y"),
                        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, "Elo_Moje": my_r,
                        "Debiut": extract_opening(g.get("pgn", ""))
                    })
        return p_data, s_data, pd.DataFrame(all_games)
    except:
        return None, None, None

# --- OBSŁUGA PAMIĘCI (SESSION STATE) ---
if 'user_data' not in st.session_state:
    st.session_state.user_data = None

# --- SIDEBAR ---
with st.sidebar:
    st.title("♟️ Chess Pro")
    input_user = st.text_input("Użytkownik Chess.com:").strip()
    if st.button("Analizuj"):
        with st.spinner("Pobieranie danych..."):
            st.session_state.user_data = fetch_data(input_user)
            st.session_state.current_user = input_user

# --- LOGIKA WYŚWIETLANIA ---
if st.session_state.user_data:
    profile, stats, df = st.session_state.user_data
    username = st.session_state.current_user
    
    if df is not None and not df.empty:
        # Nagłówek
        avatar = profile.get("avatar")
        col_h1, col_h2 = st.columns([1, 7])
        if avatar: col_h1.image(avatar, width=100)
        col_h2.title(username)

        def get_elo_v(cat):
            s = stats.get(cat, {})
            best = s.get('best', {}).get('rating', '-')
            last = s.get('last', {}).get('rating', '-')
            return f"{best} / {last}"

        m1, m2, m3 = st.columns(3)
        m1.metric("Rapid (Peak/Teraz)", get_elo_v("chess_rapid"))
        m2.metric("Blitz (Peak/Teraz)", get_elo_v("chess_blitz"))
        m3.metric("Bullet (Peak/Teraz)", get_elo_v("chess_bullet"))

        st.divider()

        # --- FILTRY ---
        with st.expander("⚙️ Filtry analizy"):
            f_c1, f_c2 = st.columns(2)
            d_range = f_c1.date_input("Zakres dat:", value=(df["Data"].min(), df["Data"].max()))
            s_mode = f_c1.selectbox("Globalny tryb gry:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))
            days_list = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
            s_days = f_c2.multiselect("Dni tygodnia:", days_list, default=days_list)
            s_hours = f_c2.slider("Godziny:", 0, 23, (0, 23))

        # Filtrowanie
        df_f = df.copy()
        if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
            df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
        df_f = df_f[df_f["Dzień"].isin(s_days)]
        df_f = df_f[(df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1])]
        if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

        if not df_f.empty:
            tab1, tab2, tab3, tab4 = st.tabs(["📊 Statystyki", "📅 Historia", "⏳ Czas", "🔬 Debiuty"])
            
            with tab1:
                w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
                wr = int(round((w/len(df_f))*100, 0))
                k1, k2, k3 = st.columns(3)
                k1.metric("Ilość gier", len(df_f))
                k2.metric("Bilans (W/R/P)", f"{w}/{d}/{l}")
                k3.metric("Win Rate", f"{wr}%")
                
                c_1, c_2 = st.columns([1, 2])
                c_1.plotly_chart(px.pie(df_f, names="Wynik", hole=0.5, color="Wynik", color_discrete_map={"Wygrane":"#00cc96","Przegrane":"#ef553b","Remisy":"#7f7f7f"}), use_container_width=True)
                act = df_f.groupby(["Data", "Wynik"]).size().reset_index(name="n")
                c_2.plotly_chart(px.bar(act, x="Data", y="n", color="Wynik", color_discrete_map={"Wygrane":"#00cc96","Przegrane":"#ef553b","Remisy":"#7f7f7f"}), use_container_width=True)

                st.divider()
                st.write("Historia ELO ")
                
                # Wyświetlanie 3 wykresów ELO
                for mode in ["Rapid", "Blitz", "Bullet"]:
                    mode_df = df_f[df_f["Tryb"] == mode].sort_values("Timestamp")
                    if not mode_df.empty:
                        fig = px.line(mode_df, x="Timestamp", y="Elo_Moje", title=f"{mode}")
                        fig.update_layout(xaxis_title=None, yaxis_title="ELO", height=300)
                        st.plotly_chart(fig, use_container_width=True)

            with tab2:
                monthly = df_f.groupby(["Miesiąc_Klucz", "Miesiąc_Format"]).agg(W=('Wynik', lambda x: (x == 'Wygrane').sum()), R=('Wynik', lambda x: (x == 'Remisy').sum()), P=('Wynik', lambda x: (x == 'Przegrane').sum()), T=('Wynik', 'count'), E=('Elo_Moje', 'mean')).reset_index()
                monthly["W/R/P"] = monthly.apply(lambda x: f"{int(x['W'])}/{int(x['R'])}/{int(x['P'])}", axis=1)
                monthly["Średnie ELO"] = monthly["E"].round(0).astype(int)
                st.dataframe(monthly[["Miesiąc_Format", "T", "W/R/P", "Średnie ELO"]].rename(columns={"Miesiąc_Format":"Miesiąc", "T":"Ilość gier"}).sort_values("Miesiąc", ascending=False), use_container_width=True, hide_index=True)
                
                st.divider()
                sel_m = st.selectbox("Wybierz miesiąc do szczegółów:", monthly["Miesiąc_Format"].unique())
                day_df = df_f[df_f["Miesiąc_Format"] == sel_m].groupby("Data").agg(W=('Wynik', lambda x: (x == 'Wygrane').sum()), R=('Wynik', lambda x: (x == 'Remisy').sum()), P=('Wynik', lambda x: (x == 'Przegrane').sum()), T=('Wynik', 'count'), E=('Elo_Moje', 'mean')).reset_index()
                day_df["Data_F"] = pd.to_datetime(day_df["Data"]).dt.strftime("%d/%m/%Y")
                day_df["Bilans"] = day_df.apply(lambda x: f"{int(x['W'])}/{int(x['R'])}/{int(x['P'])}", axis=1)
                day_df["Średnie ELO"] = day_df["E"].round(0).astype(int)
                st.dataframe(day_df[["Data_F", "T", "Bilans", "Średnie ELO"]].rename(columns={"Data_F":"Data", "T":"Ilość gier"}).sort_values("Data", ascending=False), use_container_width=True, hide_index=True)

            with tab3:
                navy = ['#ffffff', '#000080']
                d_stats = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
                d_stats["Win Rate %"] = (d_stats["W"] / d_stats["Gry"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(d_stats, x="Dzień", y="Win Rate %", color="Gry", color_continuous_scale=navy, labels={"Gry": "Ilość gier"}, title="Skuteczność wg dni tygodnia"), use_container_width=True)
                
                t_stats = df_f.groupby("Godzina").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                t_stats["Win Rate %"] = (t_stats["W"] / t_stats["Gry"] * 100).round(0).astype(int)
                st.plotly_chart(px.bar(t_stats, x="Godzina", y="Win Rate %", color="Gry", color_continuous_scale=navy, labels={"Gry": "Ilość gier"}, title="Skuteczność wg godzin"), use_container_width=True)

            with tab4:
                op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
                op["Win Rate %"] = (op["W"] / op["Gry"] * 100).round(0).astype(int)
                st.dataframe(op.rename(columns={"Gry":"Ilość gier"}).sort_values("Ilość gier", ascending=False).head(25), use_container_width=True, hide_index=True)
        else:
            st.warning("Brak danych po filtracji.")
else:
    st.info("Wpisz nick i kliknij 'Analizuj'.")