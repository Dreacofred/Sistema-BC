import streamlit as st
import utils_bcra
import re
import time
import random
import io
import pandas as pd
from datetime import datetime
from PIL import Image
from google import genai
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN E IDENTIDAD
# ==========================================
st.set_page_config(page_title="BC Consultas", page_icon="🛡️", layout="wide")

URL_LOGO_OFICIAL = "https://bjhykcdhafoqpfkpngvw.supabase.co/storage/v1/object/public/remitos/Logo%20nuevo.png"

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] {display: none !important;}
        .stApp { background-color: #f4f6f9 !important; }
        .tarjeta-pro {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px;
        }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONEXIONES A LA BÓVEDA
# ==========================================
# (La app de clientes usa tus mismas llaves para poder consultar)
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)
cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# ==========================================
# 3. INTERFAZ DEL CLIENTE
# ==========================================
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    st.image(URL_LOGO_OFICIAL, width=100)
with col_titulo:
    st.title("🛡️ Verificación de Cheques")
    st.markdown('<p style="color:#666;">Herramienta exclusiva para clientes de BC Combustibles.</p>', unsafe_allow_html=True)

tab_manual, tab_ia, tab_masivo = st.tabs(["✍️ Consulta Manual", "📸 Escáner de Cheques (IA)", "📋 Carga Masiva (Excel)"])

# --- PESTAÑA 1: MANUAL ---
with tab_manual:
    st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
    cuit_input = st.text_input("Ingresá el CUIT (solo números)", max_chars=11, key="cuit_manual")
    if st.button("Validar Riesgo Manual", type="primary"):
        cuit_limpio = re.sub(r'\D', '', cuit_input)
        if len(cuit_limpio) != 11:
            st.error("❌ CUIT inválido.")
        else:
            with st.spinner('Consultando historial en el BCRA...'):
                datos = utils_bcra.consultar_bcra_completo(cuit_limpio)
                
                if datos and not datos.get("error_api"):
                    st.markdown(f"**Titular:** {datos['denominacion']}")
                    col1, col2 = st.columns(2)
                    col1.metric("Situación Crediticia", f"Nivel {datos['situacion']}")
                    
                    if datos['cheques_rechazados'] > 0:
                        col2.error(f"⚠️ {datos['cheques_rechazados']} Cheques Rechazados")
                        st.warning("🚨 RIESGO DETECTADO EN EL BCRA.")
                    else:
                        col2.success("✅ 0 Cheques Rechazados")
                else:
                    st.error(f"Falla de conexión: {datos.get('error_api')}")
    st.markdown('</div>', unsafe_allow_html=True)

# --- PESTAÑA 2: IA ---
with tab_ia:
    if 'lote_procesado' not in st.session_state: st.session_state['lote_procesado'] = []
    fotos_lote = st.file_uploader("📸 Subí hasta 3 fotos de cheques", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
    if fotos_lote and st.button("🚀 Procesar Lotes", type="primary"):
        st.session_state['lote_procesado'] = []
        with st.spinner("Procesando fotos y consultando BCRA..."):
            barra_p = st.progress(0)
            for idx, foto in enumerate(fotos_lote):
                img = Image.open(foto)
                img.thumbnail((2500, 3000), Image.Resampling.LANCZOS)
                
                lista_cheques = utils_bcra.procesar_lote_cheques_ia(cliente_ia, img)
                
                for cheque in lista_cheques:
                    cuit_limpio = re.sub(r'\D', '', str(cheque.get("cuit", "")))
                    datos_bcra = utils_bcra.consultar_bcra_completo(cuit_limpio) if len(cuit_limpio) == 11 else None
                    st.session_state['lote_procesado'].append({"img": img, **cheque, "datos_bcra": datos_bcra})
                
                barra_p.progress((idx + 1) / len(fotos_lote))
        st.rerun()

   if st.session_state.get('lote_procesado'):
        for i, cheque in enumerate(st.session_state['lote_procesado']):
            st.markdown("---")
            c1, c2 = st.columns([1, 2])
            with c1: 
                st.image(cheque["img"], use_container_width=True)
            with c2:
                emisor_ia = cheque.get('emisor', 'Emisor Desconocido')
                st.markdown(f"**🏦 Cheque Nº {cheque.get('numero_cheque')}** | **Emisor:** {emisor_ia}")
                st.markdown(f"**CUIT:** `{cheque.get('cuit')}`")
                
                bcra = cheque.get("datos_bcra")
                if bcra and not bcra.get("error_api"):
                    # 🚀 LÓGICA ARQUITECTÓNICA: Detección de "Sin Cuentas"
                    nombre_bcra = bcra.get('denominacion', 'Cliente Desconocido')
                    sit = bcra.get('situacion', 1)
                    rechazos = bcra.get('cheques_rechazados', 0)
                    
                    # Si el BCRA no tiene historial de deudas, no hay Situación numérica
                    if nombre_bcra == "Cliente Desconocido":
                        sit_texto = "Sin cuentas activas"
                        nombre_mostrar = emisor_ia # Usamos el nombre que leyó la IA
                    else:
                        sit_texto = str(sit)
                        nombre_mostrar = nombre_bcra
                        
                    # Evaluar si el cheque es un riesgo (Tiene rechazos o Situación mala)
                    if rechazos > 0 or (isinstance(sit, int) and sit != 1):
                        st.error(f"🚨 BCRA: {nombre_mostrar} | Situación: {sit_texto} | Rechazos: {rechazos}")
                    else:
                        st.success(f"✅ BCRA: {nombre_mostrar} | Situación: {sit_texto} | 0 Rechazos")
                else:
                    st.warning("⚠️ Error en consulta BCRA o CUIT inválido.")
                    
        if st.button("🧹 Limpiar Resultados"):
            st.session_state['lote_procesado'] = []
            st.rerun()

# --- PESTAÑA 3: CARGA MASIVA ---
with tab_masivo:
    if 'resultados_masivos_cli' not in st.session_state: st.session_state['resultados_masivos_cli'] = None
    st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
    st.info("💡 Pegá una lista de CUITs. El sistema los filtrará y procesará automáticamente.")
    texto_cuits = st.text_area("Lista de CUITs", height=150)
    
    if st.button("🚀 Iniciar Consulta Masiva", type="primary"):
        lineas = texto_cuits.replace('-', '').replace(' ', '\n').split('\n')
        lista_cuits = list(set([re.sub(r'\D', '', l) for l in lineas if len(re.sub(r'\D', '', l)) == 11]))
        
        if not lista_cuits: st.error("❌ No se detectaron CUITs válidos.")
        else:
            if len(lista_cuits) > 20:
                st.warning("⚠️ Procesaremos solo los primeros 20.")
                lista_cuits = lista_cuits[:20]
            
            barra_p = st.progress(0)
            resultados_temporales = []
            for i, cuit in enumerate(lista_cuits):
                datos = utils_bcra.consultar_bcra_completo(cuit)
                if datos and not datos.get("error_api"):
                    sit, rechazos, nombre = datos.get("situacion", ""), datos.get("cheques_rechazados", 0), datos.get("denominacion", "")
                    estado = "🟢 APROBADO" if sit == 1 and rechazos == 0 else "🔴 RECHAZADO"
                    if rechazos in [-1, -429]: estado = "⚠️ ERROR API"
                    resultados_temporales.append({"CUIT": cuit, "Razón Social": nombre, "Situación": sit, "Cheques Rech.": rechazos, "Estado": estado})
                else:
                    motivo = datos.get("error_api", "Error") if datos else "Timeout"
                    resultados_temporales.append({"CUIT": cuit, "Razón Social": f"🚨 {motivo}", "Situación": "-", "Cheques Rech.": "-", "Estado": "⚠️ ERROR"})
                
                barra_p.progress((i + 1) / len(lista_cuits))
            
            st.session_state['resultados_masivos_cli'] = resultados_temporales
            st.rerun()

    if st.session_state.get('resultados_masivos_cli'):
        df_masivo = pd.DataFrame(st.session_state['resultados_masivos_cli'])
        st.dataframe(df_masivo, use_container_width=True)
        
        c_btn1, c_btn2 = st.columns(2)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as wr:
            df_masivo.to_excel(wr, index=False, sheet_name='Reporte BCRA')
        
        c_btn1.download_button("📥 Descargar Reporte", data=buf.getvalue(), file_name=f"Reporte_Riesgo_{datetime.now().strftime('%d%m%Y')}.xlsx", use_container_width=True)
        if c_btn2.button("🧹 Limpiar Pantalla", use_container_width=True):
            st.session_state['resultados_masivos_cli'] = None
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
