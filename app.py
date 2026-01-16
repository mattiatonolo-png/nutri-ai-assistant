import streamlit as st
import os
from pypdf import PdfReader
from google import genai
from google.genai import types

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Nutri-AI Biblioteca", page_icon="📚", layout="wide")
st.title("📚 Nutri-AI: Clinical RAG System (Multi-Source)")

# --- FUNZIONE PER LEGGERE TUTTI I PDF ---
def carica_biblioteca(cartella):
    """Legge tutti i PDF in una cartella e unisce i testi."""
    testo_totale = ""
    elenco_file = []
    
    # Verifica se la cartella esiste
    if not os.path.exists(cartella):
        os.makedirs(cartella) # La crea se non c'è
        return None, []

    # Scansiona i file
    files = os.listdir(cartella)
    files_pdf = [f for f in files if f.endswith('.pdf')]
    
    if not files_pdf:
        return None, []

    # Barra di caricamento visiva
    progresso = st.progress(0, text="Inizializzazione lettura documenti...")
    
    for i, file_name in enumerate(files_pdf):
        percorso = os.path.join(cartella, file_name)
        try:
            reader = PdfReader(percorso)
            testo_file = f"\n--- INIZIO FILE: {file_name} ---\n"
            for page in reader.pages:
                estratto = page.extract_text()
                if estratto:
                    testo_file += estratto + "\n"
            testo_file += f"\n--- FINE FILE: {file_name} ---\n"
            
            testo_totale += testo_file
            elenco_file.append(file_name)
            
            # Aggiorna barra
            percentuale = int((i + 1) / len(files_pdf) * 100)
            progresso.progress(percentuale, text=f"Letto: {file_name}")
            
        except Exception as e:
            st.error(f"Errore su {file_name}: {e}")
            
    progresso.empty() # Rimuove la barra alla fine
    return testo_totale, elenco_file

# --- CARICAMENTO DELLA CONOSCENZA ---
CARTELLA_DOCS = "documenti"
CONTESTO_BIBLIOTECA, LISTA_FILE = carica_biblioteca(CARTELLA_DOCS)

# --- SIDEBAR: STATO SISTEMA ---
with st.sidebar:
    st.header("🗂️ Biblioteca Scientifica")
    if LISTA_FILE:
        st.success(f"Caricati {len(LISTA_FILE)} documenti.")
        st.markdown("### Fonti attive:")
        for f in LISTA_FILE:
            st.markdown(f"- 📄 *{f}*")
        
        # Mostra quanti caratteri totali ha letto
        st.caption(f"Totale dati: {len(CONTESTO_BIBLIOTECA)} caratteri")
    else:
        st.warning("⚠️ Nessun PDF trovato.")
        st.info("Metti i file nella cartella 'documenti'.")

# --- SETUP AI ---
# INSERISCI LA TUA CHIAVE QUI SOTTO
# La chiave viene presa dai "Secrets" di Streamlit (la cassaforte)
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Chiave API non trovata. Impostala nei Secrets.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# Prompt Avanzato per gestire fonti multiple
ISTRUZIONI_BASE = """
Sei un Senior Clinical Assistant. Hai accesso a una biblioteca di documenti scientifici (qui sotto).
Il tuo compito è rispondere alle domande incrociando le informazioni dai vari documenti.

REGOLE DI RISPOSTA:
1.  **CITA LA FONTE:** Se l'info viene dal "File X", dillo (es. "Secondo le tabelle LARN...").
2.  **GERARCHIA:** Se c'è conflitto, dai priorità ai documenti SINU/LARN 2025.
3.  **PRECISIONE:** Usa i numeri esatti trovati nei testi.
4.  **LIMITI:** Se l'info non esiste in NESSUN documento, dillo chiaramente.

--- INIZIO BIBLIOTECA ---
"""

if CONTESTO_BIBLIOTECA:
    SYSTEM_PROMPT_COMPLETO = ISTRUZIONI_BASE + CONTESTO_BIBLIOTECA + "\n--- FINE BIBLIOTECA ---"
else:
    SYSTEM_PROMPT_COMPLETO = ISTRUZIONI_BASE + "NESSUN DOCUMENTO."

# --- CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Header della chat
st.divider()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Chiedi qualcosa alla tua biblioteca scientifica..."):
    
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Consultazione incrociata documenti..."):
            try:
                # Preparazione storia
                chat_history = []
                for msg in st.session_state.messages:
                    role_gemini = "model" if msg["role"] == "assistant" else "user"
                    chat_history.append(types.Content(
                        role=role_gemini, 
                        parts=[types.Part(text=msg["content"])]
                    ))

                # Chiamata
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=chat_history,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT_COMPLETO,
                        temperature=0.2 # Bassa creatività, alta fedeltà
                    )
                )
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Errore AI: {e}")