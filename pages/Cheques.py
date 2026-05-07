# Archivo: pages/Cheques.py
# INICIO DEL CÓDIGO
import streamlit as st
from google import genai
from PIL import Image
import pandas as pd
import json
import os
import io
from datetime import datetime

# Herramientas para el diseño del Excel
from openpyxl.utils import get_column_letter

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

# --- MEMORIA COMPARTIDA (Se sincroniza con lector.py) ---
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = ""

usuario_app = st.sidebar.text_input(
    "Tu nombre para operar:", 
    value=st.session_state.usuario_actual, 
    placeholder="Ej: Nancy, Diego o Tomas"
)

if usuario_app != st.session_state.usuario_actual:
    st.session_state.usuario_actual = usuario_app

if not st.session_state.usuario_actual.strip():
    st.title("💳 Módulo de Lectura de Cheques")
    st.markdown("""<div class="alerta-ingreso">⚠️ ACCESO RESTRINGIDO<br>Ingresá tu nombre en el panel lateral para habilitar el sistema.</div>""", unsafe_allow_html=True)
    st.stop()

st.sidebar.info(f"Operador activo: {st.session_state.usuario_actual}")

# ==========================================
# 3. MÓDULO PRINCIPAL DE CHEQUES
# ==========================================
st.title(f"💳 Módulo de Cheques - {st.session_state.usuario_actual}")

if 'cheques_procesados' not in st.session_state:
    st.session_state.cheques_procesados = []

col_ingreso, col_cinta = st.columns([1, 2])

with col_ingreso:
    st.subheader("📸 Ingreso de Cheque(s)")
    st.caption("Podés procesar de 1 a 4 cheques por foto.")
    imagen_capturada = st.camera_input("Escanear con cámara")
    imagen_subida = st.file_uploader("O subir foto", type=['jpg', 'jpeg', 'png'])
    
    imagen_actual = imagen_capturada if imagen_capturada else imagen_subida

    if imagen_actual is not None:
        img = Image.open(imagen_actual)
        st.image(img, caption="Vista previa de los cheques", use_container_width=True)
        
        if st.button("Procesar Imagen con IA", use_container_width=True):
            with st.spinner("Analizando imagen al detalle..."):
                try:
                    prompt = """
                    Sos un experto bancario procesando cheques físicos argentinos. En la imagen puede haber de 1 a 4 cheques.
                    Analizá la imagen detalladamente y extraé los datos de TODOS los cheques que encuentres.
                    
                    REGLAS DE EXTRACCIÓN PARA CADA CHEQUE:
                    1. EMISOR: Es la razón social impresa (ej: "DANKO MADERAS SRL"). Está a la izquierda del cheque. IGNORA LOS SELLOS DE GOMA SOBRE LAS FIRMAS.
                    2. CUIT: El número de CUIT del emisor impreso a la izquierda.
                    3. BANDA NUMÉRICA: 
                       - El CÓDIGO DE BANCO es el primer número (ej: 386).
                       - La PLAZA es el tercer número (ej: 3200). 
                       - IGNORA la sucursal (el número del medio).
                    4. FECHAS: 
                       - Fecha_Emision: La fecha en la que se emitió/hizo el cheque.
                       - Fecha_Pago: La fecha de cobro ("Páguese el..."). ¡ATENCIÓN! Si el cheque es un "cheque común" y NO tiene la leyenda "Páguese el..." con una fecha diferida, entonces la Fecha_Pago debe ser EXACTAMENTE LA MISMA que la Fecha_Emision.
                    5. IMPORTE: Devolvé el número entero (ej: 500000). El punto en el cheque es separador de miles.
                    
                    Devolvé ÚNICAMENTE un ARRAY de objetos JSON con esta estructura exacta:
                    [
                        {
                            "Banco_Cod": "3 dígitos",
                            "Plaza": "4 dígitos",
                            "Banco_Nombre": "Nombre",
                            "Numero_Cheque": "Número",
                            "Importe": 0.00,
                            "Fecha_Emision": "DD/MM/AAAA",
                            "Fecha_Pago": "DD/MM/AAAA",
                            "Emisor": "Nombre impreso",
                            "CUIT": "Número CUIT"
                        }
                    ]
                    """
                    
                    respuesta = cliente_ia.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[prompt, img]
                    )
                    
                    # Limpieza segura para evitar romper el visor de código
                    marcador = chr(96) * 3
                    texto_json = respuesta.text.strip()
                    if texto_json.startswith(f"{marcador}json"): texto_json = texto_json[7:-3]
                    elif texto_json.startswith(marcador): texto_json = texto_json[3:-3]
                        
                    datos_extraidos = json.loads(texto_json.strip())
                    if isinstance(datos_extraidos, dict): datos_extraidos = [datos_extraidos]
                    
                    for cheque in datos_extraidos:
                        cheque["Operador"] = st.session_state.usuario_actual
                        st.session_state.cheques_procesados.append(cheque)
                        
                    st.success(f"¡Se procesaron {len(datos_extraidos)} cheque(s)!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error en lectura: {e}")

with col_cinta:
    st.subheader("⚙️ Cinta Transportadora")
    
    if len(st.session_state.cheques_procesados) > 0:
        df_cheques = pd.DataFrame(st.session_state.cheques_procesados)
        
        # Editor de datos fijo para correcciones
        df_editado = st.data_editor(
            df_cheques, 
            num_rows="fixed",
            use_container_width=True,
            hide_index=True
        )
        
        st.session_state.cheques_procesados = df_editado.to_dict('records')
        
        st.markdown("---")
        total_importe = pd.to_numeric(df_editado['Importe'], errors='coerce').sum()
        st.info(f"**Total acumulado en cinta:** ${total_importe:,.2f} ({len(df_cheques)} cheques)")
        
        # --- LÓGICA DE EXPORTACIÓN ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_editado.to_excel(writer, index=False, sheet_name='Cheques_Procesados')
            ws = writer.sheets['Cheques_Procesados']
            # Ajuste automático de columnas
            for i, col in enumerate(df_editado.columns):
                ws.column_dimensions[get_column_letter(i + 1)].width = 20

        col_ex1, col_ex2 = st.columns(2)
        
        with col_ex1:
            # Al descargar, se limpia la cinta automáticamente
            if st.download_button(
                label="📥 Descargar Excel y Reiniciar",
                data=buffer.getvalue(),
                file_name=f"Lote_Cheques_{datetime.now().strftime('%d-%m-%Y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            ):
                st.session_state.cheques_procesados = []
                st.rerun()
                
        with col_ex2:
            if st.button("🗑️ Vaciar sin descargar", use_container_width=True):
                st.session_state.cheques_procesados = []
                st.rerun()
    else:
        st.info("No hay cheques en la cinta.")
# ### FIN DEL CÓDIGO ###
