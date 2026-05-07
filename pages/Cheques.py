# Archivo: pages/Cheques.py
# INICIO DEL CÓDIGO
import streamlit as st
from google import genai
from PIL import Image, ImageDraw
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
    if imagen_capturada: imagenes_a_procesar.append(imagen_capturada)
    if imagenes_subidas: imagenes_a_procesar.extend(imagenes_subidas)

    if len(imagenes_a_procesar) > 0:
        st.write(f"**{len(imagenes_a_procesar)} imagen(es) en cola.**")
        
        # Espacio donde vamos a mostrar cómo se pinta de negro
        visor_proceso = st.empty()
        visor_proceso.image(imagenes_a_procesar[0], width=200, caption="Imagen original lista")
        
        if st.button("Procesar con Enmascaramiento", use_container_width=True):
            cheques_totales_nuevos = 0
            errores = 0
            
            prompt_conteo = "¿Cuántos cheques distintos hay en esta imagen? Respondé ÚNICAMENTE con un número entero (ejemplo: 1, 2, 3 o 4)."
            
            with st.spinner("Iniciando escaneo progresivo..."):
                for i, archivo_imagen in enumerate(imagenes_a_procesar):
                    try:
                        archivo_imagen.seek(0)
                        img = Image.open(archivo_imagen)
                        
                        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
                        
                        # Mantenemos alta resolución para lectura clara
                        max_dim = 2500 
                        if max(img.size) > max_dim:
                            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                        
                        w, h = img.size
                        es_horizontal = w > h
                        
                        # 1. Contar los cheques para saber cuántas veces iterar
                        resp_conteo = cliente_ia.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[prompt_conteo, img]
                        )
                        numeros_encontrados = re.findall(r'\d+', resp_conteo.text)
                        cantidad = int(numeros_encontrados[0]) if numeros_encontrados else 1
                        cantidad = min(max(cantidad, 1), 5)
                        
                        st.info(f"📄 Foto {i+1}: Detectados {cantidad} cheque(s). Iniciando lectura y borrado secuencial...")
                        
                        # 2. Inicializamos el lienzo y el límite del marcador negro
                        draw = ImageDraw.Draw(img)
                        limite_actual_pintado = 0
                        
                        # Variables dinámicas según orientación
                        orientacion_texto = "HORIZONTAL (uno al lado del otro)" if es_horizontal else "VERTICAL (apilados)"
                        clave_coordenada = "limite_derecho_x" if es_horizontal else "limite_inferior_y"
                        instruccion_enfoque = "el cheque más a la IZQUIERDA" if es_horizontal else "el cheque más ARRIBA"
                        
                        # 3. Bucle de Lectura y Pintado
                        for k in range(cantidad):
                            # Mostramos en pantalla cómo va quedando la imagen
                            visor_proceso.image(img, width=350, caption=f"Foto {i+1} - Analizando cheque {k+1} de {cantidad}...")
                            
                            prompt_extraccion = f"""
                            Rol: Especialista en OCR Financiero Argentino.
                            
                            Contexto: Los cheques están orientados de forma {orientacion_texto}. La imagen puede tener bloques negros tapando los cheques que ya procesamos.
                            
                            Tarea: Enfocate ÚNICAMENTE en {instruccion_enfoque} que esté VISIBLE (sin pintar de negro). Extraé sus datos.
                            Además, necesito saber dónde termina este cheque para poder taparlo de negro en el próximo paso.
                            
                            Estrategia de Ejecución (Chain of Thought):
                            Abre un `<Borrador_Analisis>`. Transcribe literalmente lo que ves del cheque actual.
                            
                            Restricciones:
                            - Banda Magnética: BBB-SSS-PPPP. Extraé Banco_Cod (BBB) y Plaza (PPPP). IGNORÁ SUCURSAL (SSS).
                            - Emisor: Razón Social. IGNORÁ "FILIAL", "SUCURSAL" o localidades.
                            - CUIT: Buscar "CUIT".
                            
                            Formato de Salida Obligatorio:
                            <Borrador_Analisis>
                            (Tu análisis mental aquí)
                            </Borrador_Analisis>
                            ```json
                            {{
                                "Banco_Cod": "3 dígitos",
                                "Plaza": "4 dígitos",
                                "Banco_Nombre": "String",
                                "Numero_Cheque": "String",
                                "Importe": 0,
                                "Fecha_Emision": "DD/MM/AAAA",
                                "Fecha_Pago": "DD/MM/AAAA",
                                "Emisor": "String",
                                "CUIT": "XX-XXXXXXXX-X",
                                "{clave_coordenada}": Número del 0 al 1000 que indica dónde termina el papel de ESTE cheque (0 es inicio, 1000 es fin de imagen).
                            }}
                            ```
                            """
                            
                            exito_lectura = False
                            for intento in range(3):
                                if exito_lectura: break
                                try:
                                    resp_lectura = cliente_ia.models.generate_content(
                                        model='gemini-2.5-flash',
                                        contents=[prompt_extraccion, img]
                                    )
                                    
                                    raw_text = resp_lectura.text.strip()
                                    texto_para_json = raw_text
                                    if "</Borrador_Analisis>" in raw_text:
                                        texto_para_json = raw_text.split("</Borrador_Analisis>")[1].strip()
                                    
                                    marcador = chr(96) * 3
                                    if texto_para_json.startswith(f"{marcador}json"): texto_para_json = texto_para_json[7:-3].strip()
                                    elif texto_para_json.startswith(marcador): texto_para_json = texto_para_json[3:-3].strip()
                                    
                                    start_idx_obj = texto_para_json.find('{')
                                    end_idx_obj = texto_para_json.rfind('}') + 1
                                    
                                    if start_idx_obj != -1 and end_idx_obj != 0:
                                        datos_cheque = json.loads(texto_para_json[start_idx_obj:end_idx_obj])
                                        
                                        # Extraemos la coordenada para pintar de negro y la sacamos del dict final
                                        coordenada_fin = datos_cheque.pop(clave_coordenada, 1000)
                                        
                                        datos_cheque["Operador"] = st.session_state.usuario_actual
                                        st.session_state.cheques_procesados.append(datos_cheque)
                                        cheques_totales_nuevos += 1
                                        exito_lectura = True
                                        
                                        # --- LA MAGIA DEL ENMASCARAMIENTO (PINTAMOS DE NEGRO) ---
                                        # Si la IA alucina y tira 1000, forzamos un avance matemático seguro
                                        if coordenada_fin >= 980 and k < (cantidad - 1):
                                            coordenada_fin = int((k + 1) * (1000 / cantidad))
                                            
                                        if es_horizontal:
                                            x_pixel = int(w * (coordenada_fin / 1000.0))
                                            # Evitamos retroceder
                                            if x_pixel <= limite_actual_pintado: x_pixel = limite_actual_pintado + int(w/cantidad)
                                            draw.rectangle([limite_actual_pintado, 0, x_pixel, h], fill="black")
                                            limite_actual_pintado = x_pixel
                                        else:
                                            y_pixel = int(h * (coordenada_fin / 1000.0))
                                            # Evitamos retroceder
                                            if y_pixel <= limite_actual_pintado: y_pixel = limite_actual_pintado + int(h/cantidad)
                                            draw.rectangle([0, limite_actual_pintado, w, y_pixel], fill="black")
                                            limite_actual_pintado = y_pixel
                                            
                                    else:
                                        raise ValueError("JSON roto.")
                                        
                                except Exception as e:
                                    if "503" in str(e) or "429" in str(e): time.sleep(3)
                                    elif intento == 2:
                                        errores += 1
                                        st.warning(f"⚠️ Cheque {k+1} ilegible. Avanzando al siguiente...")
                                        # Si falla, pintamos de negro matemáticamente para poder avanzar
                                        avance = int(w/cantidad) if es_horizontal else int(h/cantidad)
                                        limite_actual_pintado += avance
                                        if es_horizontal: draw.rectangle([0, 0, limite_actual_pintado, h], fill="black")
                                        else: draw.rectangle([0, 0, w, limite_actual_pintado], fill="black")
                            
                            time.sleep(2) # Respiro para Google
                            
                    except Exception as e:
                        errores += 1
                        st.error(f"❌ Falló el análisis de la foto #{i+1}.")
                
                # Al final mostramos la imagen toda tapada
                visor_proceso.image(img, width=350, caption="¡Escaneo completado!")
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Listo! Se procesaron {cheques_totales_nuevos} cheque(s).")
                    st.session_state.reset_key += 1
                    time.sleep(1.5)
                    st.rerun()
                elif errores > 0:
                    st.error("No se pudo extraer información.")

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
