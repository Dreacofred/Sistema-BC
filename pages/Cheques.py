# Archivo: pages/Cheques.py
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
# Busca el logo en la carpeta principal o en la misma carpeta
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

# Inicializamos la "cinta transportadora" en la memoria de la sesión
if 'cheques_procesados' not in st.session_state:
    st.session_state.cheques_procesados = []

# Dividimos la pantalla: Izquierda para carga, Derecha para la cinta transportadora
col_ingreso, col_cinta = st.columns([1, 2])

with col_ingreso:
    st.subheader("📸 Ingreso de Cheque")
    # Permitimos usar la cámara de la compu/celular o subir un archivo
    imagen_capturada = st.camera_input("Escanear con cámara")
    imagen_subida = st.file_uploader("O subir foto del cheque", type=['jpg', 'jpeg', 'png'])
    
    imagen_actual = imagen_capturada if imagen_capturada else imagen_subida

    if imagen_actual is not None:
        img = Image.open(imagen_actual)
        st.image(img, caption="Vista previa del cheque", use_container_width=True)
        
        if st.button("Procesar Cheque con IA", use_container_width=True):
            with st.spinner("Analizando imagen..."):
                try:
                    # Prompt estricto para forzar a Gemini a devolver solo el JSON
                    prompt = """
                    Sos un asistente administrativo experto. Analizá la imagen de este cheque argentino y extraé los datos.
                    Devolvé ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta (sin formato markdown ni texto adicional):
                    {
                        "Banco": "Nombre del banco",
                        "Numero_Cheque": "Número del cheque (solo números)",
                        "Importe": 0.00,
                        "Fecha_Cobro": "DD/MM/AAAA",
                        "Emisor": "Nombre de quien firma o razón social",
                        "CUIT": "Número de CUIT si figura (sino vacío)"
                    }
                    """
                    
                    respuesta = cliente_ia.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[prompt, img]
                    )
                    
                    # Limpiamos la respuesta por si Gemini agrega las comillas de markdown (```json ... ```)
                    texto_json = respuesta.text.strip()
                    if texto_json.startswith("```json"):
                        texto_json = texto_json[7:-3]
                    elif texto_json.startswith("```"):
                        texto_json = texto_json[3:-3]
                        
                    datos_cheque = json.loads(texto_json.strip())
                    
                    # Agregamos el operador que lo escaneó para tener trazabilidad
                    datos_cheque["Operador"] = st.session_state.usuario_actual
                    
                    st.session_state.cheques_procesados.append(datos_cheque)
                    st.success("¡Cheque procesado y agregado a la cinta!")
                    st.rerun() # Recargamos para limpiar la vista y actualizar la tabla
                    
                except Exception as e:
                    st.error(f"Hubo un error al leer el cheque. Probá con otra foto más nítida. Detalle: {e}")

with col_cinta:
    st.subheader("⚙️ Cinta Transportadora (Cheques a procesar)")
    
    if len(st.session_state.cheques_procesados) > 0:
        # Convertimos la lista de la sesión en un DataFrame
        df_cheques = pd.DataFrame(st.session_state.cheques_procesados)
        
        # Mostramos un editor de datos. Esto es clave: permite corregir a mano si la IA leyó mal un número o una letra.
        df_editado = st.data_editor(
            df_cheques, 
            num_rows="dynamic", # Permite borrar filas si se escaneó uno doble
            use_container_width=True,
            hide_index=True
        )
        
        # Actualizamos la memoria con los datos editados
        st.session_state.cheques_procesados = df_editado.to_dict('records')
        
        st.markdown("---")
        # Totalizador rápido para control de caja
        total_cheques = pd.to_numeric(df_editado['Importe'], errors='coerce').sum()
        st.info(f"**Total en cheques listos para guardar:** ${total_cheques:,.2f}")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Guardar Lote", type="primary", use_container_width=True):
                # ACÁ VA LA LÓGICA DE GUARDADO (Ej: Google Sheets, CSV, Base de datos)
                st.success("Lote guardado correctamente. (Falta conectar destino)")
                # Limpiamos la cinta después de guardar
                st.session_state.cheques_procesados = []
                st.rerun()
                
        with col_btn2:
            if st.button("🗑️ Vaciar Cinta", use_container_width=True):
                st.session_state.cheques_procesados = []
                st.rerun()
    else:
        st.info("La cinta está vacía. Escaneá un cheque para empezar.")
