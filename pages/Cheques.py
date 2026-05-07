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
import re
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
    st.caption("CONSEJO: Acomodá hasta 4 cheques en la foto. Procurá buena luz.")
    
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
            with st.spinner(f"El experto IA está analizando {len(imagenes_a_procesar)} foto(s)... (Puede tardar unos segundos extra por el nivel de detalle)"):
                cheques_totales_nuevos = 0
                errores = 0
                
                # --- SÚPER PROMPT CREADO POR EL GEM ---
                prompt = """
                Rol: Especialista en Visión Artificial, OCR Financiero y Extracción Estructurada de Datos (Contexto Bancario Argentino).

                Contexto: Vas a procesar una imagen que contiene entre 1 y 4 cheques físicos argentinos (apilados vertical u horizontalmente). Las imágenes presentan alta densidad de información, sellos superpuestos, múltiples fechas y ruido visual.

                Tarea: Extraer con 100% de precisión los datos críticos de CADA cheque en la imagen y estructurarlos en un JSON. Para evitar cruzar datos entre cheques o inventar información (alucinación por saturación), es OBLIGATORIO que realices un análisis metódico cheque por cheque antes de emitir la respuesta final.

                Estrategia de Ejecución (Chain of Thought OBLIGATORIO):
                Antes de generar el JSON, debes abrir un bloque de texto llamado `<Borrador_Analisis>`. En este bloque, debes hacer una transcripción mental secuencial (de arriba hacia abajo o izquierda a derecha). Por cada cheque detectado, redacta de forma muy concisa:
                1. Ubicación: (Ej: Cheque 1 - Arriba).
                2. Banda Magnética: [Escribe la banda detectada BBB-SSS-PPPP]. Aislar Banco_Cod y Plaza.
                3. Importe: [Escribe el importe numérico detectado. Verifica visualmente la cantidad exacta de ceros].
                4. Fechas: [Identificar emisión vs. pago].
                5. Emisor y CUIT: [Identificar el texto exacto ubicado en la misma línea].

                Restricciones y Reglas de Negocio Críticas:
                - Banda Magnética (zona inferior): El formato es siempre `BBB-SSS-PPPP`. 
                  * `Banco_Cod` = 1er grupo de 3 dígitos (`BBB`).
                  * `Plaza` = 3er grupo de 4 dígitos (`PPPP`). 
                  * SUCURSAL = 2do grupo (`SSS`) -> DEBE IGNORARSE COMPLETAMENTE.
                - Fechas: Si el cheque NO especifica una fecha de pago diferido (no dice "Páguese el..."), entonces la `Fecha_Pago` debe ser idéntica a la `Fecha_Emision`.
                - Emisor: Debe ser la Razón Social o titular impreso. Para evitar extraer nombres erróneos, DEBES buscar el nombre del emisor que se encuentra al lado del CUIT o en su mismo renglón. Ignora absolutamente cualquier texto proveniente de sellos de goma, direcciones o nombres de localidades.
                - CUIT: Buscar exclusivamente la palabra literal "CUIT" para extraer el número (Formato XX-XXXXXXXX-X).
                - Importe Exacto: No asumas valores. Verifica estrictamente la cantidad de ceros (ej. no confundir 500.000 con 500). El valor final debe ser un número entero sin separadores de miles ni puntos.
                - Aislamiento: La información de un cheque no debe mezclarse jamás con la del cheque adyacente.

                Formato de Salida:
                Tu respuesta DEBE contener únicamente dos bloques: el `<Borrador_Analisis>` y un bloque de código con UN SOLO ARRAY de objetos JSON puros. No agregues saludos ni explicaciones fuera de este formato.

                <Borrador_Analisis>
                (Tu análisis secuencial paso a paso aquí)
                </Borrador_Analisis>
                ```json
                [
                  {
                    "Banco_Cod": "3 dígitos",
                    "Plaza": "4 dígitos",
                    "Banco_Nombre": "String",
                    "Numero_Cheque": "String",
                    "Importe": 0,
                    "Fecha_Emision": "DD/MM/AAAA",
                    "Fecha_Pago": "DD/MM/AAAA",
                    "Emisor": "String",
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
                                
                            max_dim = 1600 
                            if max(img.size) > max_dim:
                                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                            
                            respuesta = cliente_ia.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[prompt, img]
                            )
                            
                            raw_text = respuesta.text.strip()
                            
                            # --- NUEVA LÓGICA DE PARSEO INTELIGENTE ---
                            # Separamos el borrador (pensamiento de la IA) del JSON final
                            texto_para_json = raw_text
                            if "</Borrador_Analisis>" in raw_text:
                                texto_para_json = raw_text.split("</Borrador_Analisis>")[1].strip()
                            
                            # Limpiamos las comillas invertidas si las puso
                            marcador = chr(96) * 3
                            if texto_para_json.startswith(f"{marcador}json"): 
                                texto_para_json = texto_para_json[7:-3].strip()
                            elif texto_para_json.startswith(marcador): 
                                texto_para_json = texto_para_json[3:-3].strip()
                            
                            # Intentamos extraer el array JSON
                            try:
                                start_idx = texto_para_json.find('[')
                                end_idx = texto_para_json.rfind(']') + 1
                                if start_idx != -1 and end_idx != 0:
                                    datos_extraidos = json.loads(texto_para_json[start_idx:end_idx])
                                else:
                                    # Por si devuelve un solo objeto
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
                                    st.warning(f"🔄 Ajustando lectura de foto #{i+1} para mejorar precisión...")
                                    time.sleep(2)
                                else:
                                    errores += 1
                                    st.error(f"❌ Falló la foto #{i+1} | DETALLE: {error_str}")
                                    break 
                    
                    time.sleep(2)
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Se procesaron {cheques_totales_nuevos} cheque(s) en total con alta precisión!")
                    if errores > 0:
                        st.warning(f"Ojo: Hubo {errores} foto(s) con error. Revisá el detalle arriba.")
                    
                    st.session_state.reset_key += 1
                    time.sleep(1.5)
                    st.rerun()
                elif errores > 0:
                    st.error("No se pudo extraer información. Asegurate de que los cheques estén legibles.")

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
