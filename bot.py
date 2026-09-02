# ESTE BOT ES EL QUE MANEJA LA AUDITORIA DE LOS COMPROBANTES QUE ESTAN PENDIENTES DE AUDITAR
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time

from core.cuentas_propias import resolver_banco_destino

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

st.title("🏢 Auditoría de Comprobantes - BC Combustibles")
st.markdown("---")

# ==========================================
# 2. TRAER LOTES PENDIENTES
# ==========================================
@st.cache_data(ttl=10)
def obtener_datos():
    respuesta = supabase.table("cobranzas_pendientes").select("*").execute()
    return respuesta.data

datos_db = obtener_datos()
df_completo = pd.DataFrame(datos_db)

if df_completo.empty or not (df_completo['estado_auditoria'] == 'Pendiente').any():
    st.success("🎉 ¡Bandeja limpia! No hay comprobantes pendientes de auditoría en este momento.")
    st.stop()

# Solo trabajamos con los pendientes
df_pendientes = df_completo[df_completo['estado_auditoria'] == 'Pendiente'].copy()
lotes_disponibles = df_pendientes['cliente_asociado'].unique().tolist()

# ==========================================
# 3. VARIABLES DE MEMORIA
# ==========================================
if 'cheques_listos' not in st.session_state:
    st.session_state.cheques_listos = []
if 'datos_corregidos' not in st.session_state:
    st.session_state.datos_corregidos = {}

# ==========================================
# 4. SELECTOR DE LOTE
# ==========================================
st.subheader("📥 Bandeja de Pendientes")
cliente_sel = st.selectbox("Seleccioná un cliente para auditar su lote:", ["--- Elegí un cliente ---"] + lotes_disponibles)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. PANTALLA DE AUDITORÍA (ESTILO ACORDEÓN)
# ==========================================
if cliente_sel != "--- Elegí un cliente ---":
    df_lote = df_pendientes[df_pendientes['cliente_asociado'] == cliente_sel].copy()

    st.markdown(f"### 📋 Revisión de Comprobantes: {cliente_sel}")

    for index, fila in df_lote.iterrows():
        cid = fila['id']
        ya_listo = cid in st.session_state.cheques_listos

        # Icono dinámico según si ya lo guardamos en memoria
        icono = "✅ LISTO" if ya_listo else "🟠 PENDIENTE"

        # Mostramos los datos actualizados si ya se corrigieron, sino los de la base
        monto_display = st.session_state.datos_corregidos.get(cid, {}).get('monto', fila.get('monto', 0))
        nro_display = st.session_state.datos_corregidos.get(cid, {}).get('numero_identificador', fila.get('numero_identificador', 'S/N'))
        tipo_display = fila.get('tipo_comprobante') or 'Comprobante'
        if not nro_display or str(nro_display).strip() == "":
            nro_display = "S/N"

        # ACORDEÓN EXPANDIBLE
        with st.expander(f"{icono} | {tipo_display} Nº {nro_display} | Monto: ${float(monto_display or 0):,.2f}"):

            # ACÁ ESTÁ LA MAGIA: 1 de ancho para el form, 1.8 para la imagen (casi el doble de tamaño)
            col_datos, col_img = st.columns([1, 1.8])

            # --- MITAD DERECHA: IMAGEN GIGANTE ---
            with col_img:
                url_activa = str(fila['archivo_url']).split(',')[0].strip() if pd.notna(fila['archivo_url']) else ""

                if url_activa.startswith('http'):
                    if ".pdf" in url_activa.lower():
                        visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                        st.markdown(f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>', unsafe_allow_html=True)
                        st.link_button("📄 Abrir PDF en pestaña grande", url_activa)
                    else:
                        st.image(url_activa, use_container_width=True)
                        st.link_button("🖼️ Ver imagen original", url_activa)
                else:
                    st.warning("Este comprobante no tiene imagen adjunta.")

            # --- MITAD IZQUIERDA: FORMULARIO ESTILO LISTA ---
            with col_datos:
                if ya_listo:
                    st.success("✔️ Fila revisada y guardada temporalmente.")
                    if st.button("✏️ Editar nuevamente", key=f"btn_edit_{cid}"):
                        st.session_state.cheques_listos.remove(cid)
                        st.rerun()
                else:
                    # Si falta el código de banco (típico en eCheqs y
                    # transferencias, que casi nunca lo traen impreso),
                    # intentamos resolverlo solos comparando los datos de
                    # destino que extrajo la IA contra las cuentas propias
                    # de BC ya cargadas en Supabase.
                    codigo_banco_sugerido = fila.get('codigo_banco', '')
                    if not str(codigo_banco_sugerido or '').strip():
                        cuenta_resuelta = resolver_banco_destino(
                            supabase,
                            cuenta_destino=fila.get('cuenta_destino'),
                            cbu_cvu_destino=fila.get('cbu_cvu_destino'),
                            alias_destino=fila.get('alias_destino'),
                        )
                        if cuenta_resuelta:
                            codigo_banco_sugerido = cuenta_resuelta.get('codigo_banco') or ''
                            st.success(f"🏦 Banco de destino detectado automáticamente: **{cuenta_resuelta['banco']}**")
                        elif fila.get('tipo_comprobante') == 'Transferencia':
                            st.warning(
                                "⚠️ No se pudo identificar automáticamente el banco de destino. "
                                "Completalo a mano si lo sabés."
                            )

                    with st.form(f"form_cheque_{cid}"):
                        st.markdown("📝 **Completá o corregí:**")

                        # Función que crea la estructura: Texto a la Izq, Caja a la Der
                        def crear_campo(etiqueta, valor, tipo="texto"):
                            c_lbl, c_inp = st.columns([1, 1.5])
                            c_lbl.markdown(f"<div style='margin-top: 8px; font-size: 14px;'>{etiqueta}</div>", unsafe_allow_html=True)
                            if tipo == "numero":
                                return c_inp.number_input(etiqueta, value=float(valor or 0.0), label_visibility="collapsed")
                            else:
                                return c_inp.text_input(etiqueta, value=str(valor), label_visibility="collapsed")

                        f_nro = crear_campo("Nº Comprobante", fila.get('numero_identificador', ''))
                        f_monto = crear_campo("Monto ($)", fila.get('monto', 0.0), tipo="numero")
                        f_emi = crear_campo("Emisión", fila.get('fecha_emision', ''))
                        f_pago = crear_campo("Vencimiento", fila.get('fecha_pago', ''))
                        f_banco = crear_campo("Cód. Banco", codigo_banco_sugerido)
                        f_sucursal = crear_campo("Cód. Sucursal", fila.get('codigo_sucursal', ''))
                        f_cuenta = crear_campo("Nº Cuenta", fila.get('numero_cuenta', ''))
                        f_cuit = crear_campo("CUIT Emisor", fila.get('cuit_emisor', ''))
                        f_rs = crear_campo("Razón Social", fila.get('razon_social_emisor', ''))

                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.form_submit_button("✅ Guardar Fila", type="primary", use_container_width=True):
                            # Guardamos los cambios en la memoria temporal
                            st.session_state.datos_corregidos[cid] = {
                                'numero_identificador': f_nro.strip(),
                                'monto': f_monto,
                                'fecha_emision': f_emi.strip(),
                                'fecha_pago': f_pago.strip(),
                                'codigo_banco': f_banco.strip(),
                                'codigo_sucursal': f_sucursal.strip(),
                                'numero_cuenta': f_cuenta.strip(),
                                'cuit_emisor': f_cuit.strip(),
                                'razon_social_emisor': f_rs.strip(),
                                'estado_auditoria': 'Auditado'
                            }
                            st.session_state.cheques_listos.append(cid)
                            st.rerun()

    # ==========================================
    # 6. CIERRE Y EXPORTACIÓN DEL LOTE
    # ==========================================
    st.markdown("<br><hr>", unsafe_allow_html=True)
    faltantes = len(df_lote) - len(st.session_state.cheques_listos)

    if faltantes > 0:
        st.info(f"⚠️ Faltan revisar {faltantes} comprobante(s) para poder exportar y cerrar el lote.")
    else:
        st.success("🎉 ¡Excelente! Todos los comprobantes de este lote fueron revisados.")
        st.markdown("### 🚀 Exportación a Regente")

        # Armamos la tabla final para exportar
        filas_export = []
        suma_total = 0
        for cid in df_lote['id']:
            d = st.session_state.datos_corregidos[cid]
            suma_total += d['monto']
            filas_export.append({
                "Titular": d['razon_social_emisor'],
                "Emision": d['fecha_emision'],
                "Venc.": d['fecha_pago'],
                "Nro": d['numero_identificador'],
                "Bco.": d['codigo_banco'],
                "NCta.": d['numero_cuenta'],
                "Plaza": d['codigo_sucursal'],
                "Monto": d['monto']
            })

        df_regente = pd.DataFrame(filas_export)
        st.metric("Suma Total Auditada", f"${suma_total:,.2f}")

        col_ex1, col_ex2 = st.columns(2)

        # Botón de descarga
        csv_data = df_regente.to_csv(index=False).encode('utf-8')
        col_ex1.download_button(
            label="⬇️ 1. Descargar Archivo para Regente",
            data=csv_data,
            file_name=f"importacion_regente_{cliente_sel.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Cierre en base de datos
        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
        confirmar = col_ex2.checkbox("Confirmo que ya descargué el archivo CSV")
        if col_ex2.button("✅ 2. CERRAR LOTE EN BASE DE DATOS", disabled=not confirmar, type="primary", use_container_width=True):
            with st.spinner("Guardando en la nube..."):
                try:
                    # Impactamos cada cheque corregido en Supabase
                    for cid in st.session_state.cheques_listos:
                        datos_finales = st.session_state.datos_corregidos[cid].copy()
                        # Limpieza de vacíos para SQL
                        for key, value in datos_finales.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                datos_finales[key] = None

                        supabase.table("cobranzas_pendientes").update(datos_finales).eq("id", cid).execute()

                    st.success("¡Lote cerrado y limpiado de la bandeja con éxito!")

                    # Limpiamos la memoria para el próximo lote
                    st.session_state.cheques_listos = []
                    st.session_state.datos_corregidos = {}
                    time.sleep(1.5)
                    st.cache_data.clear()
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

        # ==========================================
        # 7. (NUEVO) VISTA PREVIA DE INTEGRACIÓN CON REGENTE
        # ==========================================
        # Este bloque es 100% aparte de todo lo de arriba. NO reemplaza el
        # CSV ni el cierre de lote — es solo una herramienta de prueba para
        # ir viendo cómo se comportaría la integración real con Regente,
        # antes de conectarla de verdad. NO manda ni crea nada en Regente,
        # NI modifica nada en Supabase. Solo hace consultas de LECTURA.
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🧪 Vista previa de integración con Regente (no manda nada, solo prueba)"):
            st.caption(
                "Arma los datos tal como se mandarían a Regente y consulta si "
                "cada emisor ya existe (búsqueda real, de solo lectura). "
                "No crea ni modifica nada en Regente ni en Supabase."
            )
            if st.button("🔍 Generar vista previa"):
                try:
                    from core.regente_mapeo import armar_grupos_para_regente
                    from core.regente_resolucion import resolver_emisor

                    # 1. Buscar el id_sujeto_regente del cliente en Supabase
                    res_cliente = (
                        supabase.table("clientes")
                        .select("id_sujeto_regente")
                        .eq("nombre", cliente_sel)
                        .execute()
                    )
                    id_sujeto_cliente = (
                        res_cliente.data[0]["id_sujeto_regente"] if res_cliente.data else None
                    )

                    if not id_sujeto_cliente:
                        st.error(
                            f"⚠️ El cliente '{cliente_sel}' no tiene cargado su "
                            "id_sujeto_regente en la tabla clientes de Supabase. "
                            "No se puede armar el Recibo sin ese dato."
                        )
                    else:
                        # 2. Armar las filas del lote: tipo_comprobante original
                        #    + los datos ya corregidos en la auditoría
                        filas_lote = []
                        for cid in df_lote["id"]:
                            fila_original = df_lote[df_lote["id"] == cid].iloc[0]
                            datos_fila = dict(st.session_state.datos_corregidos[cid])
                            datos_fila["id"] = cid
                            datos_fila["tipo_comprobante"] = fila_original.get("tipo_comprobante")
                            filas_lote.append(datos_fila)

                        # 3. Armar los grupos (Recibo + Valores) — sin llamar a ninguna API
                        resultado = armar_grupos_para_regente(filas_lote, id_sujeto_cliente)

                        if resultado["sin_procesar"]:
                            st.warning("⚠️ Hay filas que no se pueden mandar automáticamente:")
                            for item in resultado["sin_procesar"]:
                                st.write(f"- Fila {item['fila_id']}: {item['motivo']}")

                        if not resultado["grupos"]:
                            st.info("No hay ningún grupo armable en este lote.")
                        else:
                            for grupo in resultado["grupos"]:
                                st.markdown(
                                    f"#### 📦 Grupo: {grupo['tipo_grupo']} "
                                    f"({len(grupo['valores'])} valor(es))"
                                )
                                st.json(grupo["recibo"], expanded=False)

                                for valor in grupo["valores"]:
                                    dv = valor["datos_valor"]
                                    emisor = valor["emisor"]

                                    st.markdown(
                                        f"**Fila {valor['_fila_id']}** — "
                                        f"{emisor['sujeto']} (CUIT {emisor['cuit']}) — "
                                        f"${dv['monto']:,.2f}"
                                    )

                                    with st.spinner(f"Consultando Regente para {emisor['sujeto']}..."):
                                        try:
                                            decision = resolver_emisor(
                                                cuit_cheque=emisor["cuit"],
                                                razon_social_cheque=emisor["sujeto"],
                                                numero_cuenta=dv["nro_cuenta"],
                                                id_adm=dv["id_adm"],
                                            )
                                        except Exception as e:
                                            st.error(f"❌ Error consultando Regente: {e}")
                                            continue

                                    if decision["accion"] == "usar_existente":
                                        st.success(
                                            f"✅ Sujeto ya existe (id_sujeto={decision['id_sujeto']}). "
                                            f"{decision['motivo']}"
                                        )
                                    elif decision["accion"] == "crear_cuenta_para_existente":
                                        st.info(
                                            f"ℹ️ Sujeto existente (id_sujeto={decision['id_sujeto']}), "
                                            f"falta crear la cuenta. {decision['motivo']}"
                                        )
                                    elif decision["accion"] == "crear_sujeto_y_cuenta":
                                        st.warning(
                                            f"🆕 Emisor nuevo, habría que crear sujeto y cuenta. "
                                            f"{decision['motivo']}"
                                        )
                                    else:
                                        st.error(f"⚠️ Caso dudoso, revisar a mano. {decision['motivo']}")

                                st.markdown("<hr>", unsafe_allow_html=True)

                except RuntimeError as e:
                    st.error(
                        f"⚠️ Faltan credenciales de Regente: {e}\n\n"
                        "Revisá que REGENTE_API_URL, REGENTE_API_USUARIO y "
                        "REGENTE_API_TOKEN estén cargados en los Secrets de esta app "
                        "(la de lector.py, ya que bot.py corre adentro de ella vía "
                        "Laboratorio IA)."
                    )
                except Exception as e:
                    st.error(f"❌ Error inesperado armando la vista previa: {e}")
