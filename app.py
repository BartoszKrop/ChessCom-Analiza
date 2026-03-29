with tab5:
            st.write("### 🧠 Analiza partii")
            
            c1, c2 = st.columns(2)
            with c1: 
                search_date = st.date_input("Dzień partii (jeśli nick pusty):", value=df["Data"].max())
            with c2: 
                search_opp = st.text_input("Nick przeciwnika (override daty):").strip()

            if search_opp:
                df_ana = df[df["Przeciwnik"].str.lower() == search_opp.lower()]
            else:
                df_ana = df[df["Data"] == search_date]

            if not df_ana.empty:
                df_ana["Label"] = df_ana.apply(lambda x: f"{x['Data']} | {x['Godzina']}:00 | {x['Tryb']} vs {x['Przeciwnik']} ({x['Wynik']})", axis=1)
                sel_label = st.selectbox("Wybierz partię z listy:", df_ana.sort_values("Timestamp", ascending=False)["Label"])
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

                # Elegancki, niebieski przycisk z nickiem i datą
                if st.session_state.current_lichess_url:
                    btn_label = f"➡️ ANALIZA PARTII: {sel_game['Przeciwnik']} ({sel_game['Data']})"
                    st.link_button(btn_label, st.session_state.current_lichess_url, type="primary", use_container_width=True)
                    st.caption("Kliknij powyżej, aby otworzyć partię w aplikacji Lichess (lub przeglądarce).")
            else:
                st.warning("Nie znaleziono partii.")
