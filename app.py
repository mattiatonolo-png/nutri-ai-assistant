import streamlit as st
import os
import pandas as pd
from pypdf import PdfReader
from google import genai
from google.genai import types
from xhtml2pdf import pisa  # <--- NUOVO MOTORE PDF
import markdown             # <--- PER CONVERTIRE TESTO AI IN HTML

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

st.title("🩺 Nutri-AI: Clinical Assistant v2.1")

# --- 3. API KEY ---
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# --- 4. MOTORE PDF PRO (HTML TO PDF) ---
def crea_pdf_html(dati_paziente, testo_ai):
    # 1. Convertiamo il Markdown dell'AI in HTML (supporta tabelle)
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    
    # 2. Convertiamo i dati paziente (che sono testo semplice) in HTML leggibile
    # Sostituiamo i ritorni a capo con <br> per l'HTML
    html_paziente = dati_paziente.replace("\n", "<br>")

    # 3. Template HTML + CSS (Lo Stile del Report)
    html_template = f"""
    <html>
    <head>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: Helvetica, Arial, sans-serif;
                font-size: 12px;
                color: #333;
                line-height: 1.5;
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #2c3e50;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            h1 {{ color: #2c3e50; font-size: 18px; }}
            h2 {{ color: #16a085; font-size: 16px; margin-top: 20px; border-bottom: 1px solid #ddd; }}
            h3 {{ color: #2c3e50; font-size: 14px; margin-top: 15px; }}
            
            .box-paziente {{
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                font-family: Courier, monospace; /* Font tipo macchina da scrivere per i dati */
            }}
            
            /* Stile Tabelle */
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
                margin-bottom: 10px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #2c3e50;
                color: white;
            }}
            
            .footer {{
                position: fixed;
                bottom: 0;
                width: 100%;
                text-align: center;
                font-size: 10px;
                color: #777;
                border-top: 1px solid #ddd;
                padding-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>NUTRI-AI | REPORT CLINICO</h1>
            <p>Documento generato da Intelligenza Artificiale - Supervisione Medica Richiesta</p>
        </div>

        <div class="box-paziente">
            <b>ANAGRAFICA E QUADRO CLINICO:</b><br><br>
            {html_paziente}
        </div>

        <h2>VALUTAZIONE E PIANO NUTRIZIONALE</h2>
        {html_ai}

        <div class="footer">
            Report generato il {pd.Timestamp.now().strftime('%d/%m/%Y')} - Nutri-AI Assistant
        </div>
    </body>
    </html>
    """
    
    # 4. Generazione File PDF
    from io import BytesIO
    result_file = BytesIO()
    
    pisa_status = pisa.CreatePDF(
        html_template,                # Sorgente HTML
        dest=result_file              # Destinazione (in memoria)
    )
    
    if pisa_status.err:
        return None
        
    return result_file.getvalue()

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

# --- 6. SIDEBAR CLINICA ESTESA ---
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
    
    patologie_metaboliche = st.multiselect("Metaboliche", ["Diabete T1", "Diabete T2", "Insulino-resistenza", "Dislipidemia", "Gotta"])
    patologie_gastro = st.multiselect("Gastro-Intestinali", ["IBS (Colon Irritabile)", "Reflusso/Gastrite", "Celiachia", "IBD (Crohn/Colite)", "SIBO"])
    patologie_endocrine = st.multiselect("Endocrine", ["Ipotiroidismo", "Ipertiroidismo", "Hashimoto", "PCOS", "Endometriosi"])
    
    allergie = st.text_input("Allergie/Intolleranze", placeholder="Es. Lattosio, Nichel, Istamina")
    
    st.divider()
    obiettivo = st.selectbox("Obiettivo Clinico", 
                             ["Dimagrimento (Ipocalorica)", "Mantenimento", "Ipertrofia (Ipercalorica)", 
                              "Protocollo Antinfiammatorio", "Gestione Glicemica", "Low FODMAP"])

# --- 7. TABELLA ESAMI SANGUE ---
st.subheader("🩸 Esami Ematici Rilevanti")
st.info("Compila la tabella con i valori fuori range o rilevanti.")

df_template = pd.DataFrame(
    [
        {"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL", "Note": ""},
        {"Esame": "Colesterolo Tot", "Valore": 180, "Unità": "mg/dL", "Note": ""},
        {"Esame": "Ferro", "Valore": 80, "Unità": "mcg/dL", "Note": ""},
        {"Esame": "TSH", "Valore": 2.5, "Unità": "mIU/L", "Note": ""},
        {"Esame": "Vitamina D", "Valore": 30, "Unità": "ng/mL", "Note": ""},
    ]
)

esami_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)
stringa_esami = esami_df.to_string(index=False)

# --- 8. PROMPT DINAMICO ---
PROFILO_PAZIENTE = f"""
ANAGRAFICA: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
PATOLOGIE METABOLICHE: {', '.join(patologie_metaboliche)}
PATOLOGIE GASTRO: {', '.join(patologie_gastro)}
PATOLOGIE ENDOCRINE: {', '.join(patologie_endocrine)}
ALLERGIE: {allergie}
OBIETTIVO: {obiettivo}

ESAMI DEL SANGUE:
{stringa_esami}
"""

ISTRUZIONI_MASTER = f"""
RUOLO: Nutrizionista Clinico Esperto.
BIBLIOTECA: {CONTESTO_BIBLIOTECA}
DATI PAZIENTE: {PROFILO_PAZIENTE}

TASK:
1. Analizza esami e patologie.
2. Crea una strategia nutrizionale basata sui protocolli.
3. IMPORTANTE: Usa TABELLE Markdown per schemi dietetici o liste di alimenti (Es. | Colazione | Pranzo | Cena |).
4. Sii schematico e professionale.
"""

# --- 9. CHAT & OUTPUT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Scrivi qui... (Es: 'Genera piano settimanale')"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Generazione Report Clinico..."):
            try:
                chat_history = []
                for msg in st.session_state.messages:
                    role = "user" if msg["role"] == "user" else "model"
                    chat_history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
                
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
                
                # Generazione PDF HTML
                pdf_bytes = crea_pdf_html(PROFILO_PAZIENTE, response.text)
                
                if pdf_bytes:
                    st.download_button(
                        "🖨️ Scarica Report Ufficiale (PDF)",
                        data=pdf_bytes,
                        file_name="Report_Clinico_NutriAI.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("Errore nella generazione del PDF.")

            except Exception as e:
                st.error(f"Errore: {e}")
