import streamlit as st
import json
import tempfile
import os
import time
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
st.title("🤖 Laboratorio IA - Motor de Lotes S.I.C.E.")
st.markdown("Subí el ticket del cajero junto con todas las fotos de los cheques. La IA ahora **pensará en voz alta** para mejorar la lectura de la letra manuscrita.")
st.markdown("---")

# ==========================================
# 3. MOTOR IA (GEMINI 2.5 PRO - Chain of Thought)
# ==========================================
def procesar_lote_con_ia(archivos_subidos, cliente_tag):
    archivos_gemini_creados = []
    rutas_temporales = []
    
    try:
        # 1. Guardar y subir a Gemini
        for archivo in archivos_subidos:
            extension = os.path.splitext(archivo.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
                tmp_file.write(archivo.getvalue())
                rutas_temporales.append(tmp_file.name)
            
            archivo_g = genai.upload_file(tmp_file.name)
            archivos_gemini_creados.append(archivo_g)

        # 2. Configurar el cerebro
        modelo = genai.GenerativeModel('gemini-2.5-pro')
        
        # 3. El Súper Prompt con Cadena de Pensamiento
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Analizá este lote: UN ticket S.I.C.E. y VARIAS fotos de cheques. Cliente: '{cliente_tag}'.
        
        PASO 1 (RAZONAMIENTO): Antes de extraer los datos finales, usá el campo 'razonamiento_en_voz_alta' para describir en texto libre lo que ves en cada cheque. Analizá en detalle la letra cursiva, los montos, las fechas y los CUITs. Si una letra o número no se entiende bien o es un garabato, escribí tus dudas y dejá constancia de que no es legible.
        
        PASO 2 (EXTRACCIÓN ESTRICTA): Una vez que termines de razonar, completá los datos. REGLA DE HIERRO: Si en tu razonamiento tuviste dudas sobre una fecha, CUIT o nombre manuscrito, DEBÉS dejar el campo vacío (""). NO inventes datos.
        
        Devolvé ÚNICAMENTE un objeto JSON con esta estructura exacta:
        {{
            "razonamiento_en_voz_alta": "Tu análisis exhaustivo y transcripción paso a paso de lo que ves, razonando cada garabato.",
            "resumen_lote": {{
                "total_declarado_ticket": numero_decimal,
                "efectivo_declarado": numero_decimal
            }},
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco",
                    "codigo_banco": "Código de 3 dígitos (ej: 014)",
                    "codigo_sucursal": "Código de 3 o 4 dígitos",
                    "numero_identificador": "Número del cheque",
                    "monto": numero_decimal,
                    "fecha_emision": "YYYY-MM-DD",
                    "fecha_pago": "YYYY-MM-DD",
                    "cuit_emisor": "CUIT con guiones",
                    "firma_destino": "Razón social o firmante",
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
    archivos = st.file_uploader("Subir Ticket S.I.C.E. y Cheques", type=['png', 'jpeg', 'jpg', 'pdf'], accept_multiple_files=True)

    if archivos and st.button("🧠 Auditar Lote Completo"):
        with st.spinner(f"Procesando y analizando caligrafía. Esto puede demorar unos 15 segundos..."):
            datos_extraidos = procesar_lote_con_ia(archivos, cliente_input)
            
            if datos_extraidos:
                st.session_state['lote_ia'] = datos_extraidos
                st.session_state['archivos_temporales'] = archivos
                st.success("¡Lote analizado!")

with col2:
    st.subheader("📋 2. Semáforo y Guardado")
    
    if 'lote_ia' in st.session_state:
        lote = st.session_state['lote_ia']
        resumen = lote.get("resumen_lote", {})
        cheques = lote.get("cheques", [])
        razonamiento = lote.get("razonamiento_en_voz_alta", "Sin razonamiento previo.")
        
        # Muestra el pensamiento de la IA
        with st.expander("🤔 Ver razonamiento de la IA (Clic para expandir)"):
            st.info(razonamiento)
            
        # Matemáticas de auditoría
        total_ticket = resumen.get("total_declarado_ticket", 0)
        efectivo = resumen.get("efectivo_declarado", 0)
        suma_cheques = sum(c.get("monto", 0) for c in cheques)
        gran_total_calculado = efectivo + suma_cheques
        
        st.write("### 🚦 Conciliación S.I.C.E.")
        st.metric("Total Declarado en Ticket", f"${total_ticket:,.2f}")
        
        col_res1, col_res2 = st.columns(2)
        col_res1.metric("Efectivo Extraído", f"${efectivo:,.2f}")
        col_res2.metric("Suma de Cheques (Leídos)", f"${suma_cheques:,.2f}")
        
        diferencia = round(total_ticket - gran_total_calculado, 2)
        
        if diferencia == 0:
            st.success("✅ **¡LOTE PERFECTO!** La suma de los cheques y el efectivo coincide exactamente con el ticket.")
        else:
            st.error(f"❌ **ERROR DE CUADRATURA:** Hay una diferencia de ${diferencia:,.2f}. Revisá la grilla abajo.")
            
        st.write("---")
        st.write("**Grilla de Cheques Extraídos:**")
        datos_editados = st.data_editor(cheques)
        
        if st.button("✅ Aprobar y Enviar a Supabase"):
            with st.spinner("Subiendo imágenes y guardando..."):
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
                        
                    respuesta = supabase.table("cobranzas_pendientes").insert(datos_editados).execute()
                    
                    st.success("¡Lote guardado en Supabase perfectamente!")
                    st.balloons()
                    del st.session_state['lote_ia']
                    
                except Exception as e:
                    st.error(f"Error al guardar: {e}")