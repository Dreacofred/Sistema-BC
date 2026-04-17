import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image  # <-- LA NUEVA HERRAMIENTA PARA FOTOS

# --- CONFIGURACIÓN VISUAL DE LA PÁGINA ---
st.set_page_config(page_title="Lector de Facturas", layout="centered")
st.title("📄 Lector Inteligente de Facturas AFIP")
st.write("Subí la factura en PDF o una FOTO clara para extraer los datos.")

# --- INTERFAZ: AHORA ACEPTA FOTOS ---
archivo_subido = st.file_uploader("Arrastrá tu PDF o Foto acá", type=["pdf", "png", "jpg", "jpeg"])

if archivo_subido is not None:
    if st.button("🚀 Extraer Datos", use_container_width=True):
        
        with st.spinner("Analizando con Inteligencia Artificial... (puede demorar unos segundos)"):
            try:
                # --- LA CAJA FUERTE ---
                cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                # --- EL DESVÍO INTELIGENTE: ¿Es PDF o Foto? ---
                if archivo_subido.name.lower().endswith('.pdf'):
                    lector = PdfReader(archivo_subido)
                    material_para_ia = lector.pages[0].extract_text()
                else:
                    # ES UNA FOTO: La abrimos para que la IA la "vea"
                    material_para_ia = Image.open(archivo_subido)

                orden = """
                Sos un administrador contable experto de Argentina. Analizá esta factura de AFIP.

                REGLAS:
                1. El "Proveedor" es el emisor.
                2. El "Cliente" es BC COMBUSTIBLES S.A.
                3. NO uses el CUIT 30707837213 para el proveedor.

                ⚠️ INSTRUCCIÓN CRÍTICA:
                Devolveme el resultado EXCLUSIVAMENTE en formato informático JSON, usando exactamente esta estructura:
                {
                  "proveedor_nombre": "...",
                  "proveedor_cuit": "...",
                  "numero_comprobante": "...",
                  "fecha_emision": "...",
                  "importe_total": 0.0,
                  "articulos": [
                    {
                      "nombre_producto": "...",
                      "cantidad": 0,
                      "precio_unitario": 0.0,
                      "subtotal": 0.0
                    }
                  ]
                }
                """

                # Le mandamos a la IA la orden Y el material (texto del pdf o la foto cruda)
                respuesta = cliente.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[orden, material_para_ia]
                )

                st.success("¡Datos extraídos y empaquetados con éxito!")
                st.code(respuesta.text, language="json")

            except Exception as e:
                st.error(f"Ocurrió un error: {e}")
