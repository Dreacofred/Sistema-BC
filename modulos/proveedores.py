"""
modulos/proveedores.py

Módulo "Facturas de Proveedores" de lector.py, separado a su propio archivo.

Se llama desde lector.py así: modulo_proveedores.mostrar(cliente_ia)
"""
import streamlit as st
import pandas as pd
import json
import io
import time
import gc
from datetime import datetime
from PIL import Image
from openpyxl.utils import get_column_letter

from core.prompts_ia import PROMPT_FACTURAS_PROVEEDORES


def mostrar(cliente_ia):
    if 'lote_pendientes_prov' not in st.session_state: st.session_state.lote_pendientes_prov = []
    if 'cola_extracciones_prov' not in st.session_state: st.session_state.cola_extracciones_prov = []
    if 'resumen_prov' not in st.session_state: st.session_state.resumen_prov = []

    st.title(f"🏢 Gestión de Proveedores")
    st.markdown('<p style="color:#666; font-size:16px;">Módulo de carga y digitalización de comprobantes de compras.</p>', unsafe_allow_html=True)

    if len(st.session_state.cola_extracciones_prov) > 0:
        total_restantes = len(st.session_state.cola_extracciones_prov)
        st.warning(f"Tienes {total_restantes} factura(s) esperando tu revisión.")

        datos_actuales = st.session_state.cola_extracciones_prov[0]
        st.markdown(f'<div class="tarjeta-pro"><h4>📝 Revisando: {datos_actuales.get("_origen", "Documento desconocido")}</h4></div>', unsafe_allow_html=True)

        with st.form("validador_proveedores"):
            def limpiar_texto(v): return "" if str(v).strip().lower() in ["none", "null", ""] else str(v).strip()
            def to_f(v):
                try:
                    v_str = str(v).strip().replace('.', '').replace(',', '.') if ',' in str(v) and '.' in str(v) else str(v).strip().replace(',', '.')
                    return float(v_str) if v_str else 0.0
                except: return 0.0

            v_fecha = limpiar_texto(datos_actuales.get('fecha', ''))
            v_cuit = limpiar_texto(datos_actuales.get('cuit_proveedor', ''))
            v_razon_social = limpiar_texto(datos_actuales.get('razon_social_proveedor', ''))
            v_nro_factura = limpiar_texto(datos_actuales.get('nro_factura', ''))
            v_concepto = limpiar_texto(datos_actuales.get('concepto', ''))

            c1, c2, c3 = st.columns([1, 1.5, 2])
            fecha = c1.text_input("Fecha", v_fecha)
            cuit = c2.text_input("CUIT Proveedor", v_cuit)
            razon_social = c3.text_input("Razón Social / Nombre", v_razon_social)

            c4, c5, c6, c7 = st.columns([1.5, 1, 1, 1])
            nro_factura = c4.text_input("Factura / Remito Nº", v_nro_factura)
            neto = c5.number_input("Importe Neto", value=to_f(datos_actuales.get('importe_neto', 0.0)))
            iva = c6.number_input("IVA", value=to_f(datos_actuales.get('importe_iva', 0.0)))
            total = c7.number_input("Total Factura", value=to_f(datos_actuales.get('importe_total', 0.0)))

            concepto = st.text_input("Concepto / Detalle", v_concepto)

            st.markdown("<br>", unsafe_allow_html=True)
            col_b1, col_b2 = st.columns(2)

            if col_b1.form_submit_button("✅ GUARDAR Y VER SIGUIENTE"):
                registro_prov = {"Fecha": fecha.strip(), "Proveedor": razon_social.strip().upper(), "CUIT": cuit.strip(), "Factura": nro_factura.strip(), "Neto": neto, "IVA": iva, "Total": total, "Concepto": concepto.strip()}
                st.session_state.resumen_prov.append(registro_prov)
                st.session_state.cola_extracciones_prov.pop(0)
                st.rerun()
            if col_b2.form_submit_button("🗑️ DESCARTAR"):
                st.session_state.cola_extracciones_prov.pop(0)
                st.rerun()

    else:
        tab1, tab2 = st.tabs(["📁 Subir Facturas", "📸 Cámara"])
        with tab1:
            st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
            fotos_disco = st.file_uploader("Seleccionar facturas o remitos", type=["pdf","jpg","png","jpeg"], accept_multiple_files=True, key="up_prov")
            if fotos_disco and st.button("➕ Sumar facturas a la Pila"):
                for f in fotos_disco: st.session_state.lote_pendientes_prov.append({'nombre': f.name, 'data': f.getvalue(), 'tipo': f.type})
                st.success(f"✅ Se sumaron {len(fotos_disco)} facturas.")
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
            foto_camara = st.camera_input("Enfocar factura", key="cam_prov")
            if foto_camara and st.button("➕ Sumar captura a la Pila"):
                st.session_state.lote_pendientes_prov.append({'nombre': f"Factura_{len(st.session_state.lote_pendientes_prov)+1}.jpg", 'data': foto_camara.getvalue(), 'tipo': foto_camara.type})
                st.success("✅ ¡Factura Agregada!")
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.lote_pendientes_prov:
            st.subheader(f"📦 Pila de Facturas ({len(st.session_state.lote_pendientes_prov)} documentos)")
            if st.button("🚀 INICIAR LECTURA DE PROVEEDORES"):
                barra_progreso, status_text = st.progress(0), st.empty()
                for i, doc in enumerate(st.session_state.lote_pendientes_prov):
                    status_text.text(f"Analizando {doc['nombre']}...")
                    exito, intentos, error_interno = False, 3, ""
                    while intentos > 0 and not exito:
                        try:
                            prompt_prov = PROMPT_FACTURAS_PROVEEDORES
                            modelo_actual = 'gemini-2.5-pro' if intentos > 1 else 'gemini-2.5-flash'

                            img_rem = Image.open(io.BytesIO(doc['data']))
                            res = cliente_ia.models.generate_content(model=modelo_actual, contents=[prompt_prov, img_rem])
                            raw_text = res.text.strip().replace('```json', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_extraidos = json.loads(raw_text[start:end])
                            datos_extraidos['_origen'] = doc['nombre']
                            st.session_state.cola_extracciones_prov.append(datos_extraidos)

                            try: img_rem.close()
                            except: pass
                            gc.collect()

                            exito = True
                        except Exception as e:
                            error_interno = str(e)
                            intentos -= 1
                            time.sleep(2)
                    if not exito: st.session_state.cola_extracciones_prov.append({'_origen': f"⚠️ Error Técnico en {doc['nombre']} | Falla: {error_interno}"})
                    barra_progreso.progress((i + 1) / len(st.session_state.lote_pendientes_prov))
                st.session_state.lote_pendientes_prov = []
                st.rerun()
            if st.button("🗑️ Vaciar Pila Proveedores"):
                st.session_state.lote_pendientes_prov = []
                st.rerun()

    if st.session_state.resumen_prov:
        st.divider()
        df_prov = pd.DataFrame(st.session_state.resumen_prov)
        st.subheader(f"📋 Planilla de Proveedores ({len(df_prov)} registros)")
        st.dataframe(df_prov, use_container_width=True)
        col_ex1, col_ex2 = st.columns(2)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_prov.to_excel(writer, index=False, sheet_name='Proveedores')
            ws = writer.sheets['Proveedores']
            for i, col in enumerate(df_prov.columns): ws.column_dimensions[get_column_letter(i + 1)].width = 20
        if col_ex1.download_button(label="📥 Descargar Excel de Proveedores", data=buffer.getvalue(), file_name=f"Proveedores_{datetime.now().strftime('%d-%m-%Y')}.xlsx", use_container_width=True):
            st.session_state.resumen_prov, st.session_state.cola_extracciones_prov, st.session_state.lote_pendientes_prov = [], [], []
            st.rerun()
        if col_ex2.button("🗑️ Vaciar sin descargar (Proveedores)", use_container_width=True):
            st.session_state.resumen_prov = []
            st.rerun()
