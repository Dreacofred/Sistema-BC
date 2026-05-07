# Archivo: pages/Cheques.py
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import pandas as pd
import json
import os
import io
import time
import textwrap
from datetime import datetime
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
# 2. FUNCIONES DE APOYO (RECORTE E IA)
# ==========================================
def segmentar_cheques(img):
    """
    Detecta la orientación y divide la imagen si es necesario para 
    evitar que la IA mezcle datos de cheques diferentes.
    """
    width, height = img.size
    # Si la imagen es notablemente más alta que ancha, asumimos cheques apilados
    if height > width * 1.2:
        num_segmentos = 4 if height > width * 2.5 else 2
        segmentos = []
        alto_segmento = height // num_segmentos
        for i in range(num_segmentos):
            caja = (0, i * alto_segmento, width, (i + 1) * alto_segmento)
            segmentos.append(img.crop(caja))
        return segmentos
    return [img]

# ==========================================
# 3. CONEXIÓN A LA IA Y MENÚ LATERAL
# ==========================================
cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png", "../Logo.jpeg", "../Logo.jpg"] if os.path.exists(v)), None)
if ruta_logo: st.sidebar.image(ruta_logo, use_container_width=True)

st.sidebar.subheader("👤 Identificación")

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
# 4. MÓDULO PRINCIPAL DE CHEQUES
# ==========================================
st.title(f"💳 Módulo de Cheques - {st.session_state.usuario_actual}")

if 'cheques_procesados' not in st.session_state:
    st.session_state.cheques_procesados = []

if 'reset_key' not in st.session_state:
    st.session_state.reset_key = 0

col_ingreso, col_cinta = st.columns([1, 2])

with col_ingreso:
    st.subheader("📸 Ingreso de Cheque(s)")
    st.caption("CONSEJO: Acomodá hasta 4 cheques en la foto. Procurá buena luz y enfoque.")
    
    imagen_capturada = st.camera_input("Escanear con cámara", key=f"cam_{st.session_state.reset_key}")
    imagenes_subidas = st.file_uploader("O subir foto(s)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"up_{st.session_state.reset_key}")
    
    imagenes_a_procesar = []
    if imagen_capturada:
        imagenes_a_procesar.append(imagen_capturada)
    if imagenes_subidas:
        imagenes_a_procesar.extend(imagenes_subidas)

    if len(imagenes_a_procesar) > 0:
        st.write(f"**{len(imagenes_a_procesar)} imagen(es) lista(s)** para analizar.")
        st.image(imagenes_a_procesar, width=150)
        
        if st.button("Procesar Imagen(es) con IA", use_container_width=True):
            with st.spinner(f"Analizando con precisión mejorada..."):
                cheques_totales_nuevos = 0
                errores = 0
                
                prompt = textwrap.dedent("""
                Rol: Especialista en Visión Artificial y OCR Financiero Argentino.
                
                REGLA DE ORO DE EXTRACCIÓN:
                - EMISOR/CUIT: El nombre del titular (Emisor) está siempre físicamente cerca del CUIT. NO confundir con el beneficiario (el nombre que sigue a 'Páguese a').
                - BANDA MAGNÉTICA: Extrae el 1er grupo de 3 dígitos (Banco_Cod) y el 3er grupo de 4 dígitos (Plaza). Ignora el resto.
                - IMPORTANTE: Si la imagen es un fragmento de un cheque, extrae solo lo que veas con total seguridad.
                
                Formato de salida:
                1. <Borrador_Analisis>: Detalle de lo observado.
                2. JSON: Un array con los objetos:
                [{"Banco_Cod": "3 dígitos", "Plaza": "4 dígitos", "Banco_Nombre": "Nombre", "Numero_Cheque": "Nro", "Importe": entero, "Fecha_Emision": "DD/MM/AAAA", "Fecha_Pago": "DD/MM/AAAA", "Emisor": "Razón Social", "CUIT": "XX-XXXXXXXX-X"}]
                """)
                
                for i, archivo_imagen in enumerate(imagenes_a_procesar):
                    try:
                        archivo_imagen.seek(0)
                        img_full = Image.open(archivo_imagen).convert('RGB')
                        
                        # REDUCCIÓN DE ALUCINACIÓN: Segmentamos la foto en partes
                        fragmentos = segmentar_cheques(img_full)
                        
                        for idx, frag in enumerate(fragmentos):
                            # Preparamos el fragmento para la IA
                            max_dim = 2500
                            if max(frag.size) > max_dim:
                                frag.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                            
                            exito_frag = False
                            for intento in range(2): # Reintentos por fragmento
                                if exito_frag: break
                                try:
                                    respuesta = cliente_ia.models.generate_content(
                                        model='gemini-2.0-flash',
                                        contents=[prompt, frag],
                                        config=types.GenerateContentConfig(temperature=0.0)
                                    )
                                    
                                    raw_text = respuesta.text.strip()
                                    # Extraer JSON de la respuesta
                                    if "[" in raw_text:
                                        json_str = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                                        datos = json.loads(json_str)
                                        
                                        for cheque in datos:
                                            # Validamos que no sea un objeto vacío o alucinación sin importe
                                            if cheque.get("Importe", 0) > 0:
                                                cheque["Operador"] = st.session_state.usuario_actual
                                                st.session_state.cheques_procesados.append(cheque)
                                                cheques_totales_nuevos += 1
                                        exito_frag = True
                                except Exception:
                                    time.sleep(1)
                                    continue
                                    
                    except Exception as e:
                        errores += 1
                        st.error(f"Error en imagen {i+1}: {str(e)}")
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Se procesaron {cheques_totales_nuevos} cheque(s) con éxito!")
                    st.session_state.reset_key += 1
                    time.sleep(1)
                    st.rerun()

with col_cinta:
    st.subheader("⚙️ Cinta Transportadora")
    
    if len(st.session_state.cheques_procesados) > 0:
        df_cheques = pd.DataFrame(st.session_state.cheques_procesados)
        
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
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_editado.to_excel(writer, index=False, sheet_name='Cheques_Procesados')
            ws = writer.sheets['Cheques_Procesados']
            for i, col in enumerate(df_editado.columns):
                ws.column_dimensions[get_column_letter(i + 1)].width = 20

        col_ex1, col_ex2 = st.columns(2)
        
        with col_ex1:
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
