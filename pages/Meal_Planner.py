import streamlit as st
import pandas as pd
import meal_planner_logic as mpl

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Weekly Meal Planner",
    page_icon="🥗",
    layout="wide"
)

# --- 1. SETUP INIZIALE & STATO ---
# Inizializza la struttura dati se l'utente atterra direttamente qui
mpl.initialize_meal_plan_state()

# Carica il Database Alimenti
df_food = mpl.load_food_db()

# Controllo sicurezza DB
if df_food.empty:
    st.error("⚠️ Errore critico: Database alimenti non caricato. Verifica il file CSV.")
    st.stop()

# --- 2. SIDEBAR: SELEZIONE GIORNO ---
with st.sidebar:
    st.title("📅 Navigazione")
    selected_day = st.radio(
        "Seleziona Giorno:",
        mpl.DAYS_OF_WEEK,
        index=0
    )
    
    st.markdown("---")
    st.info("💡 **Tip:** Seleziona un alimento e premi 'Aggiungi'. I totali in alto si aggiorneranno automaticamente.")
    
    # (Opzionale) Bottone per resettare il giorno
    if st.button("🗑️ Svuota Giorno Corrente"):
        for meal in mpl.MEAL_TYPES:
            st.session_state['weekly_plan'][selected_day][meal] = []
        st.rerun()

# --- 3. TOP BAR: DASHBOARD MACRO (STICKY KPI) ---
st.title(f"Piano Alimentare: {selected_day}")

# Calcolo i totali live per il giorno selezionato
daily_macros = mpl.calculate_daily_totals(selected_day)

# Visualizzazione KPI
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("🔥 Kcal Totali", f"{daily_macros['Kcal']}", delta_color="off")
kpi2.metric("🥩 Proteine", f"{daily_macros['Proteine']} g", help="Target consigliato: ...")
kpi3.metric("🍞 Carboidrati", f"{daily_macros['Carboidrati']} g")
kpi4.metric("🥑 Grassi", f"{daily_macros['Grassi']} g")

st.markdown("---")

# --- 4. MAIN AREA: GESTIONE PASTI ---

# Ciclo per generare le sezioni dei 5 pasti
for meal in mpl.MEAL_TYPES:
    # Usiamo expander per mantenere l'interfaccia pulita
    with st.expander(f"🍽️ {meal}", expanded=True):
        
        # A. TABELLA ALIMENTI INSERITI
        current_items = st.session_state['weekly_plan'][selected_day][meal]
        
        if current_items:
            # Creiamo un DF al volo per mostrare i dati in modo tabellare
            df_display = pd.DataFrame(current_items)
            
            # Configuriamo le colonne da mostrare
            st.dataframe(
                df_display[["Nome", "Grammi", "Kcal_tot", "Prot_tot", "Carb_tot", "Grassi_tot"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Kcal_tot": st.column_config.NumberColumn("Kcal", format="%.1f"),
                    "Prot_tot": st.column_config.NumberColumn("Prot (g)", format="%.1f"),
                    "Carb_tot": st.column_config.NumberColumn("Carb (g)", format="%.1f"),
                    "Grassi_tot": st.column_config.NumberColumn("Grassi (g)", format="%.1f"),
                }
            )
        else:
            st.caption("Nessun alimento inserito per questo pasto.")

        # B. WIDGET DI INSERIMENTO
        # Creiamo colonne per allineare selectbox, input grammi e bottone
        c1, c2, c3 = st.columns([3, 1, 1])
        
        with c1:
            # Selectbox con ricerca (usa l'etichetta combinata Nome + Kcal)
            food_label = st.selectbox(
                "Cerca alimento", 
                options=df_food["Etichetta"].unique(),
                index=None,
                placeholder="Digita per cercare...",
                key=f"sel_{selected_day}_{meal}", # Chiave univoca fondamentale
                label_visibility="collapsed"
            )
            
        with c2:
            grams = st.number_input(
                "Grammi", 
                min_value=1, 
                value=100, 
                step=10, 
                key=f"num_{selected_day}_{meal}",
                label_visibility="collapsed"
            )
            
        with c3:
            # Bottone Aggiungi
            if st.button("➕ Aggiungi", key=f"btn_{selected_day}_{meal}", use_container_width=True):
                if food_label:
                    # Recupera la riga completa dal DB basandosi sull'etichetta
                    selected_row = df_food[df_food["Etichetta"] == food_label].iloc[0]
                    
                    # Chiama la logica di backend
                    mpl.add_food_to_meal(selected_day, meal, selected_row, grams)
                    
                    # Feedback utente
                    st.toast(f"Aggiunto: {selected_row['Nome']} ({grams}g)", icon="✅")
                    
                    # Rerun per aggiornare immediatamente i KPI in alto
                    st.rerun()
                else:
                    st.warning("Seleziona un alimento prima di aggiungere.")