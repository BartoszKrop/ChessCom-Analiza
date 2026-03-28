import pytz # Dodaj ten import na samej górze pliku (obok from datetime import datetime)

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_data(user):
    # Najlepiej wpisz tu jakiegoś maila, żeby Chess.com Cię nie zablokowało
    headers = {"User-Agent": f"ChessAnalyticsApp / kontakt@twojadomena.pl / username: {user}"}
    
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
        
        # Ustawienie polskiej strefy czasowej (rozwiązuje problem hostowania w chmurze)
        warsaw_tz = pytz.timezone('Europe/Warsaw')

        # Pobieramy maksymalnie 6 ostatnich miesięcy (pół roku to dobry kompromis)
        for url in archives[-6:]: 
            m_res = requests.get(url, headers=headers, timeout=10)
            if m_res.status_code != 200:
                continue # Jeśli 1 miesiąc się nie pobierze, idziemy dalej
                
            m_data = m_res.json()
            for g in m_data.get("games", []):
                if "end_time" in g:
                    # Zamiana timestampu na format UTC, a potem na czas polski
                    ts_utc = datetime.utcfromtimestamp(g["end_time"]).replace(tzinfo=pytz.utc)
                    ts = ts_utc.astimezone(warsaw_tz)
                    
                    is_w = g["white"]["username"].lower() == user.lower()
                    
                    # Czasem gracze mają zbanowane konta, co wpływa na strukturę JSON.
                    # Bezpieczniej jest używać .get() przy zagnieżdżeniach
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
        
    except requests.exceptions.RequestException as e:
        st.error(f"Błąd połączenia z API Chess.com: {e}")
        return None, None, None
    except Exception as e:
        st.error(f"Wystąpił nieoczekiwany błąd podczas przetwarzania danych: {e}")
        return None, None, None
