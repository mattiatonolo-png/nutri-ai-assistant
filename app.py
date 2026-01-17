import streamlit as st
import os
import pandas as pd
from pypdf import PdfReader
from google import genai
from google.genai import types
from xhtml2pdf import pisa
import markdown

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
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔒 Accesso Riservato")
        password_input = st.text_input("Password", type="password")
        if st.button("Accedi", use_container_width=True):
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

st.title("🩺 Nutri-AI: Clinical Assistant v3.0")

# --- 3. API KEY ---
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# --- 4. MOTORE PDF "PREMIUM" (Styling Avanzato) ---
def crea_pdf_html(dati_paziente, testo_ai):
    # Convertiamo Markdown in HTML
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    html_paziente = dati_paziente.replace("\n", "<br>")

    # CSS AVANZATO PER DESIGN MEDICO
    html_template = f"""
    <html>
    <head>
        <style>
            @page {{
                size: A4;
                margin: 1.5cm;
                @frame footer_frame {{
                    -pdf-frame-content: footerContent;
                    bottom: 0cm;
                    margin-left: 1.5cm;
                    margin-right: 1.5cm;
                    height: 1cm;
                }}
            }}
            body {{
                font-family: Helvetica, sans-serif;
                font-size: 11px;
                color: #333;
                line-height: 1.4;
            }}
            /* HEADER STYLES */
            .header-bar {{
                background-color: #008080; /* Teal Medico */
                color: white;
                padding: 15px;
                text-align: center;
                border-radius: 5px;
                margin-bottom: 20px;
            }}
            h1 {{ margin:0; font-size: 20px; text-transform: uppercase; }}
            .subtitle {{ font-size: 10px; font-weight: normal; margin-top: 5px; }}

            /* SECTION STYLES */
            h2 {{
                color: #008080;
                font-size: 14px;
                border-bottom: 2px solid #008080;
                padding-bottom: 5px;
                margin-top: 25px;
            }}
            h3 {{ color: #2c3e50; font-size: 12px; margin-top: 15px; font-weight: bold; }}
            
            /* BOX PAZIENTE */
            .box-paziente {{
                background-color: #f0f7f7; /* Grigio/Verde chiarissimo */
                border-left: 5px solid #008080;
                padding: 15px;
                margin-bottom: 20px;
                font-size: 10px;
            }}
            
            /* TABELLE (La parte importante) */
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
                margin-bottom: 15px;
                font-size: 10px;
            }}
            th {{
                background-color: #008080;
                color: white;
                font-weight: bold;
                padding: 8px;
                text-align: left;
                border: 1px solid #006666;
            }}
            td {{
                border: 1px solid #ddd;
                padding: 6px;
                color: #444;
            }}
            /* Effetto Zebra (Righe alterne) */
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            
            /* LISTE */
            ul {{ margin-top: 0; padding-left: 20px; }}
            li {{ margin-bottom: 3px; }}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <h1>Piano Clinico Nutrizionale</h1>
            <div class="subtitle">Generato con Nutri-AI Assistant - Supervisione Medica Richiesta</div>
        </div>

        <div class="box-paziente">
            <strong>QUADRO CLINICO & ANAMNESI:</strong><br><br>
            {html_paziente}
        </div>

        {html_ai}

        <div id="footerContent" style="text-align:center; color:#999; font-size:9px;">
            Report generato il {pd.Timestamp.now().strftime('%d/%m/%Y')} | Documento confidenziale
        </div>
    </body>
    </html>
    """
    
    from io import BytesIO
    result_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=result_file)
    if pisa_status.err: return None
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

# --- 6. SIDEBAR CLINICA AVANZATA ---
with st.sidebar:
    st.header("📋 Anamnesi Paziente")
    
    # Sezione Dati Biometrici
    with st.expander("Dati Biometrici", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            sesso = st.selectbox("Sesso", ["Uomo", "Donna"])
            eta = st.number_input("Età", 18, 100, 30)
        with col2:
            peso = st.number_input("Peso (kg)", 40, 150, 70)
            altezza = st.number_input("Altezza (cm)", 140, 220, 170)

    # Sezione Preferenze Alimentari (NOVITÀ RICHIESTA)
    with st.expander("Regime & Gusti", expanded=True):
        regime = st.selectbox("Tipo di Dieta", 
                              ["Onnivora (Classica)", "Vegetariana", "Vegana", "Pescatariana", "Chetogenica", "Paleo"])
        
        cibi_no = st.text_input("⛔ Alimenti da Escludere", 
                                placeholder="Es. Cipolla, Broccoli, Coriandolo...")

    # Sezione Patologie
    with st.expander("Quadro Patologico"):
        patologie_metaboliche = st.multiselect("Metaboliche", ["Diabete T1", "Diabete T2", "Insulino-resistenza", "Dislipidemia", "Gotta"])
        patologie_gastro = st.multiselect("Gastro-Intestinali", ["IBS (Colon Irritabile)", "Reflusso/Gastrite", "Celiachia", "IBD", "SIBO"])
        patologie_endocrine = st.multiselect("Endocrine", ["Ipotiroidismo", "Ipertiroidismo", "Hashimoto", "PCOS", "Endometriosi"])
        allergie = st.text_input("Allergie/Intolleranze", placeholder="Es. Lattosio, Nichel")
    
    st.divider()
    obiettivo = st.selectbox("Obiettivo Clinico", 
                             ["Dimagrimento", "Mantenimento", "Ipertrofia", "Antinfiammatorio", "Gestione Glicemica"])

# --- 7. TABELLA ESAMI SANGUE ---
st.subheader("🩸 Esami Ematici & Note")
col_sx, col_dx = st.columns([2, 1])

with col_sx:
    # Tabella più compatta
    df_template = pd.DataFrame([
        {"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL"},
        {"Esame": "Colesterolo Tot", "Valore": 180, "Unità": "mg/dL"},
        {"Esame": "Ferro", "Valore": 80, "Unità": "mcg/dL"},
        {"Esame": "TSH", "Valore": 2.5, "Unità": "mIU/L"},
    ])
    esami_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)

with col_dx:
    st.info(f"📚 Fonti attive: {len(LISTA_FILE)}")
    st.caption("Modifica i valori in tabella prima di chiedere il consulto.")

# --- 8. PROMPT DINAMICO AGGIORNATO ---
stringa_esami = esami_df.to_string(index=False)
PROFILO_PAZIENTE = f"""
ANAGRAFICA: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
REGIME ALIMENTARE: {regime}
CIBI DA ESCLUDERE (Gusti personali): {cibi_no}
PATOLOGIE: {', '.join(patologie_metaboliche + patologie_gastro + patologie_endocrine)}
ALLERGIE: {allergie}
OBIETTIVO: {obiettivo}

ESAMI DEL SANGUE:
{stringa_esami}
"""

# --- 8. PROMPT DINAMICO AVANZATO (ARCHITETTURA LOGICA V1) ---
stringa_esami = esami_df.to_string(index=False)

PROFILO_PAZIENTE = f"""
ANAGRAFICA: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
REGIME ALIMENTARE: {regime}
CIBI DA ESCLUDERE (Gusti/Etica): {cibi_no}
PATOLOGIE: {', '.join(patologie_metaboliche + patologie_gastro + patologie_endocrine)}
ALLERGIE: {allergie}
OBIETTIVO: {obiettivo}

ESAMI DEL SANGUE RILEVATI:
{stringa_esami}
"""

ISTRUZIONI_MASTER = f"""
RUOLO:
Sei un Nutrizionista Clinico Esperto basato su evidenze scientifiche (Evidence-Based Practice).
La tua logica decisionale deve seguire RIGOROSAMENTE la seguente gerarchia a 3 livelli.

LIVELLO 1: HARD CONSTRAINTS (SICUREZZA & NORMATIVA - INVIOLABILI)
1.  **Sicurezza Tossicologica (EFSA):**
    * Se un integratore o nutriente supera il Tolerable Upper Intake Level (UL), genera un ALERT immediato.
    * Vitamine Critiche: Attenzione a Vitamina A (Retinolo) e Vitamina D in caso di sovradosaggio.
2.  **Valori Critici di Laboratorio (Panic Values):**
    * Se rilevi Potassio < 2.5 o > 6.0 mmol/L -> STOP consigli dietetici, consiglia PS.
    * Se rilevi Glucosio < 50 mg/dL o > 400 mg/dL -> STOP consigli dietetici, consiglia PS.
3.  **Allergie & Celiachia:**
    * Se Diagnosi = Celiachia -> GLUTINE = 0 (Tolleranza Zero, nessuna contaminazione).
    * Se Allergia X -> Escludere tassativamente X e derivati.

LIVELLO 2: CLINICAL LOGIC (LINEE GUIDA CONDIZIONALI)
Applica le seguenti regole "IF-THEN" basate sul profilo paziente:
* **Diabete / Insulino-Resistenza:**
    * Target Zuccheri Semplici: < 15% Energia Totale (LARN 2024).
    * Preferire Carboidrati a Basso Indice Glicemico (Legumi, Cereali in chicco).
* **IBS (Intestino Irritabile):**
    * Se Diagnosi = IBS -> Suggerisci protocollo Low-FODMAP (Fase 1: Esclusione 4 settimane).
    * Escludere: Aglio, Cipolla, Legumi non decorticati, Frutta ad alto fruttosio.
* **PCOS (Ovaio Policistico):**
    * Se Fenotipo A (Iperandrogenico) -> Focus su Carico Glicemico (Low GL) + Inositoli (Rapporto 40:1 come supporto).
* **Salute Cardiovascolare:**
    * Grassi Saturi: < 10% Energia Totale.
    * Colesterolo: < 300 mg/die.

LIVELLO 3: OPTIMIZATION & QUALITY (SOFT TARGETS)
Se i livelli 1 e 2 sono soddisfatti, ottimizza la qualità:
1.  **Qualità Materia Prima:** Preferire carne Grass-Fed (miglior profilo Omega-3/6) rispetto a Grain-Fed.
2.  **Bio vs Convenzionale:** Suggerire Biologico per la "Dirty Dozen" (frutta/verdura con buccia edibile) per ridurre carico pesticidi.
3.  **Sostenibilità:** Privilegiare proteine vegetali e prodotti stagionali.
4.  **Sport:** Timing proteico (20-40g ogni 3-4h) per massimizzare la sintesi proteica (MPS).

BIBLIOTECA DI RIFERIMENTO (USALA PER I DETTAGLI):
{CONTESTO_BIBLIOTECA}

DATI PAZIENTE ATTUALE:
{PROFILO_PAZIENTE}

TASK OPERATIVO:
1. Analizza il caso clinico applicando la gerarchia (Livello 1 -> 2 -> 3).
2. Genera un output strutturato (Analisi Clinica -> Strategia Nutrizionale -> Esempio Pratico).
3. IMPORTANTE: Usa Tabelle Markdown per schemi dietetici.
"""
PORTANTE PER IL LAYOUT: Usa tabelle Markdown (| Colonna 1 | Colonna 2 |) per le diete. Verranno convertite in tabelle professionali nel PDF.
"""

# --- 9. CHAT & OUTPUT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Es: 'Genera dieta settimanale in tabella'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Elaborazione piano clinico..."):
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
                
                # PDF
                pdf_bytes = crea_pdf_html(PROFILO_PAZIENTE, response.text)
                if pdf_bytes:
                    st.download_button(
                        "🖨️ Scarica Report PDF (Stile Clinico)",
                        data=pdf_bytes,
                        file_name="Piano_Nutrizionale.pdf",
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"Errore: {e}")
