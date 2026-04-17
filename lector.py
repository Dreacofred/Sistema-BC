import streamlit as st
from google import genai
from pypdf import PdfReader

# --- CONFIGURACIÓN VISUAL DE LA PÁGINA ---
st.set_page_config(page_title="Lector de Facturas", layout="centered")
st.title("📄 Lector Inteligente de Facturas AFIP")
st.write("Subí la factura en PDF para extraer los datos automáticamente en formato Regente.")

# --- INTERFAZ: CAJÓN PARA SUBIR ARCHIVO ---
archivo_subido = st.file_uploader("Arrastrá tu PDF acá o hacé clic para buscarlo", type=["pdf"])

# Si el usuario subió un archivo, mostramos el botón
if archivo_subido is not None:
    if st.button("🚀 Extraer Datos", use_container_width=True):
        
        with st.spinner("Analizando con Inteligencia Artificial... (puede demorar unos segundos)"):
            try:
                lector = PdfReader(archivo_subido)
                texto_crudo = lector.pages[0].extract_text()

                # --- LA CAJA FUERTE ---
                # El sistema va a buscar tu clave a las opciones secretas de la nube
                cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                orden = f"""
                Sos un administrador contable experto de Argentina. Analizá el siguiente texto de una factura de AFIP.

                REGLAS:
                1. El "Proveedor" es el emisor.
                2. El "Cliente" es BC COMBUSTIBLES S.A.
                3. NO uses el CUIT 30707837213 para el proveedor.

                ⚠️ INSTRUCCIÓN CRÍTICA:
                Devolveme el resultado EXCLUSIVAMENTE en formato informático JSON, usando exactamente esta estructura:
                {{
                  "proveedor_nombre": "...",
                  "proveedor_cuit": "...",
                  "numero_comprobante": "...",
                  "fecha_emision": "...",
                  "importe_total": 0.0,
                  "articulos": [
                    {{
                      "nombre_producto": "...",
                      "cantidad": 0,
                      "precio_unitario": 0.0,
                      "subtotal": 0.0
                    }}
                  ]
                }}

                Texto de la factura:
                {texto_crudo}
                """

                respuesta = cliente.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=orden
                )

                st.success("¡Datos extraídos y empaquetados con éxito!")
                st.code(respuesta.text, language="json")

            except Exception as e:
                st.error(f"Ocurrió un error en la lectura: {e}")