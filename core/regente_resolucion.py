"""
core/regente_resolucion.py

Resuelve el emisor de un comprobante contra Regente.

A diferencia de core/regente_mapeo.py (que es pura traducción de datos, sin
tocar ninguna API), este módulo SÍ hace consultas reales de LECTURA (GET)
contra Regente. Nunca escribe nada (ningún POST) — decide qué habría que
hacer, para que una etapa posterior (con el OK explícito de Diego) sea la
que efectivamente cree algo.

Reglas de negocio confirmadas con Diego (28/08/2026):
1. Se busca primero por número de cuenta (rgSujetoCuentaNg). Si aparece una
   coincidencia exacta (mismo número de cuenta, mismo banco), ya tenemos el
   id_sujeto — no hace falta crear nada.
2. Si la cuenta no aparece, se busca el sujeto por CUIT. La comparación es
   SIEMPRE por CUIT exacto, nunca por parecido de nombre.
3. Si no aparece ningún sujeto con ese CUIT -> emisor 100% nuevo: hay que
   crear el sujeto Y la cuenta.
4. Si aparece exactamente uno -> el sujeto ya existe (con otra cuenta):
   alcanza con darle de alta la cuenta nueva, sin tocar el sujeto.
5. Si apareciera más de uno (no debería pasar) -> caso dudoso, se marca
   para revisión manual en el panel de auditoría.

HISTORIA DEL PASO 2 (corregido el 28/09/2026):
Cuando se escribió este módulo, la API de Regente no sabía buscar por CUIT,
así que el paso 2 daba un rodeo: buscaba por la primera palabra de la razón
social y después sacaba el CUIT de cada candidato con una expresión regular
aplicada a un campo de texto concatenado. Ese campo se llamaba "?column?" y
Regente lo renombró a `detalle_adic`, con lo cual la regex dejó de encontrar
nada: el CUIT salía siempre vacío, la comparación nunca coincidía y **todo
emisor que ya existiera en Regente se clasificaba igual como nuevo**.

Se reemplazó por GET /rgSujetoNg/buscar?criterio=D:{cuit}, que Damián liberó
el 10/09/2026 y resuelve en una sola consulta, con el CUIT en su propio campo
`doc`. No se parcheó el nombre del campo viejo a propósito: todo el rodeo
existía nada más que porque no se podía buscar por CUIT.

Ojo al leer estadísticas viejas de la pantalla de auditoría: mientras el bug
estuvo vivo, mostró el 100% de los emisores como nuevos. La estimación de que
"alrededor de la mitad" de los cheques son de emisores desconocidos salió de
ahí, así que hay que volver a medirla ahora que esto funciona.
"""
from core.regente_client import buscar_cuenta_por_numero, buscar_sujetos_por_cuit


def resolver_emisor(cuit_cheque, razon_social_cheque, numero_cuenta, id_adm):
    """
    Decide qué hacer con el emisor de un comprobante, consultando Regente
    en vivo. NO crea ni modifica nada — solo consulta y devuelve una
    decisión para que una etapa posterior actúe.

    Parámetros: los datos ya extraídos del cheque (cuit_emisor,
    razon_social_emisor, numero_cuenta, y el id_adm ya resuelto del banco).

    Devuelve un diccionario:
    {
        "accion": "usar_existente" | "crear_cuenta_para_existente"
                  | "crear_sujeto_y_cuenta" | "revision_manual",
        "id_sujeto": <int o None>,
        "motivo": "<texto explicando la decisión, para logs y auditoría>",
    }
    """
    cuit_limpio = "".join(c for c in str(cuit_cheque or "") if c.isdigit())

    # Paso 1: buscar por número de cuenta (coincidencia exacta, mismo banco)
    cuentas_encontradas = buscar_cuenta_por_numero(numero_cuenta, id_adm_esperado=id_adm)

    if len(cuentas_encontradas) == 1:
        return {
            "accion": "usar_existente",
            "id_sujeto": int(cuentas_encontradas[0]["id_sujeto"]),
            "motivo": f"La cuenta '{numero_cuenta}' ya está registrada en Regente.",
        }

    if len(cuentas_encontradas) > 1:
        return {
            "accion": "revision_manual",
            "id_sujeto": None,
            "motivo": (
                f"La cuenta '{numero_cuenta}' devolvió más de un resultado en "
                "rgSujetoCuentaNg — caso inesperado, revisar a mano."
            ),
        }

    # Paso 2: la cuenta no existe. Buscar el sujeto por CUIT exacto.
    if not cuit_limpio:
        return {
            "accion": "revision_manual",
            "id_sujeto": None,
            "motivo": (
                "El comprobante no trae CUIT del emisor, que es el único dato por "
                "el que se puede identificar un sujeto con seguridad. Revisar a mano."
            ),
        }

    coincidencias = buscar_sujetos_por_cuit(cuit_limpio)

    if len(coincidencias) == 1:
        encontrado = coincidencias[0]
        return {
            "accion": "crear_cuenta_para_existente",
            "id_sujeto": int(encontrado["id_sujeto"]),
            "motivo": (
                f"El sujeto ya existe en Regente por CUIT {cuit_limpio} "
                f"('{encontrado.get('sujeto')}'), pero con otra cuenta. Hay que "
                "darle de alta la cuenta nueva."
            ),
        }

    if len(coincidencias) > 1:
        nombres = ", ".join(str(c.get("sujeto")) for c in coincidencias)
        return {
            "accion": "revision_manual",
            "id_sujeto": None,
            "motivo": (
                f"Más de un sujeto en Regente con el CUIT {cuit_limpio} "
                f"({nombres}) — caso inesperado, revisar a mano."
            ),
        }

    # Ninguna coincidencia: emisor 100% nuevo
    return {
        "accion": "crear_sujeto_y_cuenta",
        "id_sujeto": None,
        "motivo": (
            f"No se encontró ni la cuenta '{numero_cuenta}' ni el CUIT "
            f"{cuit_limpio} en Regente. '{razon_social_cheque}' es un emisor nuevo."
        ),
    }
