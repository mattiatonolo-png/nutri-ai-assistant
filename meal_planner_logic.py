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

import difflib

# --- FUNZIONI DI INTEGRAZIONE AI (IMPORT PLAN) ---

def find_closest_food_match(search_term, db_df):
    """
    Cerca l'alimento più simile nel DB usando la comparazione di stringhe.
    Restituisce la riga del DF o None se non trova nulla di decente.
    """
    # 1. Creiamo una lista di tutti i nomi nel DB
    all_names = db_df['Nome'].tolist()
    
    # 2. Troviamo il match migliore (cutoff 0.5 significa che deve assomigliare almeno al 50%)
    matches = difflib.get_close_matches(search_term, all_names, n=1, cutoff=0.5)
    
    if matches:
        best_match_name = matches[0]
        # Restituisce la riga corrispondente
        return db_df[db_df['Nome'] == best_match_name].iloc[0]
    
    # Tentativo fallback: Cerca se la parola è contenuta (es. "Soia" in "Latte di soia")
    # Questo aiuta se il fuzzy fallisce
    search_lower = search_term.lower()
    mask = db_df['Nome'].str.lower().str.contains(search_lower, regex=False)
    if mask.any():
        return db_df[mask].iloc[0]
        
    return None

def import_ai_plan_to_state(ai_json_plan):
    """
    Prende il JSON generato dall'AI e popola il session_state.
    ai_json_plan deve essere una lista di dizionari:
    [
      {'day': 'Lunedì', 'meal': 'Colazione', 'food': 'Latte soia', 'grams': 200},
      ...
    ]
    """
    # Carichiamo il DB
    df_db = load_food_db()
    if df_db.empty: return False
    
    # Resettiamo il piano attuale (Opzionale: se vuoi sovrascrivere)
    initialize_meal_plan_state()
    
    # Mappatura nomi pasti AI -> Nomi pasti System
    # L'AI potrebbe scrivere "Spuntino" e noi abbiamo "Spuntino Mattina". Normalizziamo.
    meal_map = {
        "colazione": "Colazione",
        "spuntino mattina": "Spuntino Mattina",
        "pranzo": "Pranzo",
        "spuntino pomeriggio": "Spuntino Pomeriggio",
        "cena": "Cena",
        "snack": "Spuntino Mattina" # Fallback
    }

    count_added = 0
    
    for item in ai_json_plan:
        day = item.get('day', '').capitalize() # Assicura "Lunedì"
        meal_raw = item.get('meal', '').lower()
        food_query = item.get('food', '')
        grams = item.get('grams', 100)
        
        # 1. Trova il Giorno Corretto
        if day not in DAYS_OF_WEEK:
            continue # Salta giorni non validi
            
        # 2. Trova il Pasto Corretto (Matching approssimativo)
        target_meal = None
        for key, val in meal_map.items():
            if key in meal_raw:
                target_meal = val
                break
        if not target_meal: target_meal = "Colazione" # Default se non capisce
        
        # 3. Cerca l'alimento nel CSV
        match_row = find_closest_food_match(food_query, df_db)
        
        if match_row is not None:
            # 4. Aggiungi usando la funzione che abbiamo già!
            add_food_to_meal(day, target_meal, match_row, grams)
            count_added += 1
        else:
            # Opzionale: Aggiungere un "Placeholder" se non trova l'alimento?
            # Per ora saltiamo per non sporcare il piano con errori.
            print(f"Alimento non trovato nel DB: {food_query}")
            
    return count_added
