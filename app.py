import streamlit as st
import os
import pandas as pd
import time  # <--- NUOVO IMPORT NECESSARIO
from pypdf import PdfReader
from google import genai
from google.genai import types
from xhtml2pdf import pisa
import markdown

# --- LIBRERIE RAG ---
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.document import Document

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

st.title("🩺 Nutri-AI: Vector Clinical Assistant v4.1 (Stable)")

# --- 3. API KEY ---
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# --- 4. MOTORE PDF ---
def crea_pdf_html(dati_paziente, testo_ai):
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    html_paziente = dati_paziente.replace("\n", "<br>")

    html_template = f"""
    <html>
    <head>
        <style>
            @page {{ size: A4; margin: 1.5cm; @frame footer_frame {{ -pdf-frame-content: footerContent; bottom: 0cm; margin-left: 1.5cm; margin-right: 1.5cm; height: 1cm; }} }}
            body {{ font-family: Helvetica, sans-serif; font-size: 11px; color: #333; line-height: 1.4; }}
            .header-bar {{ background-color: #008080; color: white; padding: 15px; text-align: center; border-radius: 5px; margin-bottom: 20px; }}
            h1 {{ margin:0; font-size: 20px; text-transform: uppercase; }}
            .subtitle {{ font-size: 10px; font-weight: normal; margin-top: 5px; }}
            h2 {{ color: #008080; font-size: 14px; border-bottom: 2px solid #008080; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: #2c3e50; font-size: 12px; margin-top: 15px; font-weight: bold; }}
            .box-paziente {{ background-color: #f0f7f7; border-left: 5px solid #008080; padding: 15px; margin-bottom: 20px; font-size: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px; font-size: 10px; }}
            th {{ background-color: #008080; color: white; font-weight: bold; padding: 8px; text-align: left; border: 1px solid #006666; }}
            td {{ border: 1px solid #ddd; padding: 6px; color: #444; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            ul {{ margin-top: 0; padding-left: 20px; }}
            li {{ margin-bottom: 3px; }}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <h1>Piano Clinico Nutrizionale</h1>
            <div class="subtitle">Generato con Nutri-AI Assistant - Supervisione Medica Richiesta</div>
        </div>
        <div class="box-paziente"><strong>QUADRO CLINICO & ANAMNESI:</strong><br><br>{html_paziente}</div>
        {html_ai}
        <div id="footerContent" style="text-align:center; color:#999; font-size:9px;">Report generato il {pd.Timestamp.now().strftime('%d/%m/%Y')} | Documento confidenziale</div>
    </body>
    </html>
    """
    from io import BytesIO
    result_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=result_file)
    if pisa_status.err: return None
    return result_file.getvalue()

# --- 5. DATA INGESTION VETTORIALE (SMART BATCHING) ---
@st.cache_resource
def costruisci_indice_vettoriale():
    """Legge i PDF e li indicizza 'a piccoli morsi' per non bloccare le API."""
    cartella = "documenti"
    if not os.path.exists(cartella): return None, 0
    
    files = [f for f in os.listdir(cartella) if f.endswith('.pdf')]
    if not files: return None, 0

    docs = []
    # 1. Lettura File
    for file_name in files:
        path = os.path.join(cartella, file_name)
        try:
            reader = PdfReader(path)
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t
            docs.append(Document(page_content=text, metadata={"source": file_name}))
        except: pass
    
    if not docs: return None, 0

    # 2. Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    # 3. Embedding con BATCHING (La correzione fondamentale)
    # Usiamo il modello text-embedding-004 che è più robusto
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=LA_MIA_API_KEY)
    
    vector_store = None
    batch_size = 10  # Processiamo 10 pezzi alla volta
    total_chunks = len(splits)
    
    # Barra di avanzamento visiva per l'utente
    progress_text = "Indicizzazione Documenti in corso... (Questo avviene solo al primo avvio)"
    my_bar = st.progress(0, text=progress_text)

    for i in range(0, total_chunks, batch_size):
        # Prendiamo un "boccone" di documenti
        batch = splits[i : i + batch_size]
        
        try:
            if vector_store is None:
                vector_store = FAISS.from_documents(batch, embeddings)
            else:
                vector_store.add_documents(batch)
            
            # Aggiorniamo la barra
            percent_complete = min(1.0, (i + batch_size) / total_chunks)
            my_bar.progress(percent_complete, text=f"Indicizzazione: {int(percent_complete*100)}%")
            
            # PAUSA DI RESPIRO per le API di Google (Evita Error 429)
            time.sleep(2) 
            
        except Exception as e:
            st.warning(f"Errore nel batch {i}: {e}")
            time.sleep(5) # Se c'è errore, aspetta di più e riprova col prossimo
            continue
            
    my_bar.empty() # Rimuovi la barra alla fine
    return vector_store, len(files)

VECTOR_STORE, NUM_FILES = costruisci_indice_vettoriale()

# --- 6. SIDEBAR CLINICA ---
with st.sidebar:
    st.header("📋 Anamnesi Paziente")
    with st.expander("Dati Biometrici", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            sesso = st.selectbox("Sesso", ["Uomo", "Donna"])
            eta = st.number_input("Età", 18, 100, 30)
        with col2:
            peso = st.number_input("Peso (kg)", 40, 150, 70)
            altezza = st.number_input("Altezza (cm)", 140, 220, 170)

    with st.expander("Regime & Gusti", expanded=True):
        regime = st.selectbox("Tipo di Dieta", ["Onnivora (Classica)", "Vegetariana", "Vegana", "Pescatariana", "Chetogenica", "Paleo"])
        cibi_no = st.text_input("⛔ Alimenti da Escludere", placeholder="Es. Cipolla, Broccoli...")

    with st.expander("Quadro Patologico"):
        patologie_metaboliche = st.multiselect("Metaboliche", ["Diabete T1", "Diabete T2", "Insulino-resistenza", "Dislipidemia", "Gotta"])
        patologie_gastro = st.multiselect("Gastro-Intestinali", ["IBS (Colon Irritabile)", "Reflusso/Gastrite", "Celiachia", "IBD", "SIBO"])
        patologie_endocrine = st.multiselect("Endocrine", ["Ipotiroidismo", "Ipertiroidismo", "Hashimoto", "PCOS", "Endometriosi"])
        allergie = st.text_input("Allergie/Intolleranze", placeholder="Es. Lattosio, Nichel")
    
    st.divider()
    obiettivo = st.selectbox("Obiettivo Clinico", ["Dimagrimento", "Mantenimento", "Ipertrofia", "Antinfiammatorio", "Gestione Glicemica"])

# --- 7. TABELLA ESAMI ---
st.subheader("🩸 Esami Ematici & Note")
col_sx, col_dx = st.columns([2, 1])

with col_sx:
    df_template = pd.DataFrame([
        {"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL"},
        {"Esame": "Colesterolo Tot", "Valore": 180, "Unità": "mg/dL"},
        {"Esame": "Ferro", "Valore": 80, "Unità": "mcg/dL"},
        {"Esame": "TSH", "Valore": 2.5, "Unità": "mIU/L"},
    ])
    esami_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)

with col_dx:
    if VECTOR_STORE:
        st.success(f"📚 {NUM_FILES} Fonti Indicizzate")
        st.caption("Motore vettoriale attivo.")
    else:
        st.warning("⚠️ Nessun documento nella cartella!")

# --- 8. PROFILO ---
stringa_esami = esami_df.to_string(index=False)
PROFILO_PAZIENTE = f"""
ANAGRAFICA: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
REGIME ALIMENTARE: {regime}
CIBI DA ESCLUDERE: {cibi_no}
PATOLOGIE: {', '.join(patologie_metaboliche + patologie_gastro + patologie_endocrine)}
ALLERGIE: {allergie}
OBIETTIVO: {obiettivo}

ESAMI DEL SANGUE:
{stringa_esami}
"""

# --- 9. CHAT & RAG ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Scrivi qui la tua richiesta clinica..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisi vettoriale in corso..."):
            try:
                query_arricchita = f"{prompt} {', '.join(patologie_metaboliche + patologie_gastro)} {obiettivo}"
                context_text = ""
                if VECTOR_STORE:
                    docs_found = VECTOR_STORE.similarity_search(query_arricchita, k=5)
                    for doc in docs_found:
                        context_text += f"\n--- FONTE: {doc.metadata['source']} ---\n{doc.page_content}\n"
                else:
                    context_text = "Nessun documento disponibile."

                ISTRUZIONI_RAG = f"""
                RUOLO: Nutrizionista Clinico Esperto (Evidence-Based).
                
                FONTI SCIENTIFICHE RECUPERATE:
                {context_text}
                
                DATI PAZIENTE:
                {PROFILO_PAZIENTE}
                
                LOGICA DECISIONALE (MANDATORY):
                LIVELLO 1: HARD CONSTRAINTS (SICUREZZA)
                - Panic Values (es. Potassio/Glucosio estremi).
                - Celiachia/Allergie: Tolleranza zero.
                
                LIVELLO 2: CLINICAL LOGIC
                - Diabete: Zuccheri < 15% En.Tot.
                - IBS: Protocollo Low-FODMAP.
                - Cardio: Saturi < 10%.
                
                LIVELLO 3: OPTIMIZATION
                - Qualità (Grass-Fed/Bio), Sostenibilità, Sport.

                TASK:
                1. Analizza la richiesta usando SOLO le fonti recuperate e i Dati Paziente.
                2. Rispetta tassativamente il REGIME: {regime} e ESCLUSIONI: {cibi_no}.
                3. Genera risposta strutturata.
                4. IMPORTANTE: Usa tabelle Markdown (| A | B |) per le diete.
                """

                chat_history = [types.Content(role="user", parts=[types.Part(text=prompt)])]
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=chat_history,
                    config=types.GenerateContentConfig(system_instruction=ISTRUZIONI_RAG, temperature=0.3)
                )
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                pdf_bytes = crea_pdf_html(PROFILO_PAZIENTE, response.text)
                if pdf_bytes:
                    st.download_button("🖨️ Scarica Report PDF", data=pdf_bytes, file_name="Piano_Nutrizionale.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Errore: {e}")
