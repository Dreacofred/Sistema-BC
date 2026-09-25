"""
core/semaforo.py

La regla del semáforo de cobranza, en un solo lugar.

EL COLOR SE CALCULA, NO SE GUARDA. Sale de los días de atraso de la factura
vencida más vieja del cliente, que Regente devuelve en el estado de cuenta. Al
ser una función del atraso, nunca queda desactualizado: no hay nada que
sincronizar ni ninguna marca que envejezca.

    Días de atraso    Color
    0 a 2             verde
    3 a 10            amarillo
    11 o más          rojo

    Sin deuda         sin semáforo (None)

Este archivo vive en core/ y no en el módulo de cuentas corrientes porque el
color se va a usar en varios lados, no solo en la pantalla de cobranza:
- el listado de clientes con facturas vencidas,
- el bloqueo de órdenes de carga a los clientes en rojo,
- el aviso al iniciar sesión en el portal para los clientes en amarillo.

Si la regla estuviera escrita adentro de una pantalla, el día que cambie un
umbral habría que acordarse de tocarla en tres lugares. Acá se toca una sola vez.

NO IMPORTA STREAMLIT NI NADA DE RED a propósito: es una regla de negocio pura,
para que la pueda usar tanto la app de Streamlit como el webhook de Flask sin
arrastrar dependencias.
"""
from datetime import date


# ==========================================
# 1. UMBRALES
# ==========================================
# Estos son los dos números que definen todo el semáforo. Están acá, juntos y
# solos, porque más adelante se van a administrar desde la aplicación (un
# usuario con permisos los va a poder cambiar sin tocar el código). Cuando eso
# pase, lo único que cambia es obtener_umbrales(): el resto del sistema sigue
# llamando a color_por_atraso() sin enterarse.
DIAS_HASTA_AMARILLO = 2   # hasta acá, inclusive, sigue verde
DIAS_HASTA_ROJO = 10      # hasta acá, inclusive, sigue amarillo

VERDE = "verde"
AMARILLO = "amarillo"
ROJO = "rojo"

COLORES = (VERDE, AMARILLO, ROJO)


def obtener_umbrales():
    """
    Devuelve los umbrales vigentes (en días de atraso).

    Hoy son constantes del código. Este es el punto de enganche para el día que
    se administren desde una tabla de configuración en Supabase: se cambia esta
    función y nada más.
    """
    return {"amarillo": DIAS_HASTA_AMARILLO, "rojo": DIAS_HASTA_ROJO}


# ==========================================
# 2. LA REGLA
# ==========================================
def color_por_atraso(dias_atraso):
    """
    Devuelve el color que corresponde a una cantidad de días de atraso.

    Ojo con los bordes, están confirmados así: 2 días de atraso TODAVÍA es
    verde, y 10 días TODAVÍA es amarillo. El cambio es cuando los supera.

    Un cliente con deuda pero sin nada vencido tiene 0 días de atraso, o sea
    verde: es el arranque de todo cliente con deuda.
    """
    dias = int(dias_atraso or 0)
    umbrales = obtener_umbrales()

    if dias > umbrales["rojo"]:
        return ROJO
    if dias > umbrales["amarillo"]:
        return AMARILLO
    return VERDE


def dias_atraso_de_deuda(deuda):
    """
    Días de atraso reales, calculados sobre el detalle de la deuda: el mayor
    atraso entre las filas que SUMAN deuda y todavía tienen saldo.

    Dos cuidados, los dos salen de casos reales:

    1. Las notas de crédito y los anticipos (signo_comp = -1) NO cuentan. Son
       plata a favor del cliente: una nota de crédito "vencida" hace 30 días no
       es una deuda atrasada. El cliente 693 tenía justamente eso, y arrastraba
       el atraso de la nota de crédito a la cuenta entera.
    2. Solo cuentan las filas con saldo pendiente.

    Esta es la fuente más precisa de las dos; la de abajo es para cuando solo
    se tiene el estado de cuenta.
    """
    if not deuda:
        return 0
    atrasos = [
        f.get("atraso") or 0
        for f in deuda.get("filas", [])
        if (f.get("signo") or 1) > 0 and (f.get("saldo") or 0) > 0
    ]
    return max(atrasos) if atrasos else 0


def color_de_deuda(deuda):
    """
    Color a partir del detalle de deuda que arma utils_regente.obtener_deuda().
    Es la forma preferida de calcularlo cuando se tiene el detalle.
    """
    if not deuda or (deuda.get("total") or 0) <= 0:
        return None
    return color_por_atraso(dias_atraso_de_deuda(deuda))


def dias_atraso_de_estado(estado):
    """
    Días de atraso a partir del estado de cuenta.

    OJO — VERIFICADO EL 25/09/2026 CON UN CASO REAL: el campo "dias" que
    devuelve Regente NO es confiable. El cliente 693 (GOMEZ GUSTAVO GABRIEL)
    tenía "dias" = 0 con una factura de $2.200.000 vencida hacía 16 días. El
    que sí viene bien es "peor_fecha" (el vencimiento impago más viejo), así
    que calculamos los días contra esa fecha y nos quedamos con el mayor de los
    dos valores.

    Esto importa sobre todo para el listado de clientes con facturas vencidas:
    ahí solo vamos a tener el estado de cuenta, sin el detalle de la deuda.
    """
    if not estado:
        return 0
    dias = int(estado.get("dias_atraso") or 0)
    peor = estado.get("peor_fecha")
    if peor:
        dias = max(dias, (date.today() - peor).days)
    return max(dias, 0)


def color_de_estado_cuenta(estado):
    """
    Devuelve el color a partir del estado de cuenta que arma
    utils_regente.obtener_estado_cuenta(), o None si el cliente no tiene deuda.

    Acepta None (que es lo que devuelve esa función cuando el cliente no tiene
    saldo) justamente para que quien la use no tenga que preguntar dos veces.
    """
    if not estado:
        return None
    # Solo tiene semáforo el que DEBE. Saldo 0 es un cliente al día, y saldo
    # negativo es un cliente con crédito a favor (una nota de crédito o un
    # anticipo): ninguno de los dos va a una lista de cobranza.
    if (estado.get("saldo_final") or 0) <= 0:
        return None
    return color_por_atraso(dias_atraso_de_estado(estado))


def esta_bloqueado(color):
    """
    Si un cliente en este color puede o no cargar una orden.

    PENDIENTE: el bloqueo de órdenes todavía no está implementado en ningún
    lado; esta función deja la decisión escrita en el mismo lugar que el color,
    para que cuando se implemente no se invente otra regla en paralelo.
    """
    return color == ROJO


def requiere_aviso(color):
    """Si al cliente hay que mostrarle un aviso al iniciar sesión en el portal."""
    return color == AMARILLO


# ==========================================
# 3. PRESENTACIÓN
# ==========================================
# Para que las tres pantallas que van a mostrar el semáforo usen exactamente los
# mismos colores y las mismas palabras.
ETIQUETAS = {
    VERDE: "Al día",
    AMARILLO: "Atrasado",
    ROJO: "Urgente",
}

HEX = {
    VERDE: "#2E7D32",
    AMARILLO: "#F9A825",
    ROJO: "#C8102E",   # el rojo de la marca: acá sí significa alarma
}

# Color del texto ENCIMA de cada color de fondo. El amarillo es claro: texto
# blanco sobre #F9A825 da un contraste de 1,8:1, que no pasa WCAG AA y se
# vuelve ilegible al sol, que es donde se usa esto. Va texto oscuro.
TEXTO = {
    VERDE: "#FFFFFF",
    AMARILLO: "#3A3A3A",
    ROJO: "#FFFFFF",
}

# Para ordenar listados: primero lo más urgente.
ORDEN = {ROJO: 0, AMARILLO: 1, VERDE: 2}


def etiqueta(color):
    return ETIQUETAS.get(color, "Sin deuda")


def hex_color(color):
    return HEX.get(color, "#6B7280")


def hex_texto(color):
    """El color de texto que se lee bien sobre hex_color(color)."""
    return TEXTO.get(color, "#FFFFFF")


def orden(color):
    return ORDEN.get(color, 99)


def descripcion_regla():
    """Una línea explicando la regla vigente, para mostrar en pantalla y que el
    usuario sepa por qué un cliente está de cada color."""
    u = obtener_umbrales()
    return (
        f"Verde hasta {u['amarillo']} días de atraso · "
        f"Amarillo de {u['amarillo'] + 1} a {u['rojo']} · "
        f"Rojo a partir de {u['rojo'] + 1}"
    )
