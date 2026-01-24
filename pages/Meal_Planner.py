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
mpl.initialize_meal_plan_state()
df_food = mpl.load_food_db()

if df_food.empty:
    st.error("⚠️ Errore critico: Database alimenti non caricato.")
    st.stop()

# --- 2. SIDEBAR ---
with st.sidebar:
    st.title("📅 Navigazione")
    selected_day = st.radio("Seleziona Giorno:", mpl.DAYS_OF_WEEK, index=0)
    st.markdown("---")
    st.info("💡 Puoi modificare i grammi direttamente nella tabella. Metti 0 o usa il cestino per cancellare.")
    if st.button("🗑️ Svuota Giorno"):
        for meal in mpl.MEAL_TYPES:
            st.session_state['weekly_plan'][selected_day][meal] = []
        st.rerun()

# --- 3. DASHBOARD MACRO (STICKY KPI) ---
st.title(f"Piano Alimentare: {selected_day}")

# Calcolo Totali
daily_macros = mpl.calculate_daily_totals(selected_day)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("🔥 Kcal", f"{daily_macros['Kcal']:.0f}")
kpi2.metric("🥩 Proteine", f"{daily_macros['Proteine']:.1f} g")
kpi3.metric("🍞 Carboidrati", f"{daily_macros['Carboidrati']:.1f} g")
kpi4.metric("🥑 Grassi", f"{daily_macros['Grassi']:.1f} g")

# --- 4. DASHBOARD MICRO NUTRIENTI (EXPANDER) ---
with st.expander("🔬 Analisi Micronutrienti (Stimata)", expanded=False):
    col_min, col_vit, col_info = st.columns(3)
    
    with col_min:
        st.markdown("**Minerali**")
        st.write(f"🦴 **Calcio:** {daily_macros.get('Calcio', 0):.0f} mg")
        st.write(f"🩸 **Ferro:** {daily_macros.get('Ferro', 0):.1f} mg")
        st.write(f"⚡ **Potassio:** {daily_macros.get('Potassio', 0):.0f} mg")
        st.write(f"🧂 **Sodio:** {daily_macros.get('Sodio', 0):.0f} mg")
        st.write(f"🧠 **Fosforo:** {daily_macros.get('Fosforo', 0):.0f} mg")
        
    with col_vit:
        st.markdown("**Vitamine B**")
        st.write(f"⚡ **B1 (Tiamina):** {daily_macros.get('Vit B1', 0):.2f} mg")
        st.write(f"👀 **B2 (Ribofl.):** {daily_macros.get('Vit B2', 0):.2f} mg")
        st.write(f"🧬 **B3 (Niacina):** {daily_macros.get('Vit B3', 0):.1f} mg")
        
    with col_info:
        st.info("⚠️ Vitamine volatili (C, D, A, B12) non tracciate per dati insufficienti nel DB Open Source.")

st.markdown("---")

# --- 5. GESTIONE PASTI (EDITABLE) ---
for meal in mpl.MEAL_TYPES:
    with st.expander(f"🍽️ {meal}", expanded=True):
        
        # Recupero dati attuali
        current_items = st.session_state['weekly_plan'][selected_day][meal]
        df_display = pd.DataFrame(current_items)
        
        # A. TABELLA EDITABILE
        if not df_display.empty:
            edited_df = st.data_editor(
                df_display,
                key=f"editor_{selected_day}_{meal}",
                num_rows="dynamic", # Permette di cancellare/aggiungere righe
                column_order=["Nome", "Grammi", "Kcal_tot", "Prot_tot", "Carb_tot", "Grassi_tot"],
                column_config={
                    "Nome": st.column_config.TextColumn("Alimento", disabled=True),
                    "Grammi": st.column_config.NumberColumn("Grammi", min_value=1, step=10, required=True),
                    "Kcal_tot": st.column_config.NumberColumn("Kcal", disabled=True),
                    "Prot_tot": st.column_config.NumberColumn("Prot", disabled=True),
                    "Carb_tot": st.column_config.NumberColumn("Carb", disabled=True),
                    "Grassi_tot": st.column_config.NumberColumn("Grassi", disabled=True),
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Callback manuale per salvare le modifiche
            # Confrontiamo lo stato precedente con quello editato per capire se aggiornare
            # Nota: Streamlit fa il rerun automatico, quindi basta salvare sempre.
            mpl.update_meal_from_editor(selected_day, meal, edited_df)
            
        else:
            st.caption("Nessun alimento. Aggiungi qui sotto.")

        # B. WIDGET AGGIUNTA
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            food_label = st.selectbox(
                "Cerca alimento", 
                options=df_food["Etichetta"].unique(),
                index=None,
                placeholder="Digita per cercare...",
                key=f"sel_{selected_day}_{meal}",
                label_visibility="collapsed"
            )
        with c2:
            grams = st.number_input("Grammi", min_value=1, value=100, step=10, key=f"num_{selected_day}_{meal}", label_visibility="collapsed")
        with c3:
            if st.button("➕ Aggiungi", key=f"btn_{selected_day}_{meal}", use_container_width=True):
                if food_label:
                    selected_row = df_food[df_food["Etichetta"] == food_label].iloc[0]
                    mpl.add_food_to_meal(selected_day, meal, selected_row, grams)
                    st.rerun()
