# Archivo: pages/Cheques.py
# INICIO DEL CÓDIGO
import streamlit as st
from google import genai
from PIL import Image
import pandas as pd
import json
import os
import io

# ==========================================
# 1. IDENTIDAD Y CONFIGURACIÓN VISUAL (ESTILO BC)
# ==========================================
COLOR_ROJO = "#C8102E"

st.set_page_config(page_title="BC Combustibles - Cheques", page_icon="💳", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 12px; font-weight: bold; height: 3em; border: none; width: 100%; }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
        [data-testid="stSidebar"] .stTextInput div[data-baseweb="input"] {{ border: 2px solid {COLOR_ROJO} !important; border-radius: 8px !important; background-color: #ffffff !important; }}
        .alerta-ingreso {{ padding: 20px; border-radius: 15px; background-color: #fff3f3; border-left: 5px solid {COLOR_ROJO}; color: #721c24; font-weight: bold; text-align: center; font-size: 1.2em; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONEXIÓN A LA IA Y MENÚ LATERAL
# ==========================================
cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png", "../Logo.jpeg", "../Logo.jpg"] if os.path.exists(v)), None)
if ruta_logo: st.sidebar.image(ruta_logo, use_container_width=True)

st.sidebar.subheader("👤 Identificación")
usuario_app = st.sidebar.text_input("Tu nombre para operar:", value="", placeholder="Ej: Nancy o Diego")

if not usuario_app.strip():
    st.title("💳 Módulo de Lectura de Cheques")
    st.markdown("""<div class="alerta-ingreso">⚠️ ACCESO RESTRINGIDO<br>Ingresá tu nombre en el panel lateral para habilitar el sistema.</div>""", unsafe_allow_html=True)
    st.stop()

if 'usuario_actual' not in st.session_state or st.session_state.usuario_actual != usuario_app:
    st.session_state.usuario_actual = usuario_app

st.sidebar.info(f"Operador activo: {st.session_state.usuario_actual}")

# ==========================================
# 3. MÓDULO PRINCIPAL DE CHEQUES
# ==========================================
st.title(f"💳 Módulo de Cheques - {st.session_state.usuario_actual}")

if 'cheques_procesados' not in st.session_state:
    st.session_state.cheques_procesados = []

col_ingreso, col_cinta = st.columns([1, 2])

with col_ingreso:
    st.subheader("📸 Ingreso de Cheque")
    imagen_capturada = st.camera_input("Escanear con cámara")
    imagen_subida = st.file_uploader("O subir foto del cheque", type=['jpg', 'jpeg', 'png'])
    
    imagen_actual = imagen_capturada if imagen_capturada else imagen_subida

    if imagen_actual is not None:
        img = Image.open(imagen_actual)
        st.image(img, caption="Vista previa del cheque", use_container_width=True)
        
        if st.button("Procesar Cheque con IA", use_container_width=True):
            with st.spinner("Analizando cheque al detalle..."):
                try:
                    prompt = """
                    Sos un experto bancario procesando cheques físicos argentinos. Analizá la imagen y extraé los datos con precisión quirúrgica.
                    
                    REGLAS DE EXTRACCIÓN:
                    1. EMISOR: Es la razón social impresa (ej: "DANKO MADERAS SRL"). Está a la izquierda del cheque. IGNORA LOS SELLOS DE GOMA SOBRE LAS FIRMAS.
                    2. CUIT: El número de CUIT del emisor impreso a la izquierda.
                    3. BANDA NUMÉRICA (ARRIBA O ABAJO): Buscá los números que identifican al banco y la plaza. 
                       - El CÓDIGO DE BANCO es el primer número de esa secuencia (ej: 386).
                       - La PLAZA es el tercer número de esa secuencia (ej: 3200). 
                       - IGNORA la sucursal (el número del medio).
                    4. FECHAS: 
                       - Fecha_Emision: La fecha en la que se hizo el cheque (ej: Concordia, 11 de Abril).
                       - Fecha_Pago: La fecha de cobro diferido ("Páguese el..."). ES LA MÁS IMPORTANTE.
                    5. IMPORTE (¡MUY IMPORTANTE!): En Argentina el punto (.) separa los miles. Si lees "500.000", significa quinientos mil. Debes devolver el número entero sin formato, es decir: 500000. Si tiene centavos, usa punto (ej: 500000.50). NUNCA confundas un separador de miles con un decimal.
                    
                    Devolvé ÚNICAMENTE un objeto JSON con esta estructura:
                    {
                        "Banco_Cod": "3 dígitos",
                        "Plaza": "4 dígitos (ej: 3200)",
                        "Banco_Nombre": "Nombre del banco",
                        "Numero_Cheque": "Número serie",
                        "Importe": 0.00,
                        "Fecha_Emision": "DD/MM/AAAA",
                        "Fecha_Pago": "DD/MM/AAAA",
                        "Emisor": "Razón social impresa",
                        "CUIT": "Número de CUIT"
                    }
                    """
                    
                    respuesta = cliente_ia.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[prompt, img]
                    )
                    
                    texto_json = respuesta.text.strip()
                    if texto_json.startswith("```json"):
                        texto_json = texto_json[7:-3]
                    elif texto_json.startswith("```"):
                        texto_json = texto_json[3:-3]
                        
                    datos_cheque = json.loads(texto_json.strip())
                    datos_cheque["Operador"] = st.session_state.usuario_actual
                    
                    st.session_state.cheques_procesados.append(datos_cheque)
                    st.success("¡Cheque agregado a la cinta!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error en lectura: {e}")

with col_cinta:
    st.subheader("⚙️ Cinta Transportadora")
    
    if len(st.session_state.cheques_procesados) > 0:
        df_cheques = pd.DataFrame(st.session_state.cheques_procesados)
        
        # Editor de datos SIN filas extra (num_rows="fixed")
        df_editado = st.data_editor(
            df_cheques, 
            num_rows="fixed",
            use_container_width=True,
            hide_index=True
        )
        
        st.session_state.cheques_procesados = df_editado.to_dict('records')
        
        st.markdown("---")
        total_cheques = pd.to_numeric(df_editado['Importe'], errors='coerce').sum()
        st.info(f"**Total acumulado en cinta:** ${total_cheques:,.2f}")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Guardar Lote", type="primary", use_container_width=True):
                st.success("Lote de cheques guardado.")
                st.session_state.cheques_procesados = []
                st.rerun()
                
        with col_btn2:
            if st.button("🗑️ Vaciar Cinta", use_container_width=True):
                st.session_state.cheques_procesados = []
                st.rerun()
    else:
        st.info("No hay cheques en la cinta.")
# ### FIN DEL CÓDIGO ###
