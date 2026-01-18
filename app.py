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

# --- GESTIONE IMPORT ROBUSTA ---
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.document import Document

# =========================================================
# 1. CONFIGURAZIONE
# =========================================================
st.set_page_config(page_title="Nutri-AI Clinical", page_icon="🩺", layout="wide")
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# --- LOGIN ---
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

# --- DEBUG POINT 1 ---
st.warning("⚠️ DEBUG: Login superato. Inizio caricamento componenti...")

try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
    st.success("✅ API KEY trovata.")
except:
    st.error("ERRORE: Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# =========================================================
# 2. MOTORE PDF
# =========================================================
def crea_pdf_html(dati_paziente, testo_ai):
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    html_paziente = dati_paziente.replace("\n", "<br>")
    
    html_template = f"""
    <html><body>
        <h1>Piano Clinico</h1>
        <div>{html_paziente}</div>
        <hr>
        {html_ai}
    </body></html>
    """
    from io import BytesIO
    result_file = BytesIO()
    pisa.CreatePDF(html_template, dest=result_file)
    return result_file.getvalue()

# =========================================================
# 3. MOTORE VETTORIALE (CON DEBUG PRINT)
# =========================================================
@st.cache_resource
def gestisci_indice_vettoriale():
    st.info("🔄 DEBUG: Avvio funzione indice vettoriale...")
    cartella_docs = "documenti"
    cartella_index = "faiss_index_store" 
    
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=LA_MIA_API_KEY)
    
    # --- STRATEGIA A: CARICAMENTO DA DISCO ---
    if os.path.exists(cartella_index):
        st.info(f"📂 DEBUG: Trovata cartella '{cartella_index}'. Tento il caricamento...")
        try:
            # Controllo file dentro la cartella
            files_in_index = os.listdir(cartella_index)
            st.write(f"File trovati nell'indice: {files_in_index}")
            
            vector_store = FAISS.load_local(cartella_index, embeddings, allow_dangerous_deserialization=True)
            files_presenti = len(os.listdir(cartella_docs)) if os.path.exists(cartella_docs) else 0
            st.success("✅ Indice caricato da disco con successo!")
            return vector_store, files_presenti, "⚡ Memoria Persistente (GitHub/Locale)"
        except Exception as e:
            st.error(f"❌ ERRORE CARICAMENTO INDICE: {e}")
            st.warning("Proseguo con la ricostruzione da zero...")
    else:
        st.warning(f"⚠️ DEBUG: Cartella '{cartella_index}' NON trovata. Passo alla ricostruzione.")
    
    # --- STRATEGIA B: RICOSTRUZIONE ---
    st.info("🏗️ DEBUG: Inizio ricostruzione indice dai PDF...")
    if not os.path.exists(cartella_docs): return None, 0, "⚠️ Cartella Documenti Assente"
    files = [f for f in os.listdir(cartella_docs) if f.endswith('.pdf')]
    st.write(f"PDF Trovati: {len(files)}")
    
    if not files: return None, 0, "⚠️ Nessun PDF Trovato"

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
    
    st.write("DEBUG: Testo estratto. Chunking...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    vector_store = None
    batch_size = 10
    total_chunks = len(splits)
    my_bar = st.progress(0, text="Indicizzazione...")

    for i in range(0, total_chunks, batch_size):
        batch = splits[i : i + batch_size]
        try:
            if vector_store is None:
                vector_store = FAISS.from_documents(batch, embeddings)
            else:
                vector_store.add_documents(batch)
            time.sleep(1.0)
            my_bar.progress(min(1.0, (i+batch_size)/total_chunks))
        except Exception as e:
            st.write(f"Errore batch: {e}")
            time.sleep(5)
            continue
            
    my_bar.empty()
    
    if vector_store:
        try:
            vector_store.save_local(cartella_index)
            st.success("✅ Indice salvato su disco.")
        except Exception as e:
            st.error(f"Errore salvataggio: {e}")
        
    return vector_store, len(files), "✅ Indice Ricostruito e Salvato"

# --- CHIAMATA ALLA FUNZIONE ---
st.write("⏳ DEBUG: Sto per chiamare gestisci_indice_vettoriale()...")
VECTOR_STORE, NUM_FILES, STATUS_MSG = gestisci_indice_vettoriale()
st.success("🚀 DEBUG: Indice caricato! Caricamento interfaccia...")

# =========================================================
# 4. SIDEBAR & APP
# =========================================================
with st.sidebar:
    st.header("📋 Anamnesi")
    with st.expander("Dati Paziente", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            sesso = st.selectbox("Sesso", ["Uomo", "Donna"])
            eta = st.number_input("Età", 18, 100, 30)
        with col2:
            peso = st.number_input("Peso", 40, 150, 70)
            altezza = st.number_input("Altezza", 140, 220, 170)
        regime = st.selectbox("Regime", ["Onnivora", "Vegetariana", "Vegana", "Chetogenica"])
        cibi_no = st.text_input("Esclusioni", placeholder="Es. Cipolla")
    
    with st.expander("Clinica"):
        metaboliche = st.multiselect("Metaboliche", ["Diabete T2", "Insulino-resistenza", "Dislipidemia"])
        gastro = st.multiselect("Gastro", ["IBS", "Reflusso", "Celiachia"])
        obiettivo = st.selectbox("Obiettivo", ["Dimagrimento", "Mantenimento", "Gestione Glicemica"])

    st.divider()
    
    # ADMIN TOOLS
    with st.expander("🛠️ Admin Tools", expanded=False):
        st.info(f"Stato: {STATUS_MSG}")
        if st.button("🔄 Reset Indice"):
            try:
                if os.path.exists("faiss_index_store"): shutil.rmtree("faiss_index_store")
                st.cache_resource.clear()
                st.rerun()
            except: pass

st.title("🩺 Nutri-AI: Clinical Assistant v7.1 (DEBUG MODE)")

st.subheader("🩸 Esami Ematici")
col_sx, col_dx = st.columns([2, 1])
with col_sx:
    esami_df = st.data_editor(pd.DataFrame([{"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL"}]), num_rows="dynamic", use_container_width=True)
with col_dx:
    if VECTOR_STORE: st.success(f"📚 {NUM_FILES} Docs")
    else: st.error("❌ Errore Fonti")

PROFILO = f"Paziente: {sesso}, {eta}anni, {peso}kg. Dieta: {regime}. No: {cibi_no}. Patologie: {metaboliche}, {gastro}. Obiettivo: {obiettivo}.\nEsami:\n{esami_df.to_string(index=False)}"

if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Scrivi qui la tua richiesta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisi..."):
            try:
                q_aug = f"{prompt} {', '.join(metaboliche)} {', '.join(gastro)} {obiettivo}"
                docs = VECTOR_STORE.similarity_search(q_aug, k=5) if VECTOR_STORE else []
                context = "\n".join([f"FONTE {d.metadata.get('source')}: {d.page_content}" for d in docs]) or "Nessuna fonte."

                ISTRUZIONI = f"""
                RUOLO: Nutrizionista Clinico.
                FONTI: {context}
                PAZIENTE: {PROFILO}
                """
                
                resp = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(system_instruction=ISTRUZIONI, temperature=0.3)
                )
                
                st.markdown(resp.text)
                st.session_state.messages.append({"role": "assistant", "content": resp.text})
            except Exception as e: st.error(f"Errore: {e}")
