import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import re
import pytz

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
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; color: #ffffff; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    
    .block-container {
        padding: 1rem;
    }
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
    # Pamiętaj, żeby wpisać tu swój prawdziwy email, by uniknąć bana od Chess.com
    headers = {"User-Agent": f"ChessAnalyticsApp / twojmail@domena.pl / username: {user}"}
    
    try:
        p_res = requests.get(f"https://api.chess.com/pub/player/{user}", headers=headers, timeout=10)
        s_res = requests.get(f"https://api.chess.com/pub/player/{user}/stats", headers=headers, timeout=10)
        a_res = requests.get(f"https://api.chess.com/pub/player/{user}/games/archives", headers=headers, timeout=10)
        
        if p_res.status_code != 200: 
            return None, None, None
            
        p_data = p_res.json()
        s_data = s_res.json()
        archives = a_res.json().get("archives", [])
        all_games = []
        
        days_map = {0: 'Pn', 1: 'Wt', 2: 'Śr', 3: 'Czw', 4: 'Pt', 5: 'Sb', 6: 'Nd'}
        
        # Strefa czasowa dla Polski
        warsaw_tz = pytz.timezone('Europe/Warsaw')

        # Pobieramy 6 ostatnich miesięcy
        for url in archives[-6:]: 
            m_res = requests.get(url, headers=headers, timeout=10)
            if m_res.status_code != 200:
                continue
                
            m_data = m_res.json()
            for g in m_data.get("games", []):
                if "end_time" in g:
                    # Nowoczesny i bezpieczny sposób na konwersję timestampu do strefy czasowej
                    ts_utc = datetime.fromtimestamp(g["end_time"], tz=pytz.utc)
                    ts = ts_utc.astimezone(warsaw_tz)
                    
                    is_w = g["white"]["username"].lower() == user.lower()
                    
                    my_player = g.get("white" if is_w else "black", {})
                    res = my_player.get("result", "")
                    my_r = my_player.get("rating", 0)
                    
                    if res == "win":
                        out = "Wygrane"
                    elif res in ["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"]:
                        out = "Remisy"
                    else:
                        out = "Przegrane"
                    
                    all_games.append({
                        "Czas": ts, "Godzina": ts.hour, "Dzień": days_map[ts.weekday()], "Dzień_Nr": ts.weekday(),
                        "Data": ts.date(), "Miesiąc_Klucz": ts.strftime("%Y-%m"), "Miesiąc_Format": ts.strftime("%m/%Y"),
                        "Tryb": g.get("time_class", "Inne").capitalize(), "Wynik": out, "Elo": my_r,
                        "Debiut": extract_opening(g.get("pgn", ""))
                    })
                    
        return p_data, s_data, pd.DataFrame(all_games)
        
    except requests.exceptions.RequestException:
        return None, None, None
    except Exception:
        return None, None, None

# --- SESSION STATE ---
if 'data' not in st.session_state:
    st.session_state.data = None
if 'user' not in st.session_state:
    st.session_state.user = ""

# --- LOGOWANIE ---
if st.session_state.data is None:
    st.title("♟️ Chess Analytics")
    nick = st.text_input("Nick Chess.com:", value=st.session_state.user, placeholder="np. Kropek76")
    if st.button("Analizuj moje wyniki", use_container_width=True):
        if nick:
            with st.spinner("Pobieranie danych (to może potrwać kilka sekund)..."):
                fetched = fetch_data(nick)
                if fetched[2] is not None and not fetched[2].empty:
                    st.session_state.data = fetched
                    st.session_state.user = nick
                    st.rerun()
                else: st.error("Błąd pobierania danych lub brak gier w ostatnich 6 miesiącach.")
else:
    profile, stats, df = st.session_state.data
    username = st.session_state.user

    with st.sidebar:
        if st.button("⬅️ Zmień gracza", use_container_width=True):
            st.session_state.data = None
            st.rerun()

    avatar = profile.get("avatar")
    c_h1, c_h2 = st.columns([1, 4])
    if avatar: c_h1.image(avatar, width=70)
    c_h2.subheader(username)

    def get_elo_v(cat):
        s = stats.get(cat, {})
        return f"{s.get('best', {}).get('rating', '-')} / {s.get('last', {}).get('rating', '-')}"

    m1, m2, m3 = st.columns(3)
    m1.metric("Rapid (Peak / Teraz)", get_elo_v("chess_rapid"))
    m2.metric("Blitz (Peak / Teraz)", get_elo_v("chess_blitz"))
    m3.metric("Bullet (Peak / Teraz)", get_elo_v("chess_bullet"))

    with st.expander("⚙️ Filtry"):
        min_date = df["Data"].min()
        max_date = df["Data"].max()
        
        d_range = st.date_input(
            "Zakres dat:", 
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        s_mode = st.selectbox("Tryb:", ["Wszystkie"] + sorted(df["Tryb"].unique().tolist()))        days_list = ['Pn', 'Wt', 'Śr', 'Czw', 'Pt', 'Sb', 'Nd']
        s_days = st.multiselect("Dni:", days_list, default=days_list)
        s_hours = st.slider("Godziny:", 0, 23, (0, 23))

    # Aplikacja filtrów
    df_f = df.copy()
    if isinstance(d_range, (list, tuple)) and len(d_range) == 2:
        df_f = df_f[(df_f["Data"] >= d_range[0]) & (df_f["Data"] <= d_range[1])]
    df_f = df_f[df_f["Dzień"].isin(s_days)]
    df_f = df_f[(df_f["Godzina"] >= s_hours[0]) & (df_f["Godzina"] <= s_hours[1])]
    if s_mode != "Wszystkie": df_f = df_f[df_f["Tryb"] == s_mode]

    if not df_f.empty:
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Stat", "📅 Hist", "⏳ Czas", "🔬 Deb"])
        
        with tab1:
            w, d, l = (df_f["Wynik"] == "Wygrane").sum(), (df_f["Wynik"] == "Remisy").sum(), (df_f["Wynik"] == "Przegrane").sum()
            wr = int(round((w/len(df_f))*100, 0)) if len(df_f) > 0 else 0
            k1, k2, k3 = st.columns(3)
            k1.metric("Gry", len(df_f))
            k2.metric("W/R/P", f"{w}/{d}/{l}")
            k3.metric("Win%", f"{wr}%")
            
            st.plotly_chart(px.pie(df_f, names="Wynik", hole=0.5, color="Wynik", 
                                 color_discrete_map={"Wygrane":"#00cc96","Przegrane":"#ef553b","Remisy":"#7f7f7f"}), use_container_width=True)
            
            st.write("#### Aktywność dzienna")
            act = df_f.groupby(["Data", "Wynik"]).size().reset_index(name="Ilość gier")
            fig_act = px.bar(act, x="Data", y="Ilość gier", color="Wynik", 
                             color_discrete_map={"Wygrane":"#00cc96","Przegrane":"#ef553b","Remisy":"#7f7f7f"},
                             category_orders={"Wynik": ["Wygrane", "Remisy", "Przegrane"]})
            fig_act.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_act, use_container_width=True)

            st.divider()
            st.write("#### Historia ELO")
            for mode in ["Rapid", "Blitz", "Bullet"]:
                m_df = df_f[df_f["Tryb"] == mode].sort_values("Czas")
                if not m_df.empty:
                    fig_elo = px.line(m_df, x="Czas", y="Elo", title=f"{mode}")
                    fig_elo.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title=None)
                    st.plotly_chart(fig_elo, use_container_width=True)

        with tab2:
            monthly = df_f.groupby(["Miesiąc_Klucz", "Miesiąc_Format"]).agg(
                W=('Wynik', lambda x: (x == 'Wygrane').sum()), 
                R=('Wynik', lambda x: (x == 'Remisy').sum()), 
                P=('Wynik', lambda x: (x == 'Przegrane').sum()), 
                T=('Wynik', 'count'), 
                E=('Elo', 'mean')
            ).reset_index()
            monthly["W/R/P"] = monthly.apply(lambda x: f"{int(x['W'])}/{int(x['R'])}/{int(x['P'])}", axis=1)
            monthly["Średnie ELO"] = monthly["E"].round(0).astype(int)
            
            st.dataframe(monthly[["Miesiąc_Format", "T", "W/R/P", "Średnie ELO"]].rename(columns={"Miesiąc_Format":"Miesiąc", "T":"Gry"}).sort_values("Miesiąc", ascending=False), use_container_width=True, hide_index=True)
            
            st.divider()
            if not monthly.empty:
                sel_m = st.selectbox("Szczegóły miesiąca:", monthly["Miesiąc_Format"].unique())
                day_df = df_f[df_f["Miesiąc_Format"] == sel_m].groupby("Data").agg(
                    W=('Wynik', lambda x: (x == 'Wygrane').sum()), 
                    R=('Wynik', lambda x: (x == 'Remisy').sum()), 
                    P=('Wynik', lambda x: (x == 'Przegrane').sum()), 
                    T=('Wynik', 'count'), 
                    E=('Elo', 'mean')
                ).reset_index()
                day_df["Dzień"] = pd.to_datetime(day_df["Data"]).dt.strftime("%d/%m")
                day_df["Bilans"] = day_df.apply(lambda x: f"{int(x['W'])}/{int(x['R'])}/{int(x['P'])}", axis=1)
                day_df["Średnie ELO"] = day_df["E"].round(0).astype(int)
                st.dataframe(day_df[["Dzień", "T", "Bilans", "Średnie ELO"]].rename(columns={"T":"Gry"}).sort_values("Dzień", ascending=False), use_container_width=True, hide_index=True)

        with tab3:
            navy = ['#ffffff', '#000080']
            d_st = df_f.groupby(["Dzień", "Dzień_Nr"]).agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index().sort_values("Dzień_Nr")
            d_st["Win%"] = (d_st["W"] / d_st["Gry"] * 100).round(0).astype(int)
            st.plotly_chart(px.bar(d_st, x="Dzień", y="Win%", color="Gry", color_continuous_scale=navy, title="Win Rate wg dni"), use_container_width=True)
            
            t_st = df_f.groupby("Godzina").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
            t_st["Win%"] = (t_st["W"] / t_st["Gry"] * 100).round(0).astype(int)
            st.plotly_chart(px.bar(t_st, x="Godzina", y="Win%", color="Gry", color_continuous_scale=navy, title="Win Rate wg godzin"), use_container_width=True)

        with tab4:
            op = df_f.groupby("Debiut").agg(Gry=('Wynik', 'count'), W=('Wynik', lambda x: (x == 'Wygrane').sum())).reset_index()
            op["Win%"] = (op["W"] / op["Gry"] * 100).round(0).astype(int)
            st.dataframe(op[["Debiut", "Gry", "Win%"]].sort_values("Gry", ascending=False).head(20), use_container_width=True, hide_index=True)
    else:
        st.info("Brak gier spełniających wybrane kryteria filtrów.")
