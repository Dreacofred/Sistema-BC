"""
core/cuentas_propias.py

Resuelve a qué cuenta/banco propio de BC Combustibles corresponde una
transferencia, comparando los datos de destino que extrajo la IA
(cuenta_destino, cbu_cvu_destino, alias_destino) contra la tabla
`cuentas_propias` de Supabase.

Orden de prioridad de búsqueda (confirmado con Diego, 31/08/2026):
1. Número de cuenta.
2. Si no matchea, CBU/CVU.
3. Si no matchea, alias.

Este archivo NO llama a ninguna API externa — solo consulta la propia
tabla de Supabase, ya cargada con las cuentas reales de BC.
"""


def _solo_digitos(texto):
    """Deja solo los dígitos de un texto (saca guiones, barras, espacios)."""
    return "".join(c for c in str(texto or "") if c.isdigit())


def resolver_banco_destino(supabase, cuenta_destino=None, cbu_cvu_destino=None, alias_destino=None):
    """
    Busca en cuentas_propias una coincidencia para los datos de destino de
    una transferencia. Devuelve el registro completo (dict, con empresa,
    banco, codigo_banco, cbu_cvu, numero_cuenta, alias) si encuentra una
    coincidencia, o None si no encuentra nada.

    La comparación de cuenta y CBU/CVU se hace solo por dígitos (ignora
    guiones, barras y espacios), para no fallar por diferencias de formato
    entre lo que extrae la IA y cómo está guardado el dato de referencia.
    El alias se compara sin importar mayúsculas/minúsculas.
    """
    respuesta = supabase.table("cuentas_propias").select("*").eq("activa", True).execute()
    cuentas = respuesta.data or []

    cuenta_buscada = _solo_digitos(cuenta_destino)
    if cuenta_buscada:
        for cuenta in cuentas:
            if _solo_digitos(cuenta.get("numero_cuenta")) == cuenta_buscada:
                return cuenta

    cbu_buscado = _solo_digitos(cbu_cvu_destino)
    if cbu_buscado:
        for cuenta in cuentas:
            if _solo_digitos(cuenta.get("cbu_cvu")) == cbu_buscado:
                return cuenta

    alias_buscado = str(alias_destino or "").strip().lower()
    if alias_buscado:
        for cuenta in cuentas:
            if str(cuenta.get("alias") or "").strip().lower() == alias_buscado:
                return cuenta

    return None
