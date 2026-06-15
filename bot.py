import streamlit as st
import json
import tempfile
import os
import time
import pandas as pd
from supabase import create_client, Client
import google.generativeai as genai

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

supabase: Client = create_client(URL_SB, KEY_SB)
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. ENCABEZADOS
# ==========================================
st.title("🤖 Laboratorio IA - Lotes S.I.C.E. a Regente")
st.markdown("Subí el ticket y los cheques. La IA pensará en voz alta, extraerá los datos (incluyendo la cuenta limpia) y armará el archivo para importar en Regente.")
st.markdown("---")

# ==========================================
# 3. MOTOR IA (GEMINI 2.5 PRO - Cadena de Pensamiento)
# ==========================================
def procesar_lote_con_ia(archivos_subidos, cliente_tag):
    archivos_gemini_creados = []
    rutas_temporales = []
    
    try:
        for archivo in archivos_subidos:
            extension = os.path.splitext(archivo.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
                tmp_file.write(archivo.getvalue())
                rutas_temporales.append(tmp_file.name)
            
            archivo_g = genai.upload_file(tmp_file.name)
            archivos_gemini_creados.append(archivo_g)

        modelo = genai.GenerativeModel('gemini-2.5-pro')
        
        # EL SÚPER PROMPT DEFINITIVO
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Analizá este lote: UN ticket S.I.C.E. y VARIAS fotos de cheques. Cliente: '{cliente_tag}'.
        
        PASO 1 (RAZONAMIENTO): Detallá qué ves en cada cheque en el campo 'razonamiento_en_voz_alta'. Si hay garabatos ilegibles, dejalo por escrito.
        
        PASO 2 (EXTRACCIÓN ESTRICTA): Completá los datos. 
        - REGLA 1: Si dudás sobre un dato manuscrito, dejalo vacío (""). NO inventes.
        - REGLA 2: Para 'razon_social_emisor', buscá el texto impreso junto al CUIT. Ignorá el 'Páguese a' manuscrito.
        - REGLA 3: Para 'numero_cuenta', buscá en el recuadro superior derecho o en la banda magnética y extraé los números crudos, SIN guiones, ni barras, ni espacios (ej: 03800111186).
        
        Devolvé ÚNICAMENTE un objeto JSON con esta estructura exacta:
        {{
            "razonamiento_en_voz_alta": "Tu análisis...",
            "resumen_lote": {{
                "total_declarado_ticket": numero_decimal,
                "efectivo_declarado": numero_decimal
            }},
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco",
                    "codigo_banco": "Código banco (ej: 014)",
                    "codigo_sucursal": "Código sucursal/plaza (ej: 1842)",
                    "numero_cuenta": "Número de cuenta limpio",
                    "numero_identificador": "Número del cheque",
                    "monto": numero_decimal,
                    "fecha_emision": "YYYY-MM-DD",
                    "fecha_pago": "YYYY-MM-DD",
                    "cuit_emisor": "CUIT con guiones",
                    "razon_social_emisor": "Razón social impresa",
                    "estado_auditoria": "Pendiente",
                    "regente_cliente_id": "1045"
                }}
            ]
        }}
        """
        
        contenido_a_procesar = archivos_gemini_creados + [prompt]
        respuesta = modelo.generate_content(contenido_a_procesar)
        
        for g_file in archivos_gemini_creados:
            genai.delete_file(g_file.name)
        for tmp_path in rutas_temporales:
            os.remove(tmp_path)
            
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_json)

    except Exception as e:
        st.error(f"Error en el Motor de Lotes: {e}")
        for tmp_path in rutas_temporales:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return None

# ==========================================
# 4. INTERFAZ VISUAL Y GUARDADO
# ==========================================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 1. Ingreso del Lote")
    cliente_input = st.text_input("Etiqueta del Cliente", value="Pan American Energy")
    archivos = st.file_uploader("Subir Ticket y Cheques", type=['png', 'jpeg', 'jpg', 'pdf'], accept_multiple_files=True)

    if archivos and st.button("🧠 Auditar Lote Completo"):
        with st.spinner(f"Analizando imágenes y caligrafía..."):
            datos_extraidos = procesar_lote_con_ia(archivos, cliente_input)
            
            if datos_extraidos:
                st.session_state['lote_ia'] = datos_extraidos
                st.session_state['archivos_temporales'] = archivos
                st.success("¡Lote procesado!")

with col2:
    st.subheader("📋 2. Conciliación y Exportación")
    
    if 'lote_ia' in st.session_state:
        lote = st.session_state['lote_ia']
        resumen = lote.get("resumen_lote", {})
        cheques = lote.get("cheques", [])
        razonamiento = lote.get("razonamiento_en_voz_alta", "Sin razonamiento previo.")
        
        with st.expander("🤔 Ver razonamiento interno de la IA"):
            st.info(razonamiento)
            
        total_ticket = resumen.get("total_declarado_ticket", 0)
        efectivo = resumen.get("efectivo_declarado", 0)
        suma_cheques = sum(c.get("monto", 0) for c in cheques)
        gran_total_calculado = efectivo + suma_cheques
        
        st.write("### 🚦 Semáforo S.I.C.E.")
        st.metric("Total Declarado en Ticket", f"${total_ticket:,.2f}")
        
        col_res1, col_res2 = st.columns(2)
        col_res1.metric("Efectivo Leído", f"${efectivo:,.2f}")
        col_res2.metric("Suma de Cheques", f"${suma_cheques:,.2f}")
        
        diferencia = round(total_ticket - gran_total_calculado, 2)
        if diferencia == 0:
            st.success("✅ **¡CUADRA PERFECTO!**")
        else:
            st.error(f"❌ **ERROR DE CUADRATURA:** Hay una diferencia de ${diferencia:,.2f}. (Verificá si leyó bien el efectivo del ticket)")
            
        st.write("---")
        st.write("**Grilla de Cheques (Editable):**")
        datos_editados = st.data_editor(cheques)
        
        # Bloque de Botones Finales
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("☁️ Guardar en Supabase"):
                with st.spinner("Subiendo datos..."):
                    try:
                        archivo_principal = st.session_state['archivos_temporales'][0]
                        timestamp = int(time.time())
                        nombre_archivo = f"lote_{timestamp}_{archivo_principal.name}"
                        
                        supabase.storage.from_("comprobantes").upload(
                            path=nombre_archivo,
                            file=archivo_principal.getvalue(),
                            file_options={"content-type": archivo_principal.type}
                        )
                        url_publica = supabase.storage.from_("comprobantes").get_public_url(nombre_archivo)
                        
                        for fila in datos_editados:
                            fila['archivo_url'] = url_publica
                            
                        supabase.table("cobranzas_pendientes").insert(datos_editados).execute()
                        st.success("¡Guardado exitoso!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
        
        with col_btn2:
            # Lógica para convertir los datos al formato Regente
            df_exportar = pd.DataFrame(datos_editados)
            if not df_exportar.empty:
                # Mapeamos a las columnas exactas de Regente
                df_regente = pd.DataFrame({
                    "Titular": df_exportar.get("razon_social_emisor", ""),
                    "Emision": df_exportar.get("fecha_emision", ""),
                    "Venc.": df_exportar.get("fecha_pago", ""),
                    "Nro": df_exportar.get("numero_identificador", ""),
                    "Bco.": df_exportar.get("codigo_banco", ""),
                    "NCta.": df_exportar.get("numero_cuenta", ""),
                    "Plaza": df_exportar.get("codigo_sucursal", ""),
                    "Monto": df_exportar.get("monto", 0.0)
                })
                
                csv_data = df_regente.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="⬇️ Descargar para Regente",
                    data=csv_data,
                    file_name=f"importacion_regente_{int(time.time())}.csv",
                    mime="text/csv",
                    type="primary"
                )