"""
core/validaciones.py

Validaciones de datos que la IA extrae de los comprobantes, antes de
guardarlos. La idea es simple: un dato que sabemos que está mal es peor que
un dato vacío, porque el vacío se ve y el equivocado no.

El enfoque está tomado del proyecto sistema-financiero-bc, que lee los mismos
comprobantes y llegó a esto después de encontrarse 18 CUIT mal leídos en su
base.
"""
import re


def _digito_verificador_correcto(primeros_diez: str) -> int:
    """
    Calcula el dígito verificador que le corresponde a un CUIT, a partir de
    sus primeros diez dígitos.

    El algoritmo es el estándar de AFIP: se multiplica cada dígito por su
    peso (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), se suman los productos, se saca el
    resto de dividir por 11 y se lo resta de 11. Si da 11 el dígito es 0, y
    si da 10 es 9.
    """
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(d) * p for d, p in zip(primeros_diez, pesos))
    resultado = 11 - (suma % 11)
    if resultado == 11:
        return 0
    if resultado == 10:
        return 9
    return resultado


def limpiar_cuit(cuit):
    """
    Devuelve el CUIT como 11 dígitos seguidos, o None si no es válido.

    Valida dos cosas:
      1. Que tenga exactamente 11 dígitos (ignora guiones, puntos y espacios).
      2. Que el último dígito, el de control, sea el que corresponde.

    El segundo control es el que importa: el CUIT trae ese dígito justamente
    para detectar cuando se leyó mal. Y acá pesa más que en otros lados,
    porque **el emisor de un cheque se busca en Regente POR CUIT**
    (`core/regente_resolucion.py`). Un CUIT con un dígito cambiado no es un
    dato feo: es una decisión equivocada. O no encuentra a una empresa que ya
    existe y se propone crearla de nuevo, o —peor— coincide con el CUIT de
    otra empresa distinta.

    Por eso preferimos guardar el comprobante SIN CUIT y que el auditor lo
    complete mirando el original, antes que guardar uno que sabemos que está
    mal pero parece válido.

    Devuelve None también si el CUIT viene vacío o en None, así el llamador
    no tiene que distinguir "no vino" de "vino mal": en los dos casos hay que
    dejar el campo vacío y que lo revise una persona.
    """
    if not cuit:
        return None
    solo_digitos = re.sub(r"\D", "", str(cuit))
    if len(solo_digitos) != 11:
        return None
    if int(solo_digitos[10]) != _digito_verificador_correcto(solo_digitos[:10]):
        return None
    return solo_digitos
