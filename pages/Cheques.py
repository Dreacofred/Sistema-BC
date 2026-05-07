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
# 3. LÓGICA DE RECORTE INTELIGENTE (DIVIDE Y VENCERÁS)
# ==========================================
def recortar_cheques(img, cantidad):
    """Corta la imagen en N pedazos, asegurando un margen de seguridad."""
    w, h = img.size
    slices = []
    if cantidad <= 1:
        return [img]
        
    # Definimos orientación. Si es más ancha que alta, los cheques están lado a lado.
    if w > h:
        paso = w / cantidad
        superposicion = paso * 0.20 # 20% de margen para no cortar números a la mitad
        for i in range(cantidad):
            izq = max(0, int(i * paso - superposicion))
            der = min(w, int((i + 1) * paso + superposicion))
            slices.append(img.crop((izq, 0, der, h)))
    else:
        # Están apilados de arriba hacia abajo
        paso = h / cantidad
        superposicion = paso * 0.20
        for i in range(cantidad):
            arr = max(0, int(i * paso - superposicion))
            aba = min(h, int((i + 1) * paso + superposicion))
            slices.append(img.crop((0, arr, w, aba)))
            
    return slices

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
    st.caption("CONSEJO: Acomodá hasta 4 cheques derechos en la foto.")
    
    imagen_capturada = st.camera_input("Escanear con cámara", key=f"cam_{st.session_state.reset_key}")
    imagenes_subidas = st.file_uploader("O subir foto(s)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"up_{st.session_state.reset_key}")
    
    imagenes_a_procesar = []
    if imagen_capturada: imagenes_a_procesar.append(imagen_capturada)
    if imagenes_subidas: imagenes_a_procesar.extend(imagenes_subidas)

    if len(imagenes_a_procesar) > 0:
        st.write(f"**{len(imagenes_a_procesar)} imagen(es) lista(s)**.")
        st.image(imagenes_a_procesar, width=150)
        
        if st.button("✂️ Cortar y Procesar Imagen(es)", use_container_width=True):
            cheques_totales_nuevos = 0
            errores = 0
            
            prompt_conteo = "¿Cuántos cheques ves en esta imagen? Respondé ÚNICAMENTE con un número entero (ejemplo: 1, 2, 3 o 4)."
            
            prompt_extraccion = """
            Sos un experto bancario. Esta imagen es un RECORTE que contiene UN cheque principal. Extraé sus datos con precisión milimétrica.
            
            REGLAS ESTRICTAS DE EXTRACCIÓN:
            1. BANDA NUMÉRICA (Abajo, formato BBB-SSS-PPPP): 
               - Banco_Cod: Primeros 3 dígitos antes del primer guion.
               - Plaza: TERCER grupo de números (ej: 3100 o 3218). ¡NUNCA extraigas la sucursal (el número del medio)!
            2. FECHAS:
               - Fecha_Emision: Junto a la ciudad de emisión.
               - Fecha_Pago: Después de "Páguese el...". Si es un cheque al día, repetí la fecha de emisión.
            3. CUIT: Buscá "CUIT" y extraé el formato XX-XXXXXXXX-X.
            4. EMISOR: Es la Razón Social impresa. Ignorá las direcciones o nombres de ciudades (ej: Ignorá Alta Gracia, Leones, etc).
            5. IMPORTE: Solo los números enteros, sin puntos separadores (ej: 500000).
            
            Devolvé ÚNICAMENTE un objeto JSON puro (sin comillas invertidas ni texto adicional):
            {
                "Banco_Cod": "3 dígitos",
                "Plaza": "4 dígitos",
                "Banco_Nombre": "Nombre del Banco",
                "Numero_Cheque": "Número",
                "Importe": 0.00,
                "Fecha_Emision": "DD/MM/AAAA",
                "Fecha_Pago": "DD/MM/AAAA",
                "Emisor": "Razón Social o Titular",
                "CUIT": "XX-XXXXXXXX-X"
            }
            """
            
            with st.spinner("Iniciando guillotina digital..."):
                for i, archivo_imagen in enumerate(imagenes_a_procesar):
                    try:
                        archivo_imagen.seek(0)
                        img = Image.open(archivo_imagen)
                        
                        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
                        
                        max_dim = 2000 # Mantenemos alta resolución para el recorte
                        if max(img.size) > max_dim:
                            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                        
                        # --- PASO 1: Contar los cheques ---
                        resp_conteo = cliente_ia.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[prompt_conteo, img]
                        )
                        
                        numeros_encontrados = re.findall(r'\d+', resp_conteo.text)
                        cantidad = int(numeros_encontrados[0]) if numeros_encontrados else 1
                        cantidad = min(max(cantidad, 1), 5) # Límite lógico de 1 a 5
                        
                        st.info(f"📄 Foto {i+1}: Se detectaron {cantidad} cheques. Recortando y analizando...")
                        
                        # --- PASO 2: Recortar la imagen ---
                        recortes = recortar_cheques(img, cantidad)
                        
                        # --- PASO 3: Leer cheque por cheque (recortes) ---
                        for j, recorte in enumerate(recortes):
                            exito_recorte = False
                            for intento in range(3):
                                if exito_recorte: break
                                try:
                                    resp_recorte = cliente_ia.models.generate_content(
                                        model='gemini-2.5-flash',
                                        contents=[prompt_extraccion, recorte]
                                    )
                                    
                                    raw_text = resp_recorte.text.strip()
                                    marcador = chr(96) * 3
                                    if raw_text.startswith(f"{marcador}json"): raw_text = raw_text[7:-3].strip()
                                    elif raw_text.startswith(marcador): raw_text = raw_text[3:-3].strip()
                                    
                                    # Parseamos solo el OBJETO de este cheque
                                    start_idx = raw_text.find('{')
                                    end_idx = raw_text.rfind('}') + 1
                                    if start_idx != -1 and end_idx != 0:
                                        datos_cheque = json.loads(raw_text[start_idx:end_idx])
                                        datos_cheque["Operador"] = st.session_state.usuario_actual
                                        st.session_state.cheques_procesados.append(datos_cheque)
                                        cheques_totales_nuevos += 1
                                        exito_recorte = True
                                    else:
                                        raise ValueError("JSON no encontrado en este recorte.")
                                        
                                except Exception as e:
                                    if "503" in str(e) or "429" in str(e):
                                        time.sleep(3) # Pausa por saturación
                                    elif intento == 2:
                                        errores += 1
                                        st.warning(f"⚠️ Cheque {j+1} de la foto {i+1} ilegible. Podés cargarlo a mano.")
                            
                            time.sleep(2) # Respiro entre recortes para no enojar a Google
                            
                    except Exception as e:
                        errores += 1
                        st.error(f"❌ Falló el análisis general de la foto #{i+1}.")
                
                if cheques_totales_nuevos > 0:
                    st.success(f"¡Listo! Se procesaron {cheques_totales_nuevos} cheque(s) en total.")
                    st.session_state.reset_key += 1
                    time.sleep(1.5)
                    st.rerun()
                elif errores > 0:
                    st.error("No se pudo extraer información. Intentá sacar fotos individuales.")

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
