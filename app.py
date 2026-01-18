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
        .subtitle {{ font-size: 1
