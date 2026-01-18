import streamlit as st
import os
import pandas as pd
import time
import shutil
from pypdf import PdfReader
from google import genai
from google.genai import types
from xhtml2pdf import pisa
import markdown

# --- LIBRERIE RAG & GESTIONE ERRORI IMPORT ---
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.document import Document

# =========================================================
# 1. CONFIGURAZIONE INIZIALE
# =========================================================
st.set_page_config(page_title="Nutri-AI Clinical", page_icon="🩺", layout="wide")
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# --- SISTEMA DI LOGIN ---
def check_password():
    if "authenticated" not in st.session_state: st.session_state.authenticated = False
    if st.session_state.authenticated: return True
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔒 Accesso Riservato")
        pwd = st.text_input("Password", type="password")
        if st.button("Accedi", use_container_width=True):
            try:
                if pwd == st.secrets["APP_PASSWORD"]:
                    st.session_state.authenticated = True
                    st.rerun()
                else: st.error("Password errata.")
            except: st.error("Password non configurata nei Secrets!")
    return False

if not check_password(): st.stop()

st.title("🩺 Nutri-AI: Clinical Assistant v6.0 (Master)")

# --- API KEY ---
try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("ERRORE CRITICO: Manca API KEY nei Secrets.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# =========================================================
# 2. MOTORE PDF (MEDICAL DESIGN)
# =========================================================
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
            .box-paziente {{ background-color: #f0f7f7; border-left: 5px solid #008080; padding: 15px; margin-bottom: 20px; font-size: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px; font-size: 10px; }}
            th {{ background-color: #008080; color: white; font-weight: bold; padding: 8px; text-align: left; border: 1px solid #006666; }}
            td {{ border: 1px solid #ddd; padding: 6px; color: #444; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <h1>Piano Clinico Nutrizionale</h1>
            <div class="subtitle">Generato con Nutri-AI Assistant - Supervisione Medica Richiesta</div>
        </div>
        <div class="box-paziente"><strong>QUADRO CLINICO & ANAMNESI:</strong><br><br>{html_paziente}</div>
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

# =========================================================
# 3. MOTORE VETTORIALE (DISK PERSISTENCE + BATCHING)
# =========================================================
@st.cache_resource
def gestisci_indice_vettoriale():
    cartella_docs = "documenti"
    cartella_index = "faiss_index_store" 
    
    # Usiamo il modello embedding più recente
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=LA_MIA_API_KEY)
    
    # --- A. TENTATIVO CARICAMENTO RAPIDO DA DISCO ---
    if os.path.exists(cartella_index):
        try:
            # allow_dangerous_deserialization=True è necessario per file locali fidati
            vector_store = FAISS.load_local(cartella_index, embeddings, allow_dangerous_deserialization=True)
            files_count = len([f for f in os.listdir(cartella_docs) if f.endswith('.pdf')]) if os.path.exists(cartella_docs) else 0
            return vector_store, files_count, "⚡ Caricato da Disco (Istantaneo)"
        except Exception as e:
            pass # Se fallisce (es. file corrotto), proseguiamo con la ricostruzione
    
    # --- B. RICOSTRUZIONE DA ZERO (Lento, ma necessario la prima volta) ---
    if not os.path.exists(cartella_docs): return None, 0, "⚠️ Cartella documenti assente"
    files = [f for f in os.listdir(cartella_docs) if f.endswith('.pdf')]
    if not files: return None, 0, "⚠️ Nessun PDF trovato"

    docs = []
    for file_name in files:
        path = os.path.join(cartella_docs, file_name)
        try:
            reader = PdfReader(path)
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t
            docs.append(Document(page_content=text, metadata={"source": file_name}))
        except: pass
    
    # Chunking: Pezzi da 2000 caratteri con sovrapposizione
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    vector_store = None
    batch_size = 10
    total_chunks = len(splits)
    
    # Feedback visivo durante il caricamento lento
    my_bar = st.progress(0, text="Costruzione Biblioteca in corso (Richiesto solo al primo avvio)...")

    for i in range(0, total_chunks, batch_size):
        batch = splits[i : i + batch_size]
        try:
            if vector_store is None:
                vector_store = FAISS.from_documents(batch, embeddings)
            else:
                vector_store.add_documents(batch)
            
            # Pausa tattica per evitare Error 429 di Google
            time.sleep(1.5)
            my_bar.progress(min(1.0, (i+batch_size)/total_chunks))
        except Exception:
            time.sleep(5) # Se errore, aspetta di più e riprova
            continue
            
    my_bar.empty()
    
    # SALVATAGGIO SU DISCO (Per i prossimi avvii)
    if vector_store:
        vector_store.save_local(cartella_index)
        
    return vector_store, len(files), "✅ Indice Costruito e Salvato"

VECTOR_STORE, NUM_FILES, STATUS_MSG = gestisci_indice_vettoriale()

# =========================================================
# 4. INTERFACCIA UTENTE (SIDEBAR + TOOLS)
# =========================================================
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
        regime = st.selectbox("Regime Alimentare", ["Onnivora", "Vegetariana", "Vegana", "Pescatariana", "Chetogenica", "Paleo"])
        cibi_no = st.text_input("⛔ Esclusioni", placeholder="Es. Cipolla, Broccoli...")

    with st.expander("Quadro Clinico"):
        metaboliche = st.multiselect("Metaboliche", ["Diabete T1", "Diabete T2", "Insulino-resistenza", "Dislipidemia", "Gotta"])
        gastro = st.multiselect("Gastro-Intestinali", ["IBS", "Reflusso", "Celiachia", "IBD", "SIBO"])
        obiettivo = st.selectbox("Obiettivo", ["Dimagrimento", "Mantenimento", "Ipertrofia", "Antinfiammatorio", "Gestione Glicemica"])

    st.divider()
    
    # --- SEZIONE ADMIN & DEBUG (NUOVA) ---
    with st.expander("🛠️ Admin & Debug Tools"):
        st.caption(f"Status: {STATUS_MSG}")
        
        # 1. Ricostruzione forzata
        if st.button("🔄 Forza Ricostruzione Indice"):
            try:
                if os.path.exists("faiss_index_store"):
                    shutil.rmtree("faiss_index_store")
                st.cache_resource.clear()
                st.rerun()
            except: pass
            
        # 2. Download per GitHub
        if os.path.exists("faiss_index_store"):
            shutil.make_archive("indice_backup", 'zip', "faiss_index_store")
            with open("indice_backup.zip", "rb") as fp:
                st.download_button("💾 Scarica Indice (ZIP)", data=fp, file_name="faiss_index_store.zip", mime="application/zip", help="Scarica e carica su GitHub per avvio veloce.")
        
        st.divider()
        st.write("🕵️‍♂️ **Debug Inspector**")
        debug_query = st.text_input("Cerca nel DB (es. 'Ferro')", key="dbg")
        if debug_query and VECTOR_STORE:
            docs = VECTOR_STORE.similarity_search(debug_query, k=2)
            for i, d in enumerate(docs):
                st.markdown(f"**Risultato {i+1}** ({d.metadata.get('source', 'unknown')})")
                st.code(d.page_content, language="markdown")

# =========================================================
# 5. MAIN SCREEN & ESAMI
# =========================================================
st.subheader("🩸 Esami Ematici & Note")
col_sx, col_dx = st.columns([2, 1])

with col_sx:
    df_template = pd.DataFrame([
        {"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL"},
        {"Esame": "Colesterolo Tot", "Valore": 180, "Unità": "mg/dL"},
        {"Esame": "TSH", "Valore": 2.5, "Unità": "mIU/L"},
    ])
    esami_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True)

with col_dx:
    if VECTOR_STORE:
        st.success(f"📚 {NUM_FILES} Fonti Attive")
    else:
        st.error("❌ Errore Caricamento Fonti")

# Costruzione Profilo Stringa
PROFILO_PAZIENTE = f"""
PAZIENTE: {sesso}, {eta} anni, {peso}kg, {altezza}cm.
DIETA: {regime}. ESCLUSIONI: {cibi_no}.
PATOLOGIE: {', '.join(metaboliche + gastro)}. OBIETTIVO: {obiettivo}.
ESAMI SANGUE:
{esami_df.to_string(index=False)}
"""

# =========================================================
# 6. CHATBOT LOGIC (RAG)
# =========================================================
if "messages" not in st.session_state: st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]): st.markdown(message["content"])

if prompt := st.chat_input("Scrivi qui la tua richiesta clinica..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisi vettoriale e clinica in corso..."):
            try:
                # 1. RETRIEVAL (Ricerca semantica)
                # Arricchiamo la query con le patologie per trovare i protocolli giusti
                query_arricchita = f"{prompt} {', '.join(metaboliche + gastro)} {obiettivo}"
                
                context_text = ""
                if VECTOR_STORE:
                    docs_found = VECTOR_STORE.similarity_search(query_arricchita, k=5)
                    for doc in docs_found:
                        context_text += f"\n--- FONTE: {doc.metadata.get('source', 'Unknown')} ---\n{doc.page_content}\n"
                else:
                    context_text = "Nessun documento disponibile nel database."

                # 2. PROMPT CLINICO (Logica a 3 Livelli)
                ISTRUZIONI_MASTER = f"""
                RUOLO: Nutrizionista Clinico Esperto (Evidence-Based).
                
                FONTI RECUPERATE (Usa ESCLUSIVAMENTE queste per i consigli tecnici):
                {context_text}
                
                DATI PAZIENTE:
                {PROFILO_PAZIENTE}
                
                LOGICA DECISIONALE (MANDATORY):
                LIVELLO 1: HARD CONSTRAINTS (SICUREZZA)
                - Panic Values: Se esami gravi (es. Potassio <2.5), STOP dieta -> PS.
                - Celiachia/Allergie: Tolleranza zero.
                
                LIVELLO 2: CLINICAL LOGIC
                - Diabete: Zuccheri < 15% En.Tot., Carboidrati Low GI.
                - IBS: Protocollo Low-FODMAP (se applicabile).
                - Cardio: Saturi < 10%.
                
                LIVELLO 3: OPTIMIZATION
                - Qualità: Grass-Fed, Bio.
                - Sostenibilità & Sport.

                TASK:
                1. Analizza la richiesta usando SOLO le fonti e i dati paziente.
                2. Rispetta il REGIME ({regime}) e le ESCLUSIONI ({cibi_no}).
                3. Genera una risposta professionale strutturata.
                4. IMPORTANTE: Usa tabelle Markdown (| A | B |) per i piani alimentari (essenziale per PDF).
                """

                # 3. GENERAZIONE
                chat_history = [types.Content(role="user", parts=[types.Part(text=prompt)])]
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=chat_history,
                    config=types.GenerateContentConfig(system_instruction=ISTRUZIONI_MASTER, temperature=0.3)
                )
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                # 4. EXPORT PDF
                pdf_bytes = crea_pdf_html(PROFILO_PAZIENTE, response.text)
                if pdf_bytes:
                    st.download_button("🖨️ Scarica Report PDF", data=pdf_bytes, file_name="Piano_Nutrizionale.pdf", mime="application/pdf")
            
            except Exception as e:
                st.error(f"Errore durante l'elaborazione: {e}")
