"""
modulos/cuenta_corriente.py

Contenedor de la pestaña "Cuentas Corrientes": el selector de consultas, y nada
más. El contenido de cada consulta vive en su propio archivo (modulos/cc_*.py),
y este módulo solo decide cuál se muestra.

Se llama desde lector.py así: modulo_cuenta_corriente.mostrar(supabase)

POR QUÉ ESTÁ ARMADO ASÍ
-----------------------
La integración con Regente no existe para repetir consultas que el ERP ya
tiene, sino para las que no da: vistas cruzadas entre muchos clientes, para
decidir a quién reclamarle. Esas consultas van a ir llegando de a una, a medida
que Regente habilite los endpoints que faltan, así que la pantalla tenía que
ser un contenedor donde enchufarlas sin rediseñar nada cada vez.

De ahí las tres decisiones de este archivo:

1. UN REGISTRO DE CONSULTAS (CONSULTAS, más abajo) en vez de una cadena de
   "if". Cada consulta declara su título, su función y qué está esperando. Las
   que todavía dependen de Regente figuran igual, marcadas como pendientes y
   diciendo qué les falta: así la pantalla documenta sola en qué está trabado
   el proyecto, y sumar una consulta nueva es agregar una fila acá.

2. st.segmented_control Y NO st.tabs. Las pestañas de Streamlit no se pueden
   cambiar desde el código, y el movimiento central de este módulo es hacer
   clic en un deudor de un listado y caer en su ficha. Con el selector guardado
   en session_state eso es abrir_ficha(); con st.tabs no se podría.

3. LOS FILTROS COMUNES TODAVÍA NO ESTÁN. Sucursal, vendedor y rango de montos
   van a vivir acá, encima de la consulta elegida, porque sirven para las tres
   consultas de deuda. No se dibujan todavía porque la única consulta
   disponible es la ficha de un cliente puntual, donde no filtran nada: serían
   controles que no hacen nada. Entran junto con el primer listado.
"""
import streamlit as st

from modulos import cc_ficha_cliente


COLOR_ROJO = "#C8102E"
COLOR_GRIS_SUAVE = "#6B7280"

# El CSS de lector.py pinta los botones de la marca con el selector
# ".stButton>button", que NO alcanza a los botones de formulario: Streamlit los
# renderiza bajo ".stFormSubmitButton". Sin esta regla, el botón "Buscar" del
# buscador sale blanco con borde gris, desentonando con el resto de la app.
# PARA LA SEGUNDA TANDA: esto va a lector.py (o mejor, un primaryColor en
# .streamlit/config.toml), para que valga en todos los formularios de la app
# —Gestión de Clientes tiene hoy el mismo problema— y no quede repetido acá.
CSS_BOTON_FORMULARIO = f"""
<style>
    .stFormSubmitButton > button {{
        background-color: {COLOR_ROJO}; color: white; border-radius: 8px;
        font-weight: 600; height: 2.8em; border: none; width: 100%;
        transition: all 0.3s;
    }}
    .stFormSubmitButton > button:hover {{
        background-color: #900b20; color: white;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }}
</style>
"""


# ==========================================
# 1. EL REGISTRO DE CONSULTAS
# ==========================================
# "vista" es la función que dibuja la consulta y recibe (supabase).
# "espera" es lo que falta para poder implementarla; mientras tenga algo, la
# consulta aparece en el selector pero todavía no se puede usar.
CONSULTAS = [
    {
        "clave": "vencidas",
        "titulo": "Vencidas",
        "descripcion": "Clientes con facturas vencidas, ordenados por atraso y deuda.",
        "vista": None,
        "espera": (
            "Necesita que GET /rgComprobanteNg/estado_cuenta acepte consultas "
            "<b>sin id_sujeto</b>, para traer el listado de todos los clientes de "
            "una. Hoy exige el cliente, así que solo se puede preguntar de a uno "
            "y un ranking saldría de miles de consultas. Pedido a Regente el "
            "25/09/2026."
        ),
    },
    {
        "clave": "semaforo",
        "titulo": "Mis urgentes",
        "descripcion": "La lista de urgentes que arma cada vendedor sobre sus clientes con deuda.",
        "vista": None,
        "espera": (
            "La base y la regla ya están listas (tabla lista_urgentes y "
            "core/semaforo.py), pero para armar la lista hay que poder ver "
            "primero todos los clientes con deuda: depende de lo mismo que la "
            "consulta <b>Vencidas</b>. Mientras tanto, el semáforo de un cliente "
            "puntual se ve en su ficha."
        ),
    },
    {
        "clave": "sin_cargar",
        "titulo": "Sin cargar",
        "descripcion": "Clientes que no cargaron en un rango de fechas.",
        "vista": None,
        "espera": (
            "Necesita que GET /rgComprobanteNg/listado acepte consultas <b>sin "
            "id_sujeto</b>, para saber quién compró en un período y quién no. No se "
            "puede resolver con el estado de cuenta, porque su fecha de último "
            "movimiento solo viene para clientes con saldo. Pedido a Regente el "
            "25/09/2026."
        ),
    },
    {
        "clave": "ficha",
        "titulo": "Ficha de cliente",
        "descripcion": "El detalle de la cuenta corriente de un cliente.",
        "vista": cc_ficha_cliente.mostrar,
        "espera": None,
    },
    {
        "clave": "avisos",
        "titulo": "Avisos",
        "descripcion": "Avisos programados de cobranza.",
        "vista": None,
        "espera": (
            "Falta definir el canal: que avise la plataforma, o que el aviso se "
            "cargue como un item en Mi Agenda, que vive en esta misma base de "
            "Supabase (tabla agenda_items)."
        ),
    },
]

CONSULTA_POR_DEFECTO = "ficha"

_POR_TITULO = {c["titulo"]: c for c in CONSULTAS}
_POR_CLAVE = {c["clave"]: c for c in CONSULTAS}


# ==========================================
# 2. NAVEGACIÓN ENTRE CONSULTAS
# ==========================================
def abrir_ficha(id_sujeto, nombre):
    """
    Salta a la ficha de un cliente. Es lo que van a llamar los listados cuando
    el usuario haga clic en una fila: deja el cliente elegido y cambia la
    consulta activa.

    Quien la llama tiene que hacer st.rerun() después, para que la pantalla se
    redibuje ya en la ficha.
    """
    cc_ficha_cliente.inicializar_estado()
    cc_ficha_cliente.elegir_cliente(id_sujeto, nombre)
    st.session_state.cc_consulta = _POR_CLAVE["ficha"]["titulo"]


def _mostrar_pendiente(consulta):
    """
    Lo que se ve al elegir una consulta que todavía no se puede implementar.
    Decir qué falta es más útil que esconderla: así queda a la vista en qué
    está trabado el módulo, sin tener que abrir el código.
    """
    st.info(f"**{consulta['descripcion']}**\n\nEsta consulta todavía no está disponible.")
    st.markdown(
        f'<div style="color:{COLOR_GRIS_SUAVE};font-size:14px;">'
        f'<b>Qué falta:</b> {consulta["espera"]}</div>',
        unsafe_allow_html=True,
    )


# ==========================================
# 3. ENTRADA DEL MÓDULO
# ==========================================
def mostrar(supabase):
    st.title("Cuentas Corrientes")
    st.markdown(
        f'<p style="color:{COLOR_GRIS_SUAVE};font-size:16px;max-width:60ch;">'
        'Consulta en vivo de la cuenta corriente de clientes en Regente. '
        'Es solo lectura: desde acá no se modifica nada en el sistema de gestión.'
        '</p>',
        unsafe_allow_html=True,
    )
    st.markdown(CSS_BOTON_FORMULARIO, unsafe_allow_html=True)

    st.session_state.setdefault("cc_consulta", _POR_CLAVE[CONSULTA_POR_DEFECTO]["titulo"])

    titulo = st.segmented_control(
        "Consulta",
        options=[c["titulo"] for c in CONSULTAS],
        key="cc_consulta",
        label_visibility="collapsed",
    )

    # segmented_control devuelve None si el usuario deselecciona la opción activa.
    consulta = _POR_TITULO.get(titulo) or _POR_CLAVE[CONSULTA_POR_DEFECTO]

    st.markdown("")
    if consulta["espera"]:
        _mostrar_pendiente(consulta)
        return

    consulta["vista"](supabase)
