import streamlit as st
from google import genai
import anthropic
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io
import difflib
import time
import textwrap 
import re 
import random
import gc # IMPORTANTE: Recolector de basura para limpiar la memoria RAM
from datetime import datetime
from core.supabase_client import get_supabase_client
from core.prompts_ia import PROMPT_AUDITORIA_REMITOS
from modulos import clientes as modulo_clientes
from modulos import proveedores as modulo_proveedores
from modulos import verificacion_bcra as modulo_bcra
from modulos import resumen as modulo_resumen
import requests 

# Importamos la nueva botonera PRO
try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.error("⚠️ Falta instalar el menú moderno. Agregá `streamlit-option-menu` a tu archivo requirements.txt en GitHub.")
    st.stop()

# Herramientas de diseño para el Excel
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# 1. IDENTIDAD, CONEXIÓN Y SEGURIDAD
# ==========================================
COLOR_ROJO = "#C8102E"
COLOR_AMARILLO_ALERTA = "#FFE082" 
COLOR_GRIS_BC = "#3A3A3A" 

# Llamamos a las llaves desde la bóveda secreta de Streamlit
supabase = get_supabase_client()

NOMBRES_SUCURSALES = {1: "RECONQUISTA", 2: "AVELLANEDA", 3: "FLORENCIA", 4: "RECREO"}

st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""
    <style>
        [data-testid="stSidebarNav"] {{display: none !important;}}
        .stApp {{ background-color: #f4f6f9 !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; font-weight: 700; }}
        
        .stButton>button {{ 
            background-color: {COLOR_ROJO}; color: white; border-radius: 8px; 
            font-weight: 600; height: 2.8em; border: none; width: 100%; transition: all 0.3s;
        }}
        .stButton>button:hover {{ background-color: #900b20; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        
        [data-testid="stHeader"] {{ background-color: {COLOR_GRIS_BC} !important; }}
        [data-testid="stSidebar"] {{ background-color: {COLOR_GRIS_BC} !important; border-right: none; }}
        
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div {{ color: #ffffff !important; }}
        
        div[data-testid="stMetricValue"] {{ color: {COLOR_ROJO} !important; }}
        
        .tarjeta-pro {{
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px;
        }}
    </style>
""", unsafe_allow_html=True)

# Cliente de Gemini: todavía lo usan Verificación BCRA y Facturas de Proveedores.
cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Cliente de Claude: usado por el Generador de Resumen (migrado en agosto 2026).
# IMPORTANTE: hay que cargar el secret ANTHROPIC_API_KEY en esta app de Streamlit
# Cloud puntual ("BC Combustibles - Gestión Pro") — cada app tiene su propia
# bóveda de secrets, cargarlo acá no lo carga automáticamente en las otras.
cliente_claude = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

URL_LOGO_OFICIAL = "https://bjhykcdhafoqpfkpngvw.supabase.co/storage/v1/object/public/remitos/Logo%20nuevo.png"

# ==========================================
# 2. SISTEMA DE LOGIN Y AUTENTICACIÓN
# ==========================================
if 'usuario_autenticado' not in st.session_state:
    st.session_state.usuario_autenticado = None

def mostrar_login():
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(f"""
            <div class="tarjeta-pro" style="text-align:center;">
                <img src="{URL_LOGO_OFICIAL}" width="140" style="border-radius:10px; margin-bottom: 20px;">
                <h2 style='text-align:center; margin-bottom: 30px;'>Acceso Seguro</h2>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            legajo = st.text_input("Número de Legajo", placeholder="Ej: 105")
            pin = st.text_input("PIN de Acceso", type="password", placeholder="Tu clave")
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("INGRESAR AL SISTEMA"):
                try:
                    res = supabase.table("empleados").select("*").eq("legajo", legajo).eq("pin", pin).execute()
                    if res.data:
                        st.session_state.usuario_autenticado = res.data[0]
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")

if st.session_state.usuario_autenticado is None:
    mostrar_login()
    st.stop()

# --- USUARIO LOGUEADO ---
user = st.session_state.usuario_autenticado
usuario_app = user['nombre']

# 1. ELIMINAR EL "FANTASMA" DE LA BARRA LATERAL POR COMPLETO
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# 2. CABECERA SUPERIOR ALINEADA AL CENTRO
col_logo, col_esp, col_perfil, col_salir = st.columns([1, 4, 2.5, 1], vertical_alignment="center")

with col_logo:
    st.image(URL_LOGO_OFICIAL, width=120)

with col_perfil:
    # Usamos etiquetas <font> que Streamlit no puede ignorar para garantizar el texto blanco
    st.markdown(f"""
        <div style="background-color: #3A3A3A; padding: 10px 15px; border-radius: 8px; border-left: 5px solid {COLOR_ROJO}; line-height: 1.5;">
            <font color="white" size="2">Operador: <b>{usuario_app}</b></font><br>
            <font color="white" size="2">📍 {NOMBRES_SUCURSALES.get(user['sucursal_id'], 'BC')}</font>
        </div>
    """, unsafe_allow_html=True)

with col_salir:
    if st.button("**🚪 Salir**", use_container_width=True):
        st.session_state.usuario_autenticado = None
        st.rerun()

# 3. MENÚ HORIZONTAL AJUSTADO (GROSOR NORMAL)
opcion = option_menu(
    menu_title=None, 
    options=["Generador de Resumen", "Facturas de Proveedores", "Verificación BCRA", "Gestión de Clientes", "Laboratorio IA"], 
    icons=["file-earmark-spreadsheet", "receipt", "shield-check", "people", "robot"], 
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "10px!important", "background-color": COLOR_GRIS_BC, "border-radius": "8px", "margin-top": "15px"},
        "icon": {"color": "#FFFFFF", "font-size": "15px"}, 
        "nav-link": {"color": "#FFFFFF", "font-size": "13px", "text-align": "center", "margin":"0px", "--hover-color": "#4A4A4A"},
        "nav-link-selected": {"background-color": COLOR_ROJO, "color": "white", "font-weight": "normal"}, 
    }
)
st.markdown("<br>", unsafe_allow_html=True)

if 'resumen_para_cliente' not in st.session_state: st.session_state.resumen_para_cliente = []
if 'agregados_excel' not in st.session_state: st.session_state.agregados_excel = []

def convertir_a_numero(valor):
    v = str(valor).strip()
    if v.isdigit(): return int(v)
    return v

# ==========================================
# 3. MÓDULO: FACTURAS DE PROVEEDORES
# ==========================================
if opcion == "Facturas de Proveedores":
    modulo_proveedores.mostrar(cliente_ia)

# ==========================================
# 4. MÓDULO: GENERADOR DE RESUMEN A CLIENTES
# ==========================================
elif opcion == "Generador de Resumen":
    modulo_resumen.mostrar(supabase, cliente_claude, user, NOMBRES_SUCURSALES, COLOR_ROJO)

# ==========================================
# 5. MÓDULO: VERIFICACIÓN BCRA Y CHEQUES (IA AVANZADA)
# ==========================================
elif opcion == "Verificación BCRA":
    modulo_bcra.mostrar(supabase, cliente_ia)

# ==========================================
# 6. MÓDULO: GESTIÓN DE CLIENTES (ADMINISTRACIÓN)
# ==========================================
elif opcion == "Gestión de Clientes":
    modulo_clientes.mostrar(supabase, NOMBRES_SUCURSALES)

# ==========================================
# 7. MÓDULO: LABORATORIO IA (COBRANZAS)
# ==========================================
elif opcion == "Laboratorio IA":
    # Leemos y ejecutamos el archivo directamente
    with open("bot.py", encoding="utf-8") as f:
        exec(f.read())
        st.markdown('</div>', unsafe_allow_html=True)
