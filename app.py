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
# 2. MOTORE PDF (FIXED STYLE)
# =========================================================
def crea_pdf_html(dati_paziente, testo_ai):
    html_ai = markdown.markdown(testo_ai, extensions=['tables'])
    html_paziente = dati_paziente.replace("\n", "<br>")
    
    # 1. Definiamo lo stile CSS in una stringa SEMPLICE (senza f davanti)
    # Questo evita l'errore SyntaxError con le parentesi {}
    css_style = """
        @page {
            size: A4;
            margin: 1.5cm;
            @frame footer_frame {
                -pdf-frame-content: footerContent;
                bottom: 0cm;
                margin-left: 1.5cm;
                margin-right: 1.5cm;
                height: 1cm;
            }
        }
        body { font-family: Helvetica, sans-serif; font-size: 11px; color: #333; line-height: 1.4; }
        .header-bar { background-color: #008080; color: white; padding: 15px; text-align: center; border-radius: 5px; margin-bottom: 20px; }
        h1 { margin:0; font-size: 20px; text-transform: uppercase; }
        .subtitle { font-size: 10px; font-weight: normal; margin-top: 5px; }
        h2 { color: #008080; font-size: 14px; border-bottom: 2px solid #008080; padding-bottom: 5px; margin-top: 25px; }
        .box-paziente { background-color: #f0f7f7; border-left: 5px solid #008080; padding: 15px; margin-bottom: 20px; font-size: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px; font-size: 10px; }
        th { background-color: #008080; color: white; font-weight: bold; padding: 8px; text-align: left; border: 1px solid #006666; }
        td { border: 1px solid #ddd; padding: 6px; color: #444; }
        tr:nth-child(even) { background-color: #f9f9f9; }
    """

    # 2. Creiamo l'HTML iniettando il CSS e i dati
    html_template = f"""
    <html>
    <head>
        <style>
            {css_style}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <h1>Piano Clinico Nutrizionale</h1>
            <div class="subtitle">Generato con Nutri-AI Assistant</div>
        </div>
        
        <div class="box-paziente">
            <strong>QUADRO CLINICO:</strong><br><br>
            {html_paziente}
        </div>
        
        {html_ai}
        
        <div id="footerContent" style="text-align:center; color:#999; font-size:9px;">
            Report generato il {pd.Timestamp.now().strftime('%d/%m/%Y')}
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
# 3. MOTORE VETTORIALE (IBRIDO LOCALE/CLOUD)
# =========================================================
@st.cache_resource
def gestisci_indice_vettoriale():
    cartella_docs = "documenti"
    cartella_index = "faiss_index_store" 
    
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=LA_MIA_API_KEY)
    
    # --- STRATEGIA A: CARICAMENTO DA DISCO (Fast Boot) ---
    if os.path.exists(cartella_index):
