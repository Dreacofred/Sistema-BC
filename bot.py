import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y CREDENCIALES
# ==========================================
st.set_page_config(page_title="Auditoría SICE", layout="wide")

URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

st.title("🏢 Centro de Auditoría - BC Combustibles")
st.markdown("Revisá los lotes enviados desde la pista, validá la lectura de la IA y exportá a Regente.")
st.markdown("---")

# ==========================================
# 2. TRAER LOTES PENDIENTES DE SUPABASE
# ==========================================
@st.cache_data(ttl=10) # Se actualiza cada 10 segundos
def obtener_pendientes():
    respuesta = supabase.table("cobranzas_pendientes").select("*").eq("estado_auditoria", "Pendiente").execute()
    return respuesta.data

datos_pendientes = obtener_pendientes()

if not datos_pendientes:
    st.success("🎉 ¡Bandeja limpia! No hay lotes pendientes de auditoría en este momento.")
    st.stop()

# Agrupar los cheques por Cliente para armar la "Bandeja de Entrada"
df_pendientes = pd.DataFrame(datos_pendientes)
lotes_disponibles = df_pendientes['cliente_asociado'].unique().tolist()

# ==========================================
# 3. BANDEJA DE ENTRADA (EN PANTALLA PRINCIPAL)
# ==========================================
st.subheader("📥 Bandeja de Pendientes")

# Armamos la lista con una opción vacía al principio
opciones_desplegable = ["--- Elegí un cliente ---"] + lotes_disponibles

# Menú desplegable en el centro de la pantalla
lote_seleccionado = st.selectbox(
    "Seleccioná un lote para auditar:",
    opciones_desplegable
)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

# ==========================================
# 4. PANTALLA PRINCIPAL: AUDITORÍA (Maestro/Detalle)
# ==========================================
if lote_seleccionado != "--- Elegí un cliente ---":
    st.subheader(f"Auditoría en curso: Lote {lote_seleccionado}")
    
    # Filtramos solo los datos del lote seleccionado
    df_lote = df_pendientes[df_pendientes['cliente_asociado'] == lote_seleccionado].copy()

    # --- 1. TABLA GENERAL (A TODO EL ANCHO) ---
    st.write("📊 **Resumen del Lote (Vista General)**")
    
    # Función para pintar la fila de verde si ya está auditada
    def pintar_verde(fila):
        # Usamos .get por las dudas, chequeando si dice 'Auditado'
        if fila.get('estado_auditoria') == 'Auditado':
            return ['background-color: #c3e6cb; color: #155724'] * len(fila)
        return [''] * len(fila)

    # Mostramos la tabla bloqueada (solo lectura) pero pintada
    st.dataframe(
        df_lote[columnas_visibles].style.apply(pintar_verde, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()

    # --- 2. ZONA DE AUDITORÍA INDIVIDUAL ---
    st.subheader("🔍 Estación de Revisión")
    
    # Armamos la lista para el desplegable con un tilde si ya está listo
    opciones_cheques = ["--- Elegí un comprobante ---"]
    for _, fila in df_lote.iterrows():
        icono = "✅" if fila.get('estado_auditoria') == 'Auditado' else "⏳"
        opciones_cheques.append(f"{icono} Cheque N° {fila.get('numero_identificador', 'S/N')} | Monto: ${fila.get('monto', 0)} | ID: {fila['id']}")

    cheque_sel = st.selectbox("Seleccioná un comprobante para auditar y ver su imagen:", opciones_cheques)

    if cheque_sel != "--- Elegí un comprobante ---":
        # Extraemos el ID del final del texto (después de 'ID: ')
        id_seleccionado = cheque_sel.split("ID: ")[1]
        df_fila = df_lote[df_lote['id'] == id_seleccionado].copy()

        # --- A. EDITOR DE LA FILA ---
        st.write("📝 **Datos extraídos (Corregí acá si la IA se equivocó)**")
        fila_editada = st.data_editor(df_fila[columnas_visibles], hide_index=True, use_container_width=True, disabled=["id"])
        
        # --- B. BOTÓN DE CONFIRMACIÓN ---
        if st.button("✅ Confirmar y Marcar como OK", use_container_width=True):
            datos_nuevos = fila_editada.iloc[0].to_dict()
            datos_nuevos['estado_auditoria'] = 'Auditado' # Le cambiamos el estado
            
            # Actualizamos en Supabase
            supabase.table("cobranzas_pendientes").update(datos_nuevos).eq("id", id_seleccionado).execute()
            
            # Avisamos y recargamos la página para que se pinte de verde
            st.success("¡Comprobante auditado correctamente!")
            import time
            time.sleep(1)
            st.rerun()

        st.write("---")
        
        # --- C. VISOR DE ARCHIVOS DEL LOTE ---
        st.write("📸 **Documentos Adjuntos**")
        urls_crudas = df_fila['archivo_url'].dropna().unique().tolist()
        
        urls_limpias = []
        for url_str in urls_crudas:
            if isinstance(url_str, str):
                for u in url_str.split(','):
                    u_limpia = u.strip()
                    if u_limpia.startswith('http'):
                        urls_limpias.append(u_limpia)
                        
        urls_limpias = list(dict.fromkeys(urls_limpias))

        if urls_limpias:
            opciones = [f"Archivo {i+1}" for i in range(len(urls_limpias))]
            seleccion = st.radio("Navegar por las imágenes del lote:", opciones, horizontal=True, label_visibility="collapsed")
            indice = opciones.index(seleccion)
            url_activa = urls_limpias[indice]
            
            try:
                if ".pdf" in url_activa.lower():
                    visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                    mostrar_pdf = f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>'
                    st.markdown(mostrar_pdf, unsafe_allow_html=True)
                    st.link_button("📄 Abrir PDF en otra pestaña", url_activa)
                else:
                    st.image(url_activa, use_container_width=True)
            except Exception as e:
                st.error(f"Error al cargar el archivo.")
        else:
            st.warning("Este lote no tiene imágenes adjuntas.")
    with col_grilla:
        st.write("📊 **Datos Extraídos por IA (Editables)**")
        
        # Preparamos las columnas que la administración realmente necesita ver/editar
        columnas_visibles = [
            'id', 'numero_identificador', 'monto', 'fecha_emision', 
            'fecha_pago', 'codigo_banco', 'codigo_sucursal', 
            'numero_cuenta', 'cuit_emisor', 'razon_social_emisor'
        ]
        
        # Mostramos la grilla editable
        df_mostrar = df_lote[columnas_visibles].copy()
        datos_editados = st.data_editor(
            df_mostrar,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            disabled=["id"] # Bloqueamos el ID para que no lo rompan sin querer
        )
        
        st.write("---")
        st.write("### Auditoría y Exportación")
        suma_cheques = datos_editados['monto'].sum()
        st.metric("Suma Total de Cheques Auditados", f"${suma_cheques:,.2f}")
        
        if st.button("✅ Aprobar Lote y Generar Excel", type="primary"):
            with st.spinner("Guardando auditoría y generando archivo..."):
                try:
                    # 1. Actualizamos Supabase fila por fila con las correcciones
                    for index, fila in datos_editados.iterrows():
                        fila_dict = fila.to_dict()
                        
                        # Extraemos el ID y lo sacamos de la lista de datos a actualizar
                        id_fila = fila_dict.pop('id', None)
                        
                        # Si el ID es inválido (ej: se agregó una fila vacía por accidente), la saltamos
                        if pd.isna(id_fila) or str(id_fila).strip() in ["None", "<NA>", ""]:
                            continue
                            
                        # Limpieza extrema: Reemplazamos textos basura de Streamlit por vacíos reales (NULL en SQL)
                        for key, value in fila_dict.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                fila_dict[key] = None
                                
                        # Le clavamos el sello de Auditado
                        fila_dict['estado_auditoria'] = 'Auditado'
                        
                        # Actualizamos en la base de datos usando el ID limpio
                        supabase.table("cobranzas_pendientes").update(fila_dict).eq("id", id_fila).execute()
                    
                    st.success("🎉 ¡Base de datos actualizada con éxito! El lote ya no está pendiente.")
                    
                    # 2. Generamos el Excel mapeado para Regente
                    df_regente = pd.DataFrame({
                        "Titular": datos_editados.get("razon_social_emisor", ""),
                        "Emision": datos_editados.get("fecha_emision", ""),
                        "Venc.": datos_editados.get("fecha_pago", ""),
                        "Nro": datos_editados.get("numero_identificador", ""),
                        "Bco.": datos_editados.get("codigo_banco", ""),
                        "NCta.": datos_editados.get("numero_cuenta", ""),
                        "Plaza": datos_editados.get("codigo_sucursal", ""),
                        "Monto": datos_editados.get("monto", 0.0)
                    })
                    
                    csv_data = df_regente.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="⬇️ Descargar Archivo para Regente",
                        data=csv_data,
                        file_name=f"importacion_regente_{lote_seleccionado.replace(' ', '_')}.csv",
                        mime="text/csv",
                    )
                    
                    st.info("👆 Clic en el botón para descargar. (Refrescá la página para seguir con el próximo lote).")
                    
                except Exception as e:
                    st.error(f"Error al guardar la auditoría: {e}")
