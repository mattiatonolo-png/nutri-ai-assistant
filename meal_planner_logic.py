import streamlit as st
import pandas as pd
import os

# --- COSTANTI DI CONFIGURAZIONE ---
CSV_DB_PATH = "crea_food_composition_tables.csv"

# Mappatura colonne: {Nome_CSV: Nome_Interfaccia}
COLUMN_MAPPING = {
    "name": "Nome",
    "energy_kcal": "Kcal",
    "proteins": "Proteine",
    "available_carbohydrates": "Carboidrati",
    "lipids": "Grassi",
    "total_fiber": "Fibre"
}

# Struttura temporale del piano
DAYS_OF_WEEK = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MEAL_TYPES = ["Colazione", "Spuntino Mattina", "Pranzo", "Spuntino Pomeriggio", "Cena"]

# --- 1. CARICAMENTO DATI EFFICIENTE ---

@st.cache_data
def load_food_db():
    """
    Carica, pulisce e prepara il database degli alimenti.
    Usa la cache di Streamlit per evitare ricaricamenti inutili.
    """
    if not os.path.exists(CSV_DB_PATH):
        st.error(f"Errore: File database '{CSV_DB_PATH}' non trovato.")
        return pd.DataFrame() # Ritorna DF vuoto per evitare crash

    try:
        # Caricamento
        df = pd.read_csv(CSV_DB_PATH)
        
        # Rinomina colonne tecniche in user-friendly
        # Filtriamo solo le colonne che ci interessano + rinomina
        cols_to_keep = list(COLUMN_MAPPING.keys())
        df = df[cols_to_keep].rename(columns=COLUMN_MAPPING)
        
        # Gestione NaN (conversione a 0 per i calcoli numerici)
        numeric_cols = ["Kcal", "Proteine", "Carboidrati", "Grassi", "Fibre"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # Creazione colonna "Etichetta" per UI (Selectbox/Search)
        # Es: "Pasta di semola (350 kcal)"
        df["Etichetta"] = (
            df["Nome"] + " (" + df["Kcal"].astype(int).astype(str) + " kcal/100g)"
        )
        
        return df

    except Exception as e:
        st.error(f"Errore durante il parsing del database alimenti: {e}")
        return pd.DataFrame()

# --- 2. GESTIONE STATO E STRUTTURA DATI ---

def initialize_meal_plan_state():
    """
    Inizializza la struttura dati del piano alimentare nel session_state
    se non esiste già.
    
    Struttura:
    st.session_state['weekly_plan'] = {
        'Lunedì': {
            'Colazione': [ { 'Alimento': '...', 'Grammi': 100, 'Kcal_tot': ... }, ... ],
            'Pranzo': [],
            ...
        },
        ...
    }
    """
    if 'weekly_plan' not in st.session_state:
        st.session_state['weekly_plan'] = {
            day: {meal: [] for meal in MEAL_TYPES} 
            for day in DAYS_OF_WEEK
        }
    
    # Inizializziamo anche un buffer per le modifiche temporanee se necessario
    if 'current_editing_day' not in st.session_state:
        st.session_state['current_editing_day'] = "Lunedì"

def add_food_to_meal(day, meal, food_row, grams):
    """
    Aggiunge un alimento al piano calcolando i macro effettivi in base ai grammi.
    food_row: La riga del DataFrame del DB corrispondente all'alimento selezionato.
    """
    # Calcolo proporzionale (Valore * Grammi / 100)
    factor = grams / 100.0
    
    food_item = {
        "Nome": food_row["Nome"],
        "Grammi": grams,
        "Kcal_tot": round(food_row["Kcal"] * factor, 1),
        "Prot_tot": round(food_row["Proteine"] * factor, 1),
        "Carb_tot": round(food_row["Carboidrati"] * factor, 1),
        "Grassi_tot": round(food_row["Grassi"] * factor, 1),
        # Salviamo anche i valori base per futuri ricalcoli se si cambiano i grammi
        "Base_Kcal": food_row["Kcal"],
        "Base_Prot": food_row["Proteine"],
        "Base_Carb": food_row["Carboidrati"],
        "Base_Grassi": food_row["Grassi"]
    }
    
    st.session_state['weekly_plan'][day][meal].append(food_item)

# --- 3. FUNZIONI DI CALCOLO LIVE ---

def calculate_daily_totals(day):
    """
    Calcola la somma dei macro per un intero giorno specifico.
    Restituisce un dizionario con i totali.
    """
    totals = {
        "Kcal": 0,
        "Proteine": 0,
        "Carboidrati": 0,
        "Grassi": 0
    }
    
    day_plan = st.session_state['weekly_plan'].get(day, {})
    
    for meal_type in MEAL_TYPES:
        foods = day_plan.get(meal_type, [])
        for food in foods:
            totals["Kcal"] += food.get("Kcal_tot", 0)
            totals["Proteine"] += food.get("Prot_tot", 0)
            totals["Carboidrati"] += food.get("Carb_tot", 0)
            totals["Grassi"] += food.get("Grassi_tot", 0)
            
    # Arrotondamento finale per pulizia UI
    return {k: round(v, 1) for k, v in totals.items()}

def calculate_weekly_totals():
    """
    (Opzionale) Calcola la media settimanale
    """
    weekly_sums = {k: 0 for k in ["Kcal", "Proteine", "Carboidrati", "Grassi"]}
    
    for day in DAYS_OF_WEEK:
        day_totals = calculate_daily_totals(day)
        for k in weekly_sums:
            weekly_sums[k] += day_totals[k]
            
    # Calcolo media
    return {k: round(v / 7, 1) for k, v in weekly_sums.items()}