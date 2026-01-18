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
# 1. CONFIGURAZIONE & SICUREZZA
# =========================================================
st.set_page_config(page_title="Nutri-AI Clinical", page_icon="🩺", layout="wide")
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

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

try:
    LA_MIA_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("ERRORE: Manca API KEY.")
    st.stop()

client = genai.Client(api_key=LA_MIA_API_KEY)

# =========================================================
# 2. MOTORE PDF (MEDICAL DESIGN)
# =========================================================
def crea_pdf_html(dati_paziente, testo_ai):
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    html_paziente = dati_paziente.replace("\n", "<br>")
    
    html_template = f"""
    <html><head><style>
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
    </style></head><body>
        <div class="header-bar"><h1>Piano Clinico Nutrizionale</h1><div class="subtitle">Generato con Nutri-AI Assistant</div></div>
        <div class="box-paziente"><strong>QUADRO CLINICO:</strong><br><br>{html_paziente}</div>
        {html_ai}
        <div id="footerContent" style="text-align:center; color:#999; font-size:9px;">Report generato il {pd.Timestamp.now().strftime('%d/%m/%Y')}</div>
    </body></html>
    """
    from io import BytesIO
    result_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=result_file)
    if pisa_status.err: return None
    return result_file.getvalue()

# =========================================================
# 3. MOTORE VETTORIALE (IBRIDO LOCALE/CLOUD)
# =========================================================
@st.cache_resource
def gestisci_indice_vettoriale():
    cartella_docs = "documenti"
    cartella_index = "faiss_index_store" 
    
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=LA_MIA_API_KEY)
    
    # --- STRATEGIA A: CARICAMENTO DA DISCO (Fast Boot) ---
    # Se hai caricato la cartella 'faiss_index_store' su GitHub, entra qui.
    if os.path.exists(cartella_index):
        try:
            # allow_dangerous_deserialization=True serve per fidarsi dei propri file locali
            vector_store = FAISS.load_local(cartella_index, embeddings, allow_dangerous_deserialization=True)
            files_presenti = len(os.listdir(cartella_docs)) if os.path.exists(cartella_docs) else 0
            return vector_store, files_presenti, "⚡ Memoria Persistente (GitHub/Locale)"
        except Exception:
            pass # Se fallisce, passa alla ricostruzione
    
    # --- STRATEGIA B: RICOSTRUZIONE (Slow Boot) ---
    if not os.path.exists(cartella_docs): return None, 0, "⚠️ Cartella Documenti Assente"
    files = [f for f in os.listdir(cartella_docs) if f.endswith('.pdf')]
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
    
    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    # Batching per evitare Error 429
    vector_store = None
    batch_size = 10
    total_chunks = len(splits)
    my_bar = st.progress(0, text="Indicizzazione in corso (Attendere)...")

    for i in range(0, total_chunks, batch_size):
        batch = splits[i : i + batch_size]
        try:
            if vector_store is None:
                vector_store = FAISS.from_documents(batch, embeddings)
            else:
                vector_store.add_documents(batch)
            time.sleep(1.5) # Pausa anti-blocco
            my_bar.progress(min(1.0, (i+batch_size)/total_chunks))
        except Exception:
            time.sleep(5)
            continue
            
    my_bar.empty()
    
    # Salva su disco (per la sessione corrente)
    if vector_store:
        vector_store.save_local(cartella_index)
        
    return vector_store, len(files), "✅ Indice Ricostruito e Salvato"

VECTOR_STORE, NUM_FILES, STATUS_MSG = gestisci_indice_vettoriale()

# =========================================================
# 4. SIDEBAR & ADMIN TOOLS
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
    
    # --- ADMIN TOOLS POTENZIATI ---
    with st.expander("🛠️ Admin & Debug Tools", expanded=False):
        st.info(f"Stato Memoria: {STATUS_MSG}")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Ricostruisci", use_container_width=True):
                try:
                    if os.path.exists("faiss_index_store"): shutil.rmtree("faiss_index_store")
                    st.cache_resource.clear()
                    st.rerun()
                except: pass
        with c2:
            if os.path.exists("faiss_index_store"):
                shutil.make_archive("indice_backup", 'zip', "faiss_index_store")
                with open("indice_backup.zip", "rb") as fp:
                    st.download_button("💾 Download ZIP", data=fp, file_name="faiss_index_store.zip", mime="application/zip", use_container_width=True)
        
        st.divider()
       st.divider()
        st.write("🕵️‍♂️ **File Inspector (Mirino Laser)**")
        
        if os.path.exists("documenti"):
            files_in_folder = [f for f in os.listdir("documenti") if f.endswith('.pdf')]
            sel_file = st.selectbox("Seleziona File:", files_in_folder)
            
            # Leggiamo il file per sapere quante pagine ha
            try:
                path = os.path.join("documenti", sel_file)
                reader = PdfReader(path)
                num_pages = len(reader.pages)
                
                st.info(f"Il file ha {num_pages} pagine.")
                
                # SELETTORE DI PAGINA
                page_num = st.number_input("Quale pagina vuoi analizzare?", min_value=1, max_value=num_pages, value=1)
                
                if st.button(f"🔍 Analizza Pagina {page_num}"):
                    # Estrae solo la pagina richiesta (ricorda: informatica parte da 0)
                    page_content = reader.pages[page_num - 1].extract_text()
                    
                    st.markdown(f"**Contenuto Grezzo Pagina {page_num}:**")
                    if not page_content:
                        st.error("PAGINA BIANCA O IMMAGINE")
                    else:
                        st.code(page_content, language="markdown")
                        st.caption("⚠️ Controlla qui sopra: se è una tabella, le colonne sono allineate o i numeri sono mischiati?")
            
            except Exception as e:
                st.error(f"Errore lettura file: {e}")
                
        st.divider()
        st.write("🧠 **Vector Search Debug**")
        q_test = st.text_input("Cerca concetto (es. 'Ferro')")
        if q_test and VECTOR_STORE:
            res = VECTOR_STORE.similarity_search(q_test, k=2)
            for i, d in enumerate(res):
                st.caption(f"Fonte: {d.metadata.get('source')}")
                st.code(d.page_content, language="markdown")

# =========================================================
# 5. APP PRINCIPALE
# =========================================================
st.title("🩺 Nutri-AI: Clinical Assistant v7.0")

st.subheader("🩸 Esami Ematici")
col_sx, col_dx = st.columns([2, 1])
with col_sx:
    esami_df = st.data_editor(pd.DataFrame([{"Esame": "Glucosio", "Valore": 90, "Unità": "mg/dL"}, {"Esame": "Colesterolo", "Valore": 180, "Unità": "mg/dL"}]), num_rows="dynamic", use_container_width=True)
with col_dx:
    if VECTOR_STORE: st.success(f"📚 {NUM_FILES} Documenti Attivi")
    else: st.error("❌ Nessuna fonte caricata")

PROFILO = f"Paziente: {sesso}, {eta}anni, {peso}kg. Dieta: {regime}. No: {cibi_no}. Patologie: {metaboliche}, {gastro}. Obiettivo: {obiettivo}.\nEsami:\n{esami_df.to_string(index=False)}"

if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Scrivi qui la tua richiesta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultazione biblioteca scientifica..."):
            try:
                # Retrieval Arricchito
                q_aug = f"{prompt} {', '.join(metaboliche)} {', '.join(gastro)} {obiettivo}"
                docs = VECTOR_STORE.similarity_search(q_aug, k=5) if VECTOR_STORE else []
                context = "\n".join([f"FONTE {d.metadata.get('source')}: {d.page_content}" for d in docs]) or "Nessuna fonte specifica trovata."

                ISTRUZIONI = f"""
                RUOLO: Nutrizionista Clinico (Evidence-Based).
                
                BIBLIOTECA (Usa SOLO queste fonti):
                {context}
                
                PAZIENTE:
                {PROFILO}
                
                MANDATORY RULES:
                1. CHECK SICUREZZA: Panic Values (es. Potassio <2.5) -> PS. Celiachia -> No Glutine.
                2. CLINICA: Diabete (Low GI, <15% zuccheri), IBS (Low-FODMAP).
                3. FORMAT: Usa tabelle Markdown (| A | B |) per le diete.
                """
                
                resp = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(system_instruction=ISTRUZIONI, temperature=0.3)
                )
                
                st.markdown(resp.text)
                st.session_state.messages.append({"role": "assistant", "content": resp.text})
                
                pdf = crea_pdf_html(PROFILO, resp.text)
                if pdf: st.download_button("🖨️ Scarica PDF", data=pdf, file_name="Piano.pdf", mime="application/pdf")
            
            except Exception as e: st.error(f"Errore: {e}")
