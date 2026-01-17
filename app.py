import streamlit as st
import os
import pandas as pd
from pypdf import PdfReader
from google import genai
from google.genai import types
from fpdf import FPDF

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Nutri-AI Clinical", page_icon="🩺", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- 2. SISTEMA DI LOGIN ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.title("🔒 Accesso Riservato")
    password_input = st.text_input("Password", type="password")
    if st.button("Accedi"):
        try:
            if password_input == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password errata.")
        except:
            st.error("Password non configurata nei Secrets!")
    return False

if not check_password():
    st.stop()

# =========================================================
# APP REALE
# =========================================================

st.title("🩺 Nutri-AI: Clinical Assistant v2.0")

# --- 3. API KEY ---
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# --- 4. MOTORE PDF (Base) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Nutri-AI Report', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def crea_pdf_download(paziente_txt, dieta_txt):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Nota: FPDF fatica con le tabelle complesse. Per ora stampiamo testo pulito.
    safe_text = (paziente_txt + "\n\n" + dieta_txt).encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 6, safe_text)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. DATA INGESTION ---
@st.cache_resource
def carica_biblioteca():
    cartella = "documenti"
    testo_totale = ""
    if not os.path.exists(cartella): return "", []
    files = [f for f in os.listdir(cartella) if f.endswith('.pdf')]
    if not files: return "", []
    for f in files:
        try:
            reader = PdfReader(os.path.join(cartella, f))
            for p in reader.pages:
                if p.extract_text(): testo_totale += p.extract_text() + "\n"
        except: pass
    return testo_totale, files

CONTESTO_BIBLIOTECA, LISTA_FILE = carica_biblioteca()

# --- 6. SIDEBAR CLINICA ESTESA (NOVITÀ MEDICALE) ---
with st.sidebar:
    st.header("📋 Anamnesi Paziente")
    
    col1, col2 = st.columns(2)
    with col1:
        sesso = st.selectbox("Sesso", ["Uomo", "Donna"])
        eta = st.number_input("Età", 18, 100, 30)
    with col2:
        peso = st.number_input("Peso (kg)", 40, 150, 70)
        altezza = st.number_input("Altezza (cm)", 140, 220, 170)
    
    st.divider()
    st.subheader("Quadro Patologico")
    
    # ### NOVITÀ: LISTE ESTESE ###
    patologie_metaboliche = st.multiselect("Metaboliche", ["Diabete T1", "Diabete T2", "Insulino-resistenza", "Dislipidemia", "Gotta"])
    patologie_gastro = st.multiselect("Gastro-Intestinali", ["IBS (Colon Irritabile)", "Reflusso/Gastrite", "Celiachia", "IBD (Crohn/Colite)", "SIBO"])
    patologie_endocrine = st.multiselect("Endocrine", ["Ipotiroidismo", "Ipertiroidismo", "Hashimoto", "PCOS", "Endometriosi"])
    
    allergie = st.text_input("Allergie/Intolleranze", placeholder="Es. Lattosio, Nichel, Istamina")
    
    st.divider()
    obiettivo = st.selectbox("Obiettivo Clinico", 
                             ["Dimagrimento (Ipocalorica)", "Mantenimento", "Ipertrofia (Ipercalorica)", 
                              "Protocollo Antinfiammatorio", "Gestione Glicemica", "Low FODMAP"])

# --- 7. TABELLA ESAMI DEL SANGUE (NOVITÀ TECNICA) ---
st.subheader("🩸 Esami Ematici Rilevanti")
st.info("Compila la tabella con i valori fuori range o rilevanti per l'AI.")

# Creiamo un DataFrame vuoto come template
df_template = pd.DataFrame(
    [
        {"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL", "Note": ""},
        {"Esame": "Colesterolo Tot", "Valore": 180, "Unità": "mg/dL", "Note": ""},
        {"Esame": "Ferro", "Valore": 80, "Unità": "mcg/dL", "Note": ""},
        {"Esame": "TSH", "Valore": 2.5, "Unità": "mIU/L", "Note": ""},
    ]
)

# Editor interattivo: l'utente può aggiungere righe!
esami_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)

# Trasformiamo la tabella in testo per l'AI
stringa_esami = esami_df.to_string(index=False)

# --- 8. PROMPT DINAMICO ---
PROFILO_PAZIENTE = f"""
ANAGRAFICA: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
PATOLOGIE METABOLICHE: {', '.join(patologie_metaboliche)}
PATOLOGIE GASTRO: {', '.join(patologie_gastro)}
PATOLOGIE ENDOCRINE: {', '.join(patologie_endocrine)}
ALLERGIE: {allergie}
OBIETTIVO: {obiettivo}

ESAMI DEL SANGUE RILEVATI:
{stringa_esami}
"""

ISTRUZIONI_MASTER = f"""
RUOLO: Nutrizionista Clinico Esperto.
Usa ESCLUSIVAMENTE la seguente BIBLIOTECA per rispondere:
{CONTESTO_BIBLIOTECA}

DATI PAZIENTE:
{PROFILO_PAZIENTE}

TASK:
1. Analizza gli esami del sangue forniti: evidenzia valori critici in base alle patologie.
2. Elabora una strategia nutrizionale basata sui protocolli della Biblioteca.
3. Se generi una dieta, usa liste puntate semplici (NO tabelle markdown complesse) per facilitare la stampa PDF.
"""

# --- 9. CHAT & OUTPUT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Es: 'Analizza gli esami e crea schema settimanale'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisi clinica in corso..."):
            try:
                # Prepara la cronologia
                chat_history = []
                for msg in st.session_state.messages:
                    role = "user" if msg["role"] == "user" else "model"
                    chat_history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
                
                # Chiamata AI
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=chat_history,
                    config=types.GenerateContentConfig(
                        system_instruction=ISTRUZIONI_MASTER,
                        temperature=0.3
                    )
                )
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                # Bottone PDF
                st.download_button(
                    "🖨️ Scarica Report",
                    data=crea_pdf_download(PROFILO_PAZIENTE, response.text),
                    file_name="report_clinico.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Errore: {e}")
