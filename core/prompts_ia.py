"""
core/prompts_ia.py

Acá viven los prompts que se le mandan a Gemini para leer cheques.
Antes estaba escrito adentro de utils_bcra.py; ahora vive acá para que,
si en el futuro otro archivo necesita el mismo prompt, lo importe de
este lugar en vez de tenerlo copiado y pegado.
"""

PROMPT_LECTURA_CHEQUES = """
Actúa como un auditor senior de BC Combustibles. Analiza esta foto que contiene un lote de cheques físicos.

REGLAS DE ORO (Aislamiento de Datos):
1. Analiza los cheques visualmente de arriba hacia abajo.
2. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a". Ignora ese nombre gigante.
3. Ve siempre a la parte INFERIOR del cheque (junto a la firma o el logo del banco).
4. Extrae de ahí el CUIT (11 dígitos, suelen empezar con 20, 23, 27, 30) y la Razón Social del EMISOR.
5. Busca el NÚMERO DEL CHEQUE. Generalmente está en la esquina superior derecha o en la serie de números de la banda inferior.

ESTRUCTURA DE RESPUESTA OBLIGATORIA:
Devuelve ÚNICAMENTE un JSON puro (sin formato markdown) que sea una LISTA de objetos, uno por cada cheque:
[
    {
        "id": 1,
        "numero_cheque": "84512356",
        "emisor": "RAZON SOCIAL 1",
        "cuit": "20123456789"
    }
]

Si un dato no es legible con un 100% de seguridad, devuelve "ERROR_LECTURA" en ese campo específico.
"""
