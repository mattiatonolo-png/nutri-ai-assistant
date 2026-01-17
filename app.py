import streamlit as st
import os
from pypdf import PdfReader
from google import genai
from google.genai import types

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Nutri-AI Clinical", page_icon="🩺", layout="wide")

# Nascondiamo menu e footer per aspetto professionale
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("🩺 Nutri-AI: Assistente Clinico Avanzato")
st.markdown("Sistema di supporto decisionale basato su protocolli SINU/LARN.")

# --- 2. GESTIONE CHIAVE API (SECRETS) ---
try:
    # Cerca la chiave nella "Cassaforte" di Streamlit Cloud
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # Se siamo sul Mac e non abbiamo impostato secrets.toml, usiamo un fallback o errore
    # Togli il commento qui sotto e metti la chiave se lo usi in locale sul Mac:
    # LA_MIA_API_KEY = "AIzaSy....." 
    st.error("Chiave API mancante. Impostala nei Secrets di Streamlit.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# --- 3. CARICAMENTO BIBLIOTECA (Tutti i PDF) ---
@st.cache_resource # Questo comando fa sì che legga i PDF una volta sola e non a ogni click!
def carica_biblioteca():
    cartella = "documenti"
    testo_totale = ""
    lista_fonti = []
    
    if not os.path.exists(cartella):
        os.makedirs(cartella)
        return None, []

    files = [f for f in os.listdir(cartella) if f.endswith('.pdf')]
    
    if not files:
        return None, []

    for file_name in files:
        percorso = os.path.join(cartella, file_name)
        try:
            reader = PdfReader(percorso)
            testo_file = f"\n--- FONTE: {file_name} ---\n"
            for page in reader.pages:
                t = page.extract_text()
                if t: testo_file += t + "\n"
            testo_totale += testo_file
            lista_fonti.append(file_name)
        except:
            pass
            
    return testo_totale, lista_fonti

CONTESTO_BIBLIOTECA, LISTA_FILE = carica_biblioteca()

# --- 4. SIDEBAR: CARTELLA CLINICA (Input Dati) ---
with st.sidebar:
    st.header("📋 Dati Paziente")
    
    # Input strutturati
    sesso = st.selectbox("Sesso", ["Uomo", "Donna", "Altro"])
    eta = st.number_input("Età", min_value=0, max_value=120, value=30)
    peso = st.number_input("Peso (kg)", min_value=0, value=70)
    altezza = st.number_input("Altezza (cm)", min_value=0, value=170)
    
    st.divider()
    
    st.subheader("Quadro Clinico")
    patologie = st.multiselect(
        "Patologie/Condizioni",
        ["Nessuna", "Diabete T2", "Ipertensione", "Colesterolo Alto", "Gravidanza", "Celiachia", "Sportivo Agonista"]
    )
    
    allergie = st.text_input("Allergie/Intolleranze", placeholder="Es. Lattosio, Nichel...")
    
    obiettivo = st.selectbox(
        "Obiettivo", 
        ["Mantenimento", "Perdita Peso", "Aumento Massa", "Gestione Patologia"]
    )
    
    # Creiamo una stringa che riassume il paziente
    PROFILO_PAZIENTE = f"""
    DATI PAZIENTE:
    - Sesso: {sesso}
    - Età: {eta} anni
    - Peso: {peso} kg
    - Altezza: {altezza} cm
    - Patologie: {', '.join(patologie)}
    - Allergie: {allergie}
    - Obiettivo: {obiettivo}
    """
    
    st.info(f"📚 Fonti attive: {len(LISTA_FILE) if LISTA_FILE else 0}")
    if st.button("🗑️ Cancella Chat"):
        st.session_state.messages = []
        st.rerun()

# --- 5. IL CERVELLO (SYSTEM PROMPT DINAMICO) ---
# Qui uniamo: Ruolo + Dati Paziente + Libri letti
ISTRUZIONI_MASTER = f"""
RUOLO: Sei un Assistente Nutrizionista Clinico Esperto basato su evidenze scientifiche.

{PROFILO_PAZIENTE}

BIBLIOTECA SCIENTIFICA DI RIFERIMENTO:
{CONTESTO_BIBLIOTECA if CONTESTO_BIBLIOTECA else "Nessun documento caricato."}

REGOLE FONDAMENTALI:
1. Analizza la richiesta dell'utente incrociandola con i DATI PAZIENTE (es. se iperteso, controlla il sodio nei documenti).
2. Usa ESCLUSIVAMENTE le informazioni presenti nella BIBLIOTECA per dare raccomandazioni nutrizionali.
3. Se un'informazione manca nei documenti, dillo.
4. Tono professionale, empatico e sintetico.
5. Usa elenchi puntati e tabelle per la dieta.
"""

# --- 6. GESTIONE CHAT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostra messaggi precedenti
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input Utente
if prompt := st.chat_input("Scrivi qui (es: 'Genera una giornata tipo' o 'Quante proteine servono?')"):
    
    # Aggiungi input utente alla storia
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Genera risposta
    with st.chat_message("assistant"):
        with st.spinner("Elaborazione piano clinico..."):
            try:
                # Prepara la storia per Gemini
                chat_history_gemini = []
                for msg in st.session_state.messages:
                    role = "user" if msg["role"] == "user" else "model"
                    chat_history_gemini.append(types.Content(
                        role=role, 
                        parts=[types.Part(text=msg["content"])]
                    ))

                # Chiamata all'AI
                response = client.models.generate_content(
                    model="gemini-1.5-flash-latest", # Modello veloce e capace
                    contents=chat_history_gemini,
                    config=types.GenerateContentConfig(
                        system_instruction=ISTRUZIONI_MASTER,
                        temperature=0.3 # Bassa creatività per rigore scientifico
                    )
                )
                
                output_text = response.text
                st.markdown(output_text)
                
                # Salva risposta nella storia
                st.session_state.messages.append({"role": "assistant", "content": output_text})

            except Exception as e:
                st.error(f"Errore di generazione: {e}")
