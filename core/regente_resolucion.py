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
2. Si la cuenta no aparece, se busca por apellido en rgSujetoNg (que puede
   traer 0, 1 o varios resultados, ya que el apellido puede repetirse).
3. De esos resultados, se extrae el CUIT de cada uno (viene pegado en un
   campo de texto sin nombre propio) y se compara contra el CUIT real del
   cheque — la comparación es SIEMPRE por CUIT exacto, nunca por parecido
   de nombre.
4. Si ningún resultado coincide en CUIT -> emisor 100% nuevo: hay que crear
   el sujeto Y la cuenta.
5. Si coincide exactamente uno -> el sujeto ya existe (con otra cuenta):
   alcanza con darle de alta la cuenta nueva, sin tocar el sujeto.
6. Si coincidiera más de uno (no debería pasar) -> caso dudoso, se marca
   para revisión manual en el panel de auditoría.
"""
import re

from core.regente_client import buscar_cuenta_por_numero, buscar_sujetos_por_apellido


def _extraer_cuit_de_texto(texto):
    """
    Busca el patrón "CUIT" seguido de números dentro del campo de texto sin
    nombre propio que devuelve la búsqueda por apellido (aparece como
    "?column?" en la respuesta cruda de Regente). Devuelve el CUIT como
    string de solo dígitos, o None si no lo encuentra.
    """
    if not texto:
        return None
    coincidencia = re.search(r"CUIT\s*(\d{6,})", str(texto))
    return coincidencia.group(1) if coincidencia else None


def _obtener_apellido_para_busqueda(razon_social):
    """
    Toma la primera palabra de la razón social como "apellido" para la
    búsqueda de respaldo (ej: 'FOCHESATTO SILVIO JOSE' -> 'FOCHESATTO').
    Funciona bien para personas físicas. Para razones sociales de empresas
    (ej: 'TOURNE Y TOURNE S.A.') puede no ser un apellido real, pero sigue
    siendo un texto de búsqueda razonable.

    PENDIENTE DE VERIFICAR: si en la práctica esto da resultados pobres para
    empresas, se puede ajustar más adelante (probar con más palabras, o con
    la razón social completa).
    """
    texto = str(razon_social or "").strip()
    return texto.split(" ")[0] if texto else ""


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

    # Paso 2: la cuenta no existe. Buscar por apellido y comparar por CUIT.
    apellido = _obtener_apellido_para_busqueda(razon_social_cheque)
    if not apellido or not cuit_limpio:
        return {
            "accion": "revision_manual",
            "id_sujeto": None,
            "motivo": "Falta razón social o CUIT del emisor para poder buscar con seguridad.",
        }

    candidatos = buscar_sujetos_por_apellido(apellido)
    coincidencias = [
        c for c in candidatos
        if _extraer_cuit_de_texto(c.get("?column?")) == cuit_limpio
    ]

    if len(coincidencias) == 1:
        return {
            "accion": "crear_cuenta_para_existente",
            "id_sujeto": int(coincidencias[0]["id_sujeto"]),
            "motivo": (
                f"El sujeto ya existe en Regente (encontrado por CUIT {cuit_limpio} "
                f"entre los resultados de '{apellido}'), pero con otra cuenta. Hay "
                "que darle de alta la cuenta nueva."
            ),
        }

    if len(coincidencias) > 1:
        return {
            "accion": "revision_manual",
            "id_sujeto": None,
            "motivo": (
                f"Más de un sujeto con CUIT {cuit_limpio} entre los resultados de "
                f"'{apellido}' — caso inesperado, revisar a mano."
            ),
        }

    # Ninguna coincidencia: emisor 100% nuevo
    return {
        "accion": "crear_sujeto_y_cuenta",
        "id_sujeto": None,
        "motivo": (
            f"No se encontró ni la cuenta '{numero_cuenta}' ni el CUIT "
            f"{cuit_limpio} en Regente. Es un emisor nuevo."
        ),
    }
