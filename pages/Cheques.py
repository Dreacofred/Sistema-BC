# Archivo: pages/Cheques.py
# INICIO DEL CÓDIGO
import streamlit as st
from google import genai
from PIL import Image
import pandas as pd
import json
import os
import io
import time
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

# --- MEMORIA COMPARTIDA ---
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

if 'reset_key' not in st.session_state:
    st.session_state.reset_key = 0

col_ingreso, col_cinta = st.columns([1, 2])

with col_ingreso:
    st.subheader("📸 Ingreso de Cheque(s)")
    st.caption("CONSEJO: Procesá hasta 4 cheques por foto.")
    
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
            with st.spinner(f"Optimizando y analizando {len(imagenes_a_procesar)} foto(s)..."):
                cheques_totales_nuevos = 0
                errores = 0
                
                # Prompt directo y sin vueltas para que no pierda tiempo pensando de más
                prompt = """
                Sos un experto bancario procesando cheques físicos argentinos. En la imagen hay entre 1 y 4 cheques apilados.
                Extraé los datos de TODOS los cheques que encuentres.
                
                REGLAS DE EXTRACCIÓN:
                1. EMISOR: Razón social impresa a la izquierda. Ignora sellos de goma.
                2. CUIT: Número de CUIT impreso.
                3. BANDA NUMÉRICA: Banco (1er número), Plaza (3er número).
                4. FECHAS: Fecha_Emision y Fecha_Pago (si es cheque común sin diferido, repetí la fecha de emisión).
                5. IMPORTE: Número entero (ej: 500000). El punto es separador de miles.
                
                Devolvé ÚNICAMENTE un ARRAY JSON PURO. Sin texto adicional. Formato estricto:
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
                
                for i, archivo_imagen in enumerate(imagenes_a_procesar):
                    exito = False
                    
                    for intento in range(3): # Max 3 intentos cortos
                        if exito:
                            break
                            
                        try:
                            archivo_imagen.seek(0)
                            img = Image.open(archivo_imagen)
                            
                            # --- LA SOLUCIÓN: OPTIMIZACIÓN DE IMAGEN ---
                            # Convertimos a formato compatible y achicamos la foto si es enorme.
                            # Esto evita el Timeout del servidor y los "falsos 503".
                            if img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')
                                
                            max_dim = 1600 # Resolución óptima para lectura rápida
                            if max(img.size) > max_dim:
                                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                            
                            # Llamada a la IA
                            respuesta = cliente_ia.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[prompt, img]
                            )
                            
                            raw_text = respuesta.text.strip()
                            marcador = chr(96) * 3
                            if raw_text.startswith(f"{marcador}json"): raw_text = raw_text[7:-3].strip()
                            elif raw_text.startswith(marcador): raw_text = raw_text[3:-3].strip()
                            
                            # Parseo del JSON
                            try:
                                datos_extraidos = json.loads(raw_text)
                            except:
                                start_idx = raw_text.find('[')
                                end_idx = raw_text.rfind(']') + 1
                                if start_idx != -1 and end_idx != 0:
                                    datos_extraidos = json.loads(raw_text[start_idx:end_idx])
                                else:
                                    start_idx_obj = raw_text.find('{')
                                    end_idx_obj = raw_text.rfind('}') + 1
                                    if start_idx_obj != -1 and end_idx_obj != 0:
                                        datos_extraidos = [json.loads(raw_text[start_idx_obj:end_idx_obj])]
                                    else:
                                        raise ValueError("La IA devolvió texto ilegible.")
                            
                            if isinstance(datos_extraidos, dict): 
                                datos_extraidos = [datos_extraidos]
                                
                            for cheque in datos_extraidos:
                                cheque["Operador"] = st.session_state.usuario_actual
                                st.session_state.cheques_procesados.append(cheque)
                                cheques_totales_nuevos += 1
                                
                            exito = True 
                                
                        except Exception as e:
                            error_str = str(e)
                            if "503" in error_str or "429" in error_str or "timeout" in error_str.lower():
                                if intento < 2:
                                    st.warning(f"⏳ Optimizando carga. Reintentando foto #{i+1} en breve...")
                                    time.sleep(3)
                                else:
                                    errores += 1
                                    st.error(f"❌ Falló la foto #{i+1}. La imagen resultó muy pesada de procesar.")
                            else:
                                errores += 1
                                st.error(f"❌ Falló la foto #{i+1} | DETALLE: {error_str}")
                                break 
                    
                    time.sleep(2) # Pausa cortita entre fotos
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Se procesaron {cheques_totales_nuevos} cheque(s) en total!")
                    if errores > 0:
                        st.warning(f"Ojo: Hubo {errores} foto(s) con error. Revisá el detalle arriba.")
                    
                    st.session_state.reset_key += 1
                    time.sleep(1.5)
                    st.rerun()
                elif errores > 0:
                    st.error("No se pudo extraer información. Intentá con fotos que enfoquen mejor el lote.")

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
# ### FIN DEL CÓDIGO ###
