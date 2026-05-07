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
            with st.spinner(f"Analizando en ALTA RESOLUCIÓN {len(imagenes_a_procesar)} foto(s)... (Puede tardar unos segundos)"):
                cheques_totales_nuevos = 0
                errores = 0
                
                # --- PROMPT MAESTRO ---
                prompt = """
                Rol: Especialista en Visión Artificial, OCR Financiero y Extracción de Datos (Contexto Bancario Argentino).

                Contexto: El sistema procesa fotografías que contienen entre 1 y 4 cheques físicos apilados. Existe un riesgo crítico de "alucinación por saturación" (cruzar el CUIT, importe o fechas de un cheque a otro). 

                Tarea: Analizar la imagen aplicando "Chain of Thought" (Cadena de Pensamiento). Debes aislar visualmente cada cheque y procesarlo secuencialmente de arriba hacia abajo (o izquierda a derecha). Mientras analizas un cheque, debes ignorar el resto de la imagen.

                Restricciones y Reglas de Extracción:
                1. Banda Magnética (zona inferior): Formato BBB-SSS-PPPP. Extrae el 1er grupo de 3 dígitos (Banco_Cod) y el 3er grupo de 4 dígitos (Plaza). El 2do grupo (Sucursal) se ignora por completo.
                2. Fechas: Si el cheque NO especifica una fecha de pago diferido (no dice "Páguese el..."), entonces la "Fecha_Pago" debe ser exactamente igual a la "Fecha_Emision".
                3. Emisor: Identifica la Razón Social o el titular impreso, generalmente cerca del CUIT. Ignora direcciones, nombres de localidades o sellos de goma.
                4. CUIT: Busca la palabra literal "CUIT" para extraer el número.
                5. Importe: Extraer el valor numérico exacto y convertirlo a un número entero continuo, sin puntos separadores de miles ni signos.
                6. Aislamiento estricto: Prohibido combinar datos de diferentes cheques.

                Formato de salida:
                Tu respuesta DEBE contener obligatoriamente dos partes:
                1. Un bloque de texto llamado `<Borrador_Analisis>` donde detalles tu lectura cheque por cheque para asegurar que no cruzas datos.
                2. Un bloque de código con UN SOLO ARRAY de objetos JSON puros, respetando ESTRICTAMENTE la siguiente estructura:

                ```json
                [
                  {
                    "Banco_Cod": "3 dígitos",
                    "Plaza": "4 dígitos",
                    "Banco_Nombre": "Nombre del Banco",
                    "Numero_Cheque": "Número del cheque",
                    "Importe": número entero sin puntos,
                    "Fecha_Emision": "DD/MM/AAAA",
                    "Fecha_Pago": "DD/MM/AAAA",
                    "Emisor": "Razón Social o Titular",
                    "CUIT": "XX-XXXXXXXX-X"
                  }
                ]
                ```
                """
                
                for i, archivo_imagen in enumerate(imagenes_a_procesar):
                    exito = False
                    
                    for intento in range(3):
                        if exito:
                            break
                            
                        try:
                            archivo_imagen.seek(0)
                            img = Image.open(archivo_imagen)
                            
                            if img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')
                                
                            # Resolución alta para lectura nítida
                            max_dim = 3000 
                            if max(img.size) > max_dim:
                                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                            
                            respuesta = cliente_ia.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[prompt, img]
                            )
                            
                            raw_text = respuesta.text.strip()
                            
                            texto_para_json = raw_text
                            if "</Borrador_Analisis>" in raw_text:
                                texto_para_json = raw_text.split("</Borrador_Analisis>")[1].strip()
                            
                            marcador = chr(96) * 3
                            if texto_para_json.startswith(f"{marcador}json"): 
                                texto_para_json = texto_para_json[7:-3].strip()
                            elif texto_para_json.startswith(marcador): 
                                texto_para_json = texto_para_json[3:-3].strip()
                            
                            try:
                                start_idx = texto_para_json.find('[')
                                end_idx = texto_para_json.rfind(']') + 1
                                if start_idx != -1 and end_idx != 0:
                                    datos_extraidos = json.loads(texto_para_json[start_idx:end_idx])
                                else:
                                    start_idx_obj = texto_para_json.find('{')
                                    end_idx_obj = texto_para_json.rfind('}') + 1
                                    if start_idx_obj != -1 and end_idx_obj != 0:
                                        datos_extraidos = [json.loads(texto_para_json[start_idx_obj:end_idx_obj])]
                                    else:
                                        raise ValueError("No se detectó el bloque JSON final en la respuesta.")
                            except Exception as parse_err:
                                raise ValueError(f"Error al estructurar los datos finales. {parse_err}")
                            
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
                                    st.warning(f"⏳ Servidor ocupado. Reintentando foto #{i+1} en breve...")
                                    time.sleep(3)
                                else:
                                    errores += 1
                                    st.error(f"❌ Falló la foto #{i+1}. Excedió el tiempo límite.")
                            else:
                                if intento < 2:
                                    st.warning(f"🔄 Releyendo foto #{i+1} para mejorar precisión...")
                                    time.sleep(2)
                                else:
                                    errores += 1
                                    st.error(f"❌ Falló la foto #{i+1} | DETALLE: {error_str}")
                                    break 
                    
                    time.sleep(2)
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Se procesaron {cheques_totales_nuevos} cheque(s) en total!")
                    if errores > 0:
                        st.warning(f"Aviso: Hubo error en {errores} foto(s). Revisá el detalle arriba.")
                    
                    st.session_state.reset_key += 1
                    time.sleep(1.5)
                    st.rerun()
                elif errores > 0:
                    st.error("No se pudo extraer la información. Asegurate de que los cheques estén legibles.")

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
