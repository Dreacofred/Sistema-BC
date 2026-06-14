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
st.markdown("Subí el ticket del cajero junto con todas las fotos de los cheques. La IA de **Gemini 2.5 Pro** armará la conciliación completa.")
st.markdown("---")

# ==========================================
# 3. MOTOR IA (GEMINI 2.5 PRO Lotes)
# ==========================================
def procesar_lote_con_ia(archivos_subidos, cliente_tag):
    archivos_gemini_creados = []
    rutas_temporales = []
    
    try:
        # 1. Guardar temporalmente y subir TODAS las fotos a Gemini
        for archivo in archivos_subidos:
            extension = os.path.splitext(archivo.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
                tmp_file.write(archivo.getvalue())
                rutas_temporales.append(tmp_file.name)
            
            archivo_g = genai.upload_file(tmp_file.name)
            archivos_gemini_creados.append(archivo_g)

        # 2. Configurar el cerebro
        modelo = genai.GenerativeModel('gemini-2.5-pro')
        
        # 3. El Súper Prompt de Conciliación con Regla Estricta
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Estás analizando un lote de imágenes que contiene UN ticket de depósito S.I.C.E. y VARIAS fotos de cheques físicos asociados a ese depósito. El cliente asociado es '{cliente_tag}'.
        
        REGLA DE HIERRO PARA TEXTO MANUSCRITO: Si la letra cursiva, las fechas manuscritas, los nombres o los CUITs son borrosos, confusos o tenés la más mínima duda sobre un dígito o letra, DEBÉS dejar el campo completamente vacío (""). BAJO NINGUNA CIRCUNSTANCIA intentes adivinar, deducir o inventar fechas, CUITs o firmas. Priorizamos campos vacíos antes que datos erróneos.
        
        Devolvé ÚNICAMENTE un objeto JSON con esta estructura exacta:
        {{
            "resumen_lote": {{
                "total_declarado_ticket": numero_decimal,
                "efectivo_declarado": numero_decimal
            }},
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco (ej: Banco Provincia)",
                    "codigo_banco": "Código de 3 dígitos (ej: 014)",
                    "codigo_sucursal": "Código de 3 o 4 dígitos (ej: 1842)",
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
        Importante: Extraé el código del banco y la sucursal de la banda magnética o del recuadro superior derecho del cheque (ej: en 014-058-1842, banco es 014, sucursal es 1842). Los montos deben ser numéricos (sin el símbolo $).
        """
        
        # Mandamos la lista de imágenes junto con el texto de instrucciones
        contenido_a_procesar = archivos_gemini_creados + [prompt]
        respuesta = modelo.generate_content(contenido_a_procesar)
        
        # Limpieza de temporales (Nube de Google y Disco local)
        for g_file in archivos_gemini_creados:
            genai.delete_file(g_file.name)
        for tmp_path in rutas_temporales:
            os.remove(tmp_path)
            
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_json)

    except Exception as e:
        st.error(f"Error en el Motor de Lotes: {e}")
        # Limpieza de emergencia
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
        with st.spinner(f"Procesando {len(archivos)} archivos. Esto puede demorar unos segundos..."):
            datos_extraidos = procesar_lote_con_ia(archivos, cliente_input)
            
            if datos_extraidos:
                st.session_state['lote_ia'] = datos_extraidos
                st.session_state['archivos_temporales'] = archivos
                st.success("¡Lote procesado exitosamente!")

with col2:
    st.subheader("📋 2. Semáforo y Guardado")
    
    if 'lote_ia' in st.session_state:
        lote = st.session_state['lote_ia']
        resumen = lote.get("resumen_lote", {})
        cheques = lote.get("cheques", [])
        
        # Matemáticas de auditoría
        total_ticket = resumen.get("total_declarado_ticket", 0)
        efectivo = resumen.get("efectivo_declarado", 0)
        suma_cheques = sum(c.get("monto", 0) for c in cheques)
        gran_total_calculado = efectivo + suma_cheques
        
        # El Semáforo Visual
        st.write("### 🚦 Conciliación S.I.C.E.")
        st.metric("Total Declarado en Ticket", f"${total_ticket:,.2f}")
        
        col_res1, col_res2 = st.columns(2)
        col_res1.metric("Efectivo Extraído", f"${efectivo:,.2f}")
        col_res2.metric("Suma de Cheques (Leídos)", f"${suma_cheques:,.2f}")
        
        diferencia = round(total_ticket - gran_total_calculado, 2)
        
        if diferencia == 0:
            st.success("✅ **¡LOTE PERFECTO!** La suma de los cheques y el efectivo coincide exactamente con el ticket.")
        else:
            st.error(f"❌ **ERROR DE CUADRATURA:** Hay una diferencia de ${diferencia:,.2f}. Revisá la grilla de cheques abajo.")
            
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