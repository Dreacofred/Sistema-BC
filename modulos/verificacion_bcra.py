"""
modulos/verificacion_bcra.py

Módulo "Verificación BCRA" de lector.py, separado a su propio archivo.

MIGRADO A CLAUDE (agosto 2026): el escáner de cheques (pestaña "Escáner de
Cheques IA Pro") ahora usa Claude a través de utils_bcra.procesar_lote_cheques_ia,
que migró de Gemini a Claude. Por eso el segundo parámetro de mostrar() ahora
tiene que ser un cliente de Anthropic (anthropic.Anthropic), no un cliente de
Gemini como antes.

Se llama desde lector.py así: modulo_bcra.mostrar(supabase, cliente_claude)
"""
import streamlit as st
import utils_bcra
import requests
import time
import json
import urllib3
import re
import random
import io
import pandas as pd
from datetime import datetime
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def mostrar(supabase, cliente_claude):
    # --- INTERFAZ CON 3 PESTAÑAS ---
    tab_manual, tab_ia, tab_masivo = st.tabs(["✍️ Consulta Manual", "📸 Escáner de Cheques (IA Pro)", "📋 Carga Masiva (Excel)"])

    # ==========================================
    # PESTAÑA 1: CONSULTA MANUAL
    # ==========================================
    with tab_manual:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        cuit_input = st.text_input("Ingresá el CUIT (solo números)", max_chars=11, key="cuit_manual")

        if st.button("Validar Riesgo Manual"):
            cuit_limpio = re.sub(r'\D', '', cuit_input)

            if len(cuit_limpio) != 11:
                st.error("❌ CUIT inválido. Debe contener exactamente 11 números.")
            else:
                registro_interno = supabase.table("cuits_afectados").select("*").eq("cuit", cuit_limpio).execute()
                if registro_interno.data:
                    st.error(f"⚠️ Este CUIT ya está en nuestra lista de AFECTADOS (Nivel {registro_interno.data[0]['situacion_bcra']}).")
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
                                if st.button("Confirmar y Enviar a Lista Negra", key="btn_save_manual"):
                                    utils_bcra.guardar_en_lista_negra(supabase, cuit_limpio, datos['situacion'], datos['denominacion'], f"Rechazos: {datos['cheques_rechazados']}")
                            elif datos['cheques_rechazados'] == 0:
                                col2.success("✅ 0 Cheques Rechazados")
                                st.success("Operación totalmente segura.")
                            else:
                                col2.warning("El BCRA bloqueó la lectura del historial. Intente nuevamente.")
                        elif datos and datos.get("error_api"):
                            st.error(f"Falla de conexión con el túnel (ScraperAPI): {datos['error_api']}")
        st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # PESTAÑA 2: ESCÁNER DE LOTES MÚLTIPLES (IA PRO + COLA)
    # ==========================================
    with tab_ia:
        if 'lote_procesado' not in st.session_state:
            st.session_state['lote_procesado'] = []

        fotos_lote = st.file_uploader("📸 Subí hasta 3 fotos de cheques", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

        if fotos_lote:
            if st.button("🚀 Procesar Lotes (IA Avanzada)", type="primary"):
                st.session_state['lote_procesado'] = []

                with st.spinner("Procesando fotos y consultando BCRA..."):
                    barra_p = st.progress(0)
                    total_fotos = len(fotos_lote)

                    for idx, foto in enumerate(fotos_lote):
                        img = Image.open(foto)
                        img.thumbnail((2500, 3000), Image.Resampling.LANCZOS)

                        lista_cheques = utils_bcra.procesar_lote_cheques_ia(cliente_claude, img)

                        for numero_orden, cheque in enumerate(lista_cheques, start=1):
                            cuit_limpio = re.sub(r'\D', '', str(cheque.get("cuit") or ""))
                            datos_bcra = None

                            if len(cuit_limpio) == 11:
                                time.sleep(random.uniform(1.5, 3.5))
                                datos_bcra = utils_bcra.consultar_bcra_completo(cuit_limpio)

                            st.session_state['lote_procesado'].append({
                                "img": img,
                                "id": numero_orden,
                                "numero_cheque": cheque.get("numero_cheque"),
                                "emisor": cheque.get("emisor"),
                                "cuit": cheque.get("cuit"),
                                "cuit_limpio": cuit_limpio,
                                "datos_bcra": datos_bcra
                            })

                        barra_p.progress((idx + 1) / total_fotos)

                    st.success("✅ Lote procesado completamente.")

        # --- RENDERIZADO DE RESULTADOS ---
        if st.session_state.get('lote_procesado'):
            st.markdown("### 📋 Resultados de Auditoría")

            for i, cheque in enumerate(st.session_state['lote_procesado']):
                st.markdown("---")
                col1, col2 = st.columns([1, 2])
                with col1:
                    with st.expander("Ver Foto"):
                        st.image(cheque["img"], use_container_width=True)
                with col2:
                    st.markdown(f"**🏦 Cheque Nº {cheque.get('numero_cheque')}** | **Emisor:** {cheque.get('emisor')}")
                    st.markdown(f"**CUIT:** `{cheque.get('cuit')}`")

                    bcra = cheque.get("datos_bcra")
                    if bcra and not bcra.get("error_api"):
                        if bcra['situacion'] == 1 and bcra['cheques_rechazados'] == 0:
                            st.success(f"✅ BCRA: {bcra['denominacion']} | Sit: 1 | 0 Rechazos")
                        else:
                            st.error(f"🚨 BCRA: {bcra['denominacion']} | Sit: {bcra['situacion']} | Rechazos: {bcra['cheques_rechazados']}")
                            if st.button(f"Guardar en Lista Negra", key=f"btn_lote_{i}"):
                                utils_bcra.guardar_en_lista_negra(supabase, cheque['cuit_limpio'], bcra['situacion'], bcra['denominacion'], f"Rechazos: {bcra['cheques_rechazados']}")
                    else:
                        st.warning("⚠️ Consulta fallida o CUIT inválido.")
                        if bcra and bcra.get("error_api"):
                            st.error(f"Error Técnico: {bcra['error_api']}")

            if st.button("🧹 Limpiar Resultados"):
                st.session_state['lote_procesado'] = []
                st.rerun()

    # ==========================================
    # PESTAÑA 3: CARGA MASIVA (CAJA DE DISPARO RÁPIDO)
    # ==========================================
    with tab_masivo:
        if 'resultados_masivos' not in st.session_state:
            st.session_state['resultados_masivos'] = None

        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        st.info("💡 Pegá una lista de CUITs (ej. copiados desde un Excel). El sistema los filtrará y procesará automáticamente.")
        texto_cuits = st.text_area("Lista de CUITs", height=150, placeholder="30123456789\n20123456789\n...")

        if st.button("🚀 Iniciar Consulta Masiva"):
            lineas = texto_cuits.replace('-', '').replace(' ', '\n').split('\n')
            lista_cuits = []

            for l in lineas:
                c = re.sub(r'\D', '', l)
                if len(c) == 11 and c not in lista_cuits:
                    lista_cuits.append(c)

            if not lista_cuits:
                st.error("❌ No se detectaron CUITs válidos de 11 dígitos en el texto.")
            else:
                if len(lista_cuits) > 20:
                    st.warning(f"⚠️ Detectamos {len(lista_cuits)} CUITs. Para evitar bloqueos, procesaremos solo los primeros 20.")
                    lista_cuits = lista_cuits[:20]

                st.write(f"⏳ Procesando {len(lista_cuits)} CUITs... Podés dejar esta pestaña abierta.")
                barra_p = st.progress(0)
                resultados_temporales = []

                for i, cuit in enumerate(lista_cuits):
                    datos = utils_bcra.consultar_bcra_completo(cuit)

                    if datos and not datos.get("error_api"):
                        sit = datos.get("situacion", "")
                        rechazos = datos.get("cheques_rechazados", "")
                        nombre = datos.get("denominacion", "")

                        estado = "🟢 APROBADO" if sit == 1 and rechazos == 0 else "🔴 RECHAZADO"
                        if rechazos in [-1, -429]: estado = "⚠️ ERROR API"

                        resultados_temporales.append({
                            "CUIT": cuit, "Razón Social": nombre,
                            "Situación": sit, "Cheques Rech.": rechazos, "Estado": estado
                        })
                    else:
                        motivo_real = datos.get("error_api", "Error fatal desconocido") if datos else "Timeout masivo"
                        resultados_temporales.append({
                            "CUIT": cuit, "Razón Social": f"🚨 {motivo_real}",
                            "Situación": "-", "Cheques Rech.": "-", "Estado": "⚠️ ERROR"
                        })

                    barra_p.progress((i + 1) / len(lista_cuits))
                    time.sleep(1.5)

                st.success("✅ ¡Consulta Masiva Finalizada!")
                st.session_state['resultados_masivos'] = resultados_temporales
                st.rerun()

        if st.session_state.get('resultados_masivos'):
            df_masivo = pd.DataFrame(st.session_state['resultados_masivos'])
            st.dataframe(df_masivo, use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            col_btn1, col_btn2 = st.columns(2)

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as wr:
                df_masivo.to_excel(wr, index=False, sheet_name='Reporte BCRA')

            col_btn1.download_button(
                "📥 Descargar Reporte en Excel",
                data=buf.getvalue(),
                file_name=f"Reporte_Riesgo_{datetime.now().strftime('%d%m%Y')}.xlsx",
                use_container_width=True
            )

            if col_btn2.button("🧹 Limpiar Pantalla", use_container_width=True):
                st.session_state['resultados_masivos'] = None
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
