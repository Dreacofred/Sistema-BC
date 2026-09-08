"""
modulos/verificacion_bcra.py

Módulo "Verificación BCRA" de lector.py, separado a su propio archivo.

MIGRADO A CLAUDE (agosto 2026): el escáner de cheques (pestaña "Escáner de
Cheques IA Pro") ahora usa Claude a través de utils_bcra.procesar_lote_cheques_ia,
que migró de Gemini a Claude. Por eso el segundo parámetro de mostrar() ahora
tiene que ser un cliente de Anthropic (anthropic.Anthropic), no un cliente de
Gemini como antes.

Se llama desde lector.py así: modulo_bcra.mostrar(supabase, cliente_claude)

DETALLE DE RIESGO (septiembre 2026): utils_bcra.consultar_bcra_completo ahora
devuelve, además de los campos de siempre, "detalle_entidades" (una fila por
banco donde el CUIT tiene deuda informada) y "detalle_cheques" (una fila por
cheque rechazado, con fecha, causal, monto y nombre de entidad). Este módulo
los muestra en desplegables (st.expander) en las tres pestañas.

En "Carga Masiva", la tabla de resultados es interactiva (st.dataframe con
on_select="rerun"): al hacer clic en una fila se muestra el detalle de ese
CUIT debajo, con los desplegables ya abiertos. OJO: esto requiere Streamlit
1.35 o superior. Si al desplegar tira error en esa línea, revisar la versión
fijada en requirements.txt.
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


# Colores para pintar filas enteras en las tablas de detalle (semáforo).
COLOR_VERDE_CLARO = "#C8E6C9"   # Multa Pagada / Situación 1
COLOR_ROJO_CLARO = "#FFCDD2"    # Multa Impaga / Situación 2
COLOR_ROJO_MEDIO = "#EF9A9A"    # Situación 3
COLOR_ROJO_FUERTE = "#E57373"   # Situación 4
COLOR_ROJO_INTENSO = "#EF5350"  # Situación 5
COLOR_ROJO_MAXIMO = "#B71C1C"   # Situación 6 o superior (por las dudas)


def _pintar_fila_cheques(fila):
    """Devuelve el estilo CSS de toda la fila según si el CHEQUE fue pagado
    (verde clarito) o no (rojo clarito). Ojo: esto mira la columna "Fecha
    Pago" (pago del cheque en sí), NO la columna "Multa" (que es sobre la
    multa que aplica el BCRA por el rechazo — son cosas distintas). Si
    "Fecha Pago" tiene una fecha real, el cheque se pagó; si dice
    "Sin pagar", no. Se usa con df.style.apply(axis=1)."""
    color = COLOR_ROJO_CLARO if fila.get("Fecha Pago") == "Sin pagar" else COLOR_VERDE_CLARO
    return [f"background-color: {color}"] * len(fila)


def _pintar_fila_entidades(fila):
    """Devuelve el estilo CSS de toda la fila según la Situación BCRA:
    1 = verde clarito, y de 2 a 5 (o más) va de rojo clarito a rojo intenso.
    Se usa con df.style.apply(axis=1)."""
    colores_por_situacion = {
        1: COLOR_VERDE_CLARO,
        2: COLOR_ROJO_CLARO,
        3: COLOR_ROJO_MEDIO,
        4: COLOR_ROJO_FUERTE,
        5: COLOR_ROJO_INTENSO,
    }
    try:
        situacion = int(fila.get("Situación"))
    except (TypeError, ValueError):
        situacion = None

    if situacion in colores_por_situacion:
        color = colores_por_situacion[situacion]
    elif situacion is not None and situacion > 5:
        color = COLOR_ROJO_MAXIMO
    else:
        color = "#FFFFFF"  # Situación desconocida ("-"), sin pintar

    return [f"background-color: {color}"] * len(fila)


def _mostrar_detalle_bcra(datos, key_prefix="", expandido=False):
    """
    Dibuja los dos desplegables de detalle (entidades y cheques rechazados)
    para un diccionario "datos" devuelto por utils_bcra.consultar_bcra_completo.
    Se usa en las tres pestañas para no repetir el mismo bloque de código.
    "key_prefix" evita colisiones de key cuando se llama varias veces en un
    mismo rerun (por ejemplo, una vez por cada cheque del lote).
    "expandido" controla si el desplegable arranca abierto o cerrado.

    Las filas se pintan tipo semáforo (ver _pintar_fila_cheques y
    _pintar_fila_entidades más arriba) para que de un vistazo se note qué
    cheque está pagado y qué situación crediticia tiene cada entidad.
    """
    detalle_entidades = datos.get("detalle_entidades") or []
    detalle_cheques = datos.get("detalle_cheques") or []

    if detalle_entidades:
        with st.expander(f"📊 Ver detalle por entidad ({len(detalle_entidades)})", expanded=expandido):
            df_entidades = pd.DataFrame(detalle_entidades)
            st.dataframe(
                df_entidades.style.apply(_pintar_fila_entidades, axis=1),
                use_container_width=True, hide_index=True, key=f"df_entidades_{key_prefix}"
            )

    if detalle_cheques:
        with st.expander(f"📄 Ver detalle de cheques rechazados ({len(detalle_cheques)})", expanded=expandido):
            df_cheques = pd.DataFrame(detalle_cheques)
            st.dataframe(
                df_cheques.style.apply(_pintar_fila_cheques, axis=1),
                use_container_width=True, hide_index=True, key=f"df_cheques_{key_prefix}"
            )


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
                            st.session_state['ultimo_resultado_manual'] = datos
                            st.session_state['ultimo_cuit_manual'] = cuit_limpio
                        elif datos and datos.get("error_api"):
                            st.session_state['ultimo_resultado_manual'] = None
                            st.error(f"Falla de conexión con el túnel (ScraperAPI): {datos['error_api']}")

        # --- RENDERIZADO DEL RESULTADO (fuera del if del botón, para que el
        # detalle no desaparezca si Streamlit vuelve a correr el script por
        # otra interacción, como abrir un expander) ---
        datos = st.session_state.get('ultimo_resultado_manual')
        if datos:
            st.markdown(f"**Titular:** {datos['denominacion']}")
            col1, col2 = st.columns(2)
            col1.metric("Situación Crediticia", f"Nivel {datos['situacion']}")
            if datos['cheques_rechazados'] > 0:
                col2.error(f"⚠️ {datos['cheques_rechazados']} Cheques Rechazados")
                st.warning("🚨 RIESGO DETECTADO EN EL BCRA.")
            elif datos['cheques_rechazados'] == 0:
                col2.success("✅ 0 Cheques Rechazados")
                st.success("Operación totalmente segura.")
            else:
                col2.warning("El BCRA bloqueó la lectura del historial. Intente nuevamente.")

            _mostrar_detalle_bcra(datos, key_prefix="manual")

            if datos['cheques_rechazados'] > 0:
                if st.button("Confirmar y Enviar a Lista Negra", key="btn_save_manual"):
                    cuit_guardar = st.session_state.get('ultimo_cuit_manual', re.sub(r'\D', '', cuit_input))
                    utils_bcra.guardar_en_lista_negra(supabase, cuit_guardar, datos['situacion'], datos['denominacion'], f"Rechazos: {datos['cheques_rechazados']}")
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

                        _mostrar_detalle_bcra(bcra, key_prefix=f"lote_{i}")

                        if bcra['situacion'] != 1 or bcra['cheques_rechazados'] != 0:
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
        if 'datos_completos_masivos' not in st.session_state:
            st.session_state['datos_completos_masivos'] = {}

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
                datos_completos_temp = {}

                for i, cuit in enumerate(lista_cuits):
                    datos = utils_bcra.consultar_bcra_completo(cuit)
                    datos_completos_temp[cuit] = datos

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
                st.session_state['datos_completos_masivos'] = datos_completos_temp
                st.rerun()

        if st.session_state.get('resultados_masivos'):
            df_masivo = pd.DataFrame(st.session_state['resultados_masivos'])

            st.caption("💡 Hacé clic en una fila de la tabla para ver el detalle de ese CUIT más abajo.")
            evento_tabla = st.dataframe(
                df_masivo,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_resultados_masivos",
            )

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
                st.session_state['datos_completos_masivos'] = {}
                st.rerun()

            # --- DETALLE DEL CUIT SELECCIONADO (clic en la fila) ---
            filas_seleccionadas = []
            if evento_tabla and getattr(evento_tabla, "selection", None):
                filas_seleccionadas = evento_tabla.selection.rows

            if filas_seleccionadas:
                idx_sel = filas_seleccionadas[0]
                cuit_seleccionado = str(df_masivo.iloc[idx_sel]["CUIT"])
                datos_sel = st.session_state['datos_completos_masivos'].get(cuit_seleccionado)

                st.markdown(f"#### 🔍 Detalle — CUIT {cuit_seleccionado}")
                if datos_sel and not datos_sel.get("error_api"):
                    detalle_entidades = datos_sel.get("detalle_entidades") or []
                    detalle_cheques = datos_sel.get("detalle_cheques") or []
                    if detalle_entidades or detalle_cheques:
                        _mostrar_detalle_bcra(datos_sel, key_prefix=f"masivo_{cuit_seleccionado}", expandido=True)
                    else:
                        st.info("Sin deudas ni cheques rechazados informados para este CUIT.")
                else:
                    st.warning("No se pudo obtener el detalle de este CUIT (falló la consulta).")
            else:
                st.caption("Ningún CUIT seleccionado todavía.")

        st.markdown('</div>', unsafe_allow_html=True)
