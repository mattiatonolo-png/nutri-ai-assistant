import streamlit as st
import pandas as pd
import os

# --- COSTANTI DI CONFIGURAZIONE ---
CSV_DB_PATH = "crea_food_composition_tables.csv"

# Mappatura colonne: {Nome_Colonna_CSV : Nome_Visualizzato_UI}
COLUMN_MAPPING = {
    # Macro
    "name": "Nome",
    "energy_kcal": "Kcal",
    "proteins": "Proteine",
    "available_carbohydrates": "Carboidrati",
    "lipids": "Grassi",
    "total_fiber": "Fibre",
    # Micro Minerali (selezionati in base alla copertura > 60%)
    "calcium": "Calcio",
    "iron": "Ferro",
    "phosphorus": "Fosforo",
    "potassium": "Potassio",
    "sodium": "Sodio",
    # Micro Vitamine (selezionati in base alla copertura > 55%)
    "thiamine": "Vit B1",
    "riboflavin": "Vit B2",
    "niacin": "Vit B3"
}

# Lista tecnica dei Micro (usata per i cicli di calcolo)
MICRO_LIST = ["Calcio", "Ferro", "Fosforo", "Potassio", "Sodio", "Vit B1", "Vit B2", "Vit B3"]

# Struttura temporale del piano
DAYS_OF_WEEK = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MEAL_TYPES = ["Colazione", "Spuntino Mattina", "Pranzo", "Spuntino Pomeriggio", "Cena"]

# --- 1. CARICAMENTO DATI EFFICIENTE ---

@st.cache_data
def load_food_db():
    """
    Carica, pulisce e prepara il database degli alimenti.
    Gestisce Macro e Micro nutrienti.
    """
    if not os.path.exists(CSV_DB_PATH):
        st.error(f"Errore: File database '{CSV_DB_PATH}' non trovato.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(CSV_DB_PATH)
        
        # Filtriamo solo le colonne che esistono sia nel CSV che nel Mapping
        cols_available = list(set(COLUMN_MAPPING.keys()).intersection(df.columns))
        df = df[cols_available].rename(columns=COLUMN_MAPPING)
        
        # Pulizia Numerica (Macro + Micro)
        numeric_cols = ["Kcal", "Proteine", "Carboidrati", "Grassi", "Fibre"] + MICRO_LIST
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else:
                df[col] = 0.0 # Se manca del tutto nel CSV
            
        # Creazione colonna "Etichetta" per UI
        df["Etichetta"] = (
            df["Nome"] + " (" + df["Kcal"].astype(int).astype(str) + " kcal)"
        )
        
        return df

    except Exception as e:
        st.error(f"Errore parsing DB: {e}")
        return pd.DataFrame()

# --- 2. GESTIONE STATO E STRUTTURA DATI ---

def initialize_meal_plan_state():
    if 'weekly_plan' not in st.session_state:
        st.session_state['weekly_plan'] = {
            day: {meal: [] for meal in MEAL_TYPES} 
            for day in DAYS_OF_WEEK
        }

def add_food_to_meal(day, meal, food_row, grams):
    """
    Aggiunge un alimento calcolando proporzionalmente tutti i valori (Macro e Micro).
    """
    factor = grams / 100.0
    
    # 1. Base Item con Macro
    food_item = {
        "Nome": food_row["Nome"],
        "Grammi": grams,
        "Kcal_tot": round(food_row.get("Kcal", 0) * factor, 1),
        "Prot_tot": round(food_row.get("Proteine", 0) * factor, 1),
        "Carb_tot": round(food_row.get("Carboidrati", 0) * factor, 1),
        "Grassi_tot": round(food_row.get("Grassi", 0) * factor, 1),
        # Salviamo i valori base per 100g (utili se si modifica il peso dopo)
        "Base_Kcal": food_row.get("Kcal", 0),
        "Base_Prot": food_row.get("Proteine", 0),
        "Base_Carb": food_row.get("Carboidrati", 0),
        "Base_Grassi": food_row.get("Grassi", 0)
    }

    # 2. Aggiunta Dinamica Micronutrienti
    for micro in MICRO_LIST:
        val_base = food_row.get(micro, 0)
        food_item[f"{micro}_tot"] = round(val_base * factor, 1)
        food_item[f"Base_{micro}"] = val_base

    st.session_state['weekly_plan'][day][meal].append(food_item)

def update_meal_from_editor(day, meal, edited_df):
    """
    Aggiorna lo stato quando l'utente modifica la tabella (cambia grammi o cancella righe).
    """
    new_meal_list = []
    
    if edited_df is not None and not edited_df.empty:
        for index, row in edited_df.iterrows():
            try:
                grams = float(row["Grammi"])
                factor = grams / 100.0
                
                # Recuperiamo i valori base salvati
                base_kcal = row.get("Base_Kcal", 0)
                base_prot = row.get("Base_Prot", 0)
                base_carb = row.get("Base_Carb", 0)
                base_grassi = row.get("Base_Grassi", 0)
                
                updated_item = {
                    "Nome": row["Nome"],
                    "Grammi": grams,
                    "Kcal_tot": round(base_kcal * factor, 1),
                    "Prot_tot": round(base_prot * factor, 1),
                    "Carb_tot": round(base_carb * factor, 1),
                    "Grassi_tot": round(base_grassi * factor, 1),
                    "Base_Kcal": base_kcal,
                    "Base_Prot": base_prot,
                    "Base_Carb": base_carb,
                    "Base_Grassi": base_grassi
                }
                
                # Aggiornamento Dinamico Micro
                for micro in MICRO_LIST:
                    base_val = row.get(f"Base_{micro}", 0)
                    updated_item[f"{micro}_tot"] = round(base_val * factor, 1)
                    updated_item[f"Base_{micro}"] = base_val
                
                new_meal_list.append(updated_item)
            except ValueError:
                continue # Salta righe con errori nei numeri
            
    st.session_state['weekly_plan'][day][meal] = new_meal_list

# --- 3. FUNZIONI DI CALCOLO LIVE ---

def calculate_daily_totals(day):
    # Inizializza contatori a 0 per Macro e Micro
    totals = {k: 0 for k in ["Kcal", "Proteine", "Carboidrati", "Grassi"] + MICRO_LIST}
    
    day_plan = st.session_state['weekly_plan'].get(day, {})
    
    for meal_type in MEAL_TYPES:
        foods = day_plan.get(meal_type, [])
        for food in foods:
            # Somma Macro
            totals["Kcal"] += food.get("Kcal_tot", 0)
            totals["Proteine"] += food.get("Prot_tot", 0)
            totals["Carboidrati"] += food.get("Carb_tot", 0)
            totals["Grassi"] += food.get("Grassi_tot", 0)
            
            # Somma Micro
            for micro in MICRO_LIST:
                totals[micro] += food.get(f"{micro}_tot", 0)
            
    return {k: round(v, 1) for k, v in totals.items()}
