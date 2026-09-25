"""
scripts/preview_cuenta_corriente.py

Banco de pruebas para ver el módulo de Cuentas Corrientes sin levantar la app
entera. Se corre desde la raíz del repositorio:

    streamlit run scripts/preview_cuenta_corriente.py

PARA QUÉ EXISTE
---------------
`lector.py` pide siete secrets apenas arranca (`SUPABASE_URL`, `SUPABASE_KEY`,
`ANTHROPIC_API_KEY`, `SCRAPEOPS_API_KEY` y los tres de Regente), así que no se
puede levantar en una máquina que solo tenga cargadas las credenciales de
Regente. Este script monta únicamente la pantalla de Cuentas Corrientes, que es
lo único que necesita esas tres, y le aplica el mismo CSS que la app real para
que lo que se ve acá se parezca a lo que se va a ver en producción.

NO ES PARTE DE LA APLICACIÓN. No se despliega, no lo importa nadie y no tiene
que crecer con lógica propia: si una prueba necesita algo más, va en el módulo.

QUÉ NO SE PUEDE PROBAR ACÁ
--------------------------
Pasa `supabase=None`, así que la búsqueda por CUIT —la única parte del módulo
que consulta Supabase— va a mostrar siempre su mensaje de "no encontrado". La
búsqueda por código y por razón social, que van contra Regente, funcionan igual
que en producción.

Requiere `.streamlit/secrets.toml` con REGENTE_API_URL, REGENTE_API_USUARIO y
REGENTE_API_TOKEN (ese archivo está en .gitignore y no se sube nunca).
"""
import sys
from pathlib import Path

import streamlit as st

# Streamlit agrega al path la carpeta del script (scripts/), no la raíz del
# repositorio, así que los imports del proyecto no resolverían. Se agrega la
# raíz a mano, calculada desde este archivo para que no dependa de dónde se
# ejecute.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from modulos import cuenta_corriente as modulo_cuenta_corriente  # noqa: E402

# Los mismos colores que define lector.py.
COLOR_ROJO = "#C8102E"
COLOR_GRIS_BC = "#3A3A3A"

st.set_page_config(
    page_title="BC - Cuentas Corrientes (prueba)",
    page_icon="⛽",
    layout="wide",
)

# Copia del bloque de estilos de lector.py, recortado a lo que afecta a esta
# pantalla. Si en lector.py cambia la identidad visual, acá hay que reflejarlo
# o el banco de pruebas deja de representar lo que se ve en producción.
st.markdown(f"""
    <style>
        .stApp {{ background-color: #f4f6f9 !important; }}
        h1, h2, h3 {{
            color: {COLOR_ROJO} !important;
            font-family: 'Montserrat', sans-serif;
            font-weight: 700;
        }}
        .stButton>button {{
            background-color: {COLOR_ROJO}; color: white; border-radius: 8px;
            font-weight: 600; height: 2.8em; border: none; width: 100%;
            transition: all 0.3s;
        }}
        .stButton>button:hover {{
            background-color: #900b20;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        [data-testid="stHeader"] {{ background-color: {COLOR_GRIS_BC} !important; }}
        div[data-testid="stMetricValue"] {{ color: {COLOR_ROJO} !important; }}
        .tarjeta-pro {{
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0; margin-bottom: 20px;
        }}
    </style>
""", unsafe_allow_html=True)

modulo_cuenta_corriente.mostrar(supabase=None)
