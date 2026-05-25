import os
import json
import re

from models import (
    ClasificacionPreguntaProceso,
    DatosContacto,
    DescripcionProblema,
    ClasificacionTema,
    SDK_DISPONIBLE,
    cargar_variables_env
)

if SDK_DISPONIBLE:
    from google import genai
    from google.genai import types

def es_pregunta_especifica_de_procesos(mensaje_texto):
    """
    Detecta de manera inteligente, utilizando Gemini y tipado Pydantic (Structured Outputs),
    si una pregunta del usuario requiere consultar directamente datos concretos e inmutables
    de la tabla de procesos operativos (procesos_operativos) en SQLite en vez de manuales generales (RAG).
    Devuelve una tupla (bool, str) indicando si es específica y el ID del proceso asociado en caso de aplicar.
    """
    cargar_variables_env()
    api_key = os.environ.get("GEMINI_API_KEY")

    instrucciones = (
        "Eres un clasificador inteligente para un centro de soporte corporativo.\n"
        "Debes analizar el mensaje del usuario y determinar si está realizando una pregunta "
        "altamente específica que requiere consultar la base de datos de procesos operativos internos inmutables.\n"
        "Los procesos operativos soportados son:\n"
        "1. P_001: atención a aclaraciones (área responsable: Servicio a cliente)\n"
        "2. P_002: cancelación de productos (área responsable: Servicio a cliente)\n"
        "3. P_003: escalamiento de incidencias (área responsable: Supervisores)\n"
        "4. P_004: actualización de datos (área responsable: Finanzas)\n"
        "5. P_005: gestión de quejas internas (área responsable: Recursos Humanos)\n\n"
        "Si el usuario pregunta por detalles o atributos particulares de estos cinco como tiempos promedio de resolución, "
        "canales de atención específicos, nivel de criticidad o área responsable a cargo, o si menciona el nombre/ID "
        "de alguno de estos para obtener información inmutable, debes marcar `es_pregunta_altamente_especifica` como True y "
        "especificar el de `id_del_proceso` (P_001, P_002, P_003, P_004 o P_005) correcto.\n"
        "Si es una pregunta de soporte general sobre políticas que no describe estos cinco procesos internos, "
        "un saludo o un reclamo amplio, debes marcar `es_pregunta_altamente_especifica` como False."
    )

    # 1. Intentar usar la librería oficial google-genai SDK con Pydantic primero
    if api_key and api_key != "MY_GEMINI_API_KEY" and api_key != "" and SDK_DISPONIBLE:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=f"Analiza el siguiente mensaje del usuario:\n\n\"{mensaje_texto}\"",
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ClasificacionPreguntaProceso,
                    max_output_tokens=150
                )
            )
            if response and response.text:
                res_data = json.loads(response.text.strip())
                return bool(res_data.get("es_pregunta_altamente_especifica", False)), str(res_data.get("id_del_proceso", "")).upper()
        except Exception:
            pass

    # 2. Fallback clásico por palabras clave / identificadores locales por seguridad de red o API key ausente
    m_lower = mensaje_texto.lower()
    for pid in ["p_001", "p_002", "p_003", "p_004", "p_005"]:
        if pid in m_lower:
            return True, pid.upper()
            
    if any(p in m_lower for p in ["atención a aclaraciones", "atencion a aclaraciones", "aclaración", "aclaracion"]):
        return True, "P_001"
    elif any(p in m_lower for p in ["cancelación de productos", "cancelacion de productos", "cancelar productos", "cancelar mis productos", "cancelar un producto"]):
        return True, "P_002"
    elif any(p in m_lower for p in ["escalamiento de incidencias", "escalamiento de incidencia", "escalar incidencias", "incidencia", "incidencias"]):
        return True, "P_003"
    elif any(p in m_lower for p in ["actualización de datos", "actualizacion de datos", "actualizar mis datos", "actualizar datos"]):
        return True, "P_004"
    elif any(p in m_lower for p in ["gestión de quejas", "gestion de quejas", "gestión de quejas internas", "quejas internas", "queja interna"]):
        return True, "P_005"

    return False, ""

def extraer_datos_contacto_con_gemini(mensaje_texto, historial_str=""):
    """
    Usa el SDK oficial de Gemini para extraer 
    inteligentemente los datos de contacto que el usuario desea actualizar (nombre_completo, correo, o telefono) y su nuevo valor.
    Retorna un diccionario JSON con las llaves: 'campo', 'valor'.
    Si no se puede identificar el campo o el valor de forma explícita en el mensaje actual (incluso analizando el historial), retorna null para ellos.
    """
    cargar_variables_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 1. Análisis local de soporte por si no hay API key disponible o falla la conexión
    campo_local = None
    valor_local = None
    t_low = mensaje_texto.lower()
    
    # Buscar si hay un correo en el mensaje actual
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', mensaje_texto)
    if emails:
        campo_local = "correo"
        valor_local = emails[0].strip(".,()!\"'¿?")
    else:
        # Buscar números de teléfono en el mensaje actual (p. ej. "5551234", "123-4567")
        telefonos = re.findall(r'\+?\d[\d\s-]{6,14}\d', mensaje_texto)
        if telefonos:
             # Si en el historial se les pidió teléfono, o si se menciona teléfono en el mensaje
             h_low = historial_str.lower() if historial_str else ""
             if any(p in t_low for p in ["tel", "fono", "número", "numero", "cel", "móvil", "movil", "contacto", "telefono", "teléfono"]) or "teléfono" in h_low or "telefono" in h_low:
                 campo_local = "telefono"
                 valor_local = telefonos[0].strip()
        else:
             # Si no hay correo ni teléfono, ver si hay un nombre mencionado en respuesta a una petición o con patrones
             patrones_nombre = [
                 r'(?:nombre es|nombre a|cambiar nombre por|nuevo nombre:?)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ\s\.]+)',
                 r'(?:llamo|llamarme)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ\s\.]+)'
             ]
             for pat in patrones_nombre:
                 match_nombre = re.search(pat, t_low)
                 if match_nombre:
                     campo_local = "nombre_completo"
                     valor_local = mensaje_texto[match_nombre.start(1):match_nombre.end(1)].strip()
                     break
                     
             # Si el último mensaje de soporte en el historial le preguntó por su nombre
             if not campo_local and historial_str:
                 lineas_hist = [l.strip() for l in historial_str.strip().split("\n") if l.strip()]
                 if lineas_hist:
                     ultima_linea = lineas_hist[-1]
                     if "SOPORTE:" in ultima_linea and any(p in ultima_linea.lower() for p in ["nombre", "cómo te llamas", "como se llama", "indique su nombre", "nombre completo"]):
                         campo_local = "nombre_completo"
                         valor_local = mensaje_texto.strip()
                     elif "SOPORTE:" in ultima_linea and any(p in ultima_linea.lower() for p in ["teléfono", "telefono", "número", "numero"]):
                         campo_local = "telefono"
                         valor_local = mensaje_texto.strip()
                     elif "SOPORTE:" in ultima_linea and any(p in ultima_linea.lower() for p in ["correo", "email", "dirección", "direccion"]):
                         if "@" in mensaje_texto:
                             campo_local = "correo"
                             valor_local = mensaje_texto.strip()
 
    if not api_key or api_key == "MY_GEMINI_API_KEY" or api_key == "":
        return {"campo": campo_local, "valor": valor_local}
 
    instrucciones = (
        "Eres un extractor de datos de soporte extremadamente preciso.\n"
        "Analiza el mensaje actual del usuario y el historial de conversación para determinar si el usuario desea actualizar un dato de contacto.\n"
        "Campos válidos que se pueden actualizar:\n"
        "- 'nombre_completo' (para actualizaciones de Nombre Completo/Nombre)\n"
        "- 'correo' (para Dirección de Correo Electrónico/Email)\n"
        "- 'telefono' (para Número de Teléfono/Celular)\n\n"
        "Reglas:\n"
        "1. Identifica qué campo desea actualizar el usuario y el nuevo valor EXACTO que indicó en su mensaje actual.\n"
        "2. Si el usuario especificó el nuevo valor en su mensaje (o si el mensaje actual es simplemente el valor en respuesta a una pregunta previa de Soporte, por ejemplo si Soporte preguntó 'Por favor indique su nuevo teléfono' y el usuario respondió '555-1234'), asocia ese valor al campo correcto.\n"
        "3. Si el usuario NO ha proporcionado un valor específico en su mensaje actual para la actualización (por ejemplo, si solo dice 'quiero actualizar mi teléfono' sin indicar el número nuevo), debes retornar null para 'valor'. No inventes ningún valor ficticio ni uses correos/teléfonos por defecto.\n"
        "4. Si el usuario no dice qué campo quiere actualizar ni el valor, devuelve null en ambos.\n\n"
        "Debes responder estrictamente en formato JSON válido de la forma:\n"
        "{\n"
        "  \"campo\": \"nombre_completo\" | \"correo\" | \"telefono\" | null,\n"
        "  \"valor\": \"<valor_exacto_provisto_por_el_usuario_del_mensaje>\" | null\n"
        "}\n"
        "No agregues explicaciones, solo el JSON exacto."
    )
    
    prompt = (
        f"[HISTORIAL DE CONVERSACIÓN RECIENTE]\n{historial_str}\n\n"
        f"[MENSAJE ACTUAL DEL USUARIO]\n\"{mensaje_texto}\""
    )
 
    # Usar la librería oficial google-genai SDK
    if SDK_DISPONIBLE:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.0,
                    max_output_tokens=150,
                    response_mime_type="application/json",
                    response_schema=DatosContacto
                )
            )
            if response and response.text:
                res_json = json.loads(response.text.strip())
                if "campo" in res_json and "valor" in res_json:
                    return res_json
        except Exception:
            pass
 
    return {"campo": campo_local, "valor": valor_local}

def extraer_descripcion_problema_de_cuenta(mensaje_texto, historial_str=""):
    """
    Analiza el mensaje del usuario y su historial para extraer una descripción específica del problema.
    Si el usuario solo emitió un activador genérico (ej. 'problemas con mi cuenta', 'soporte urgente'),
    retorna null.
    """
    cargar_variables_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 1. Limpieza local y detección local heurística
    t_low = mensaje_texto.lower().strip(".,()!\"'¿? ")
    genericos = [
        "problema con la cuenta", "problema con mi cuenta", "problema de cuenta",
        "problemas con la cuenta", "problemas con mi cuenta", "error con la cuenta",
        "error con mi cuenta", "problemas urgentes", "problema urgente", "urgente",
        "escalar ticket", "escalacion de tickets", "escalar", "escalacion", "asistencia",
        "soporte urgente", "tengo un problema", "tengo problemas", "ayuda", "soporte",
        "problemas urgentes con mi cuenta"
    ]
    
    es_generico = False
    for gen in genericos:
        if t_low == gen or t_low == f"mi {gen}" or t_low == f"un {gen}" or t_low == f"quiero {gen}":
            es_generico = True
            break
            
    # Si el último mensaje de soporte en el historial le preguntó por su problema
    problema_local = None
    if not es_generico and len(mensaje_texto.strip()) > 5:
        problema_local = mensaje_texto.strip()
    elif historial_str:
        lineas_hist = [l.strip() for l in historial_str.strip().split("\n") if l.strip()]
        if lineas_hist:
            ultima_linea = lineas_hist[-1]
            if "SOPORTE:" in ultima_linea and any(p in ultima_linea.lower() for p in ["indique", "describa", "cuál es el problema", "cual es el problema", "qué problema", "que problema"]):
                problema_local = mensaje_texto.strip()
        
    if not api_key or api_key == "MY_GEMINI_API_KEY" or api_key == "":
        return {"problema": problema_local}

    instrucciones = (
        "Eres un analizador de soporte bancario inteligente.\n"
        "Debes determinar si el usuario ha provisto una descripción concreta del problema que tiene con su cuenta "
        "(ej. 'el cajero no me dio el dinero', 'banca móvil bloqueada', 'movimiento no reconocido de $1000', etc.).\n"
        "Reglas:\n"
        "1. Si el usuario describe un problema específico en su mensaje actual (o respondiendo a una petición del historial), extrae esa descripción redactada de forma concisa.\n"
        "2. Si el mensaje del usuario es solo un saludo o una frase genérica indicando que tiene un problema o que quiere escalar/crear un ticket (ej. 'tengo un problema con la cuenta', 'problema urgente', 'necesito ayuda', 'soporte'), pero NO aclara el problema en sÍ, debes retornar null.\n\n"
        "Responde estrictamente en formato JSON válido:\n"
        "{\n"
        "  \"problema\": \"<descripcion_concreta>\" | null\n"
        "}"
    )
    
    prompt = (
        f"[HISTORIAL RECIENTE]\n{historial_str}\n\n"
        f"[MENSAJE DEL USUARIO]\n\"{mensaje_texto}\""
    )
    
    if SDK_DISPONIBLE:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.0,
                    max_output_tokens=150,
                    response_mime_type="application/json",
                    response_schema=DescripcionProblema
                )
            )
            if response and response.text:
                res_json = json.loads(response.text.strip())
                if "problema" in res_json:
                    return res_json
        except Exception:
            pass
            
    return {"problema": problema_local}

def clasificar_tema_con_gemini(mensaje_texto):
    """
    Utiliza el SDK oficial de Gemini para clasificar el mensaje del usuario en uno de los temas específicos.
    Si falla o no hay llave de API, utiliza un motor de reglas local por palabras clave de seguridad.
    """
    cargar_variables_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    instrucciones = (
        "Eres un clasificador de temas de soporte al cliente para una empresa. "
        "Debes responder ÚNICAMENTE con una de las siguientes opciones exactas:\n"
        "- Cancelación de Producto\n"
        "- Escalación de tickets (Selecciona esta opción obligatoriamente si el usuario indica o reporta un problema con su cuenta)\n"
        "- Actualización de contacto\n"
        "- Complaints / Quejas\n"
        "- Soporte General\n\n"
        "No agregues explicaciones, puntuaciones adicionales, introducciones ni despedidas. Solo el texto exacto del tema."
    )
    
    temas_validos = [
        "Cancelación de Producto",
        "Escalación de tickets",
        "Actualización de contacto",
        "Complaints / Quejas",
        "Soporte General"
    ]

    # 1. Intentar usar la librería oficial google-genai SDK con Pydantic primero
    if api_key and api_key != "MY_GEMINI_API_KEY" and api_key != "" and SDK_DISPONIBLE:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=f"Clasifica el siguiente mensaje del usuario:\n\n\"{mensaje_texto}\"",
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.0,
                    max_output_tokens=100,
                    response_mime_type="application/json",
                    response_schema=ClasificacionTema
                )
            )
            if response and response.text:
                res_json = json.loads(response.text.strip())
                tema_detectado = res_json.get("tema", "Soporte General")
                for t in temas_validos:
                    if t.lower() == tema_detectado.lower():
                        return t
                return "Soporte General"
        except Exception:
            pass

    # 2. Fallback de seguridad simple por palabras clave en caso de error o sin API Key
    t_lower = mensaje_texto.lower()
    if any(p in t_lower for p in ["cancel", "cancelar", "baja", "suscripcion", "suscripción", "desactivar"]):
        return "Cancelación de Producto"
    elif any(p in t_lower for p in ["escalar", "escalacion", "escalación", "urgente", "caido", "caído", "error crítico", "problema con la cuenta", "problema con mi cuenta", "problema de cuenta", "problemas con la cuenta", "problemas con mi cuenta", "error con la cuenta", "error con mi cuenta"]):
        return "Escalación de tickets"
    elif any(p in t_lower for p in ["actualizar", "contacto", "correo", "email", "telefono", "teléfono", "dirección", "direccion"]):
        return "Actualización de contacto"
    elif any(p in t_lower for p in ["queja", "reclamacion", "reclamación", "mal servicio", "insatisfecho", "pesimo", "pésimo"]):
        return "Complaints / Quejas"

    return "Soporte General"

def generar_respuesta_compleja_gemini(usuario_mensaje, tema, historial_str, contexto_rag, resultados_tool, perfil_usuario=None):
    """
    Genera la respuesta compleja usando la librería oficial Google GenAI SDK.
    """
    cargar_variables_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key or api_key == "MY_GEMINI_API_KEY" or api_key == "":
        return (
            "[INSTRUCCIÓN DE CONFIGURACIÓN]\n"
            "El Agente requiere de la variable de entorno 'GEMINI_API_KEY' para generar la respuesta compleja.\n"
            "Por favor, configure esta variable de entorno o cree un archivo '.env' en la raíz del proyecto para habilitar las respuestas complejas con IA.\n"
            "Ejemplo de archivo .env:\n"
            "GEMINI_API_KEY=\"tu_clave_secreta_aquí\""
        )

    instrucciones = (
        "Eres un Agente Virtual de Soporte Avanzado de nivel corporativo para una empresa bancaria.\n"
        "Tu objetivo es resolver la consulta del cliente utilizando las políticas internas (RAG) y los resultados de las herramientas del backend *ÚNICAMENTE*.\n"
        "Debes responder en español, con un tono extremadamente profesional, empático, claro, estructurado y seguro. "
        "Dirígete al cliente con respeto y formalidad.\n\n"
        "REGLA CRÍTICA ABSOLUTA DE LIMITACIÓN DE PALABRAS:\n"
        "Tu respuesta definitiva NO DEBE exceder las 50 palabras bajo ninguna circunstancia. "
        "Sé sumamente conciso, directo, preciso y claro. Tu respuesta debe ser breve, directa al grano, "
        "y terminar elegantemente en 50 palabras o menos."
    )
    
    bloque_perfil = ""
    if perfil_usuario:
        try:
            tickets = json.loads(perfil_usuario.get("tickets_activos", "[]"))
            tickets_fmt = "\n".join([f"  - Ticket {t.get('numero_ticket')}: {t.get('problema')}" for t in tickets]) if tickets else "  (Ninguno)"
        except Exception:
            tickets_fmt = f"  {perfil_usuario.get('tickets_activos')}"
            
        bloque_perfil = (
            "[INFORMACIÓN DE REGISTRO DEL USUARIO ACTUAL]\n"
            f"- Nombre Completo: {perfil_usuario.get('nombre_completo')}\n"
            f"- Correo Electrónico: {perfil_usuario.get('correo')}\n"
            f"- Teléfono de Contacto: {perfil_usuario.get('telefono')}\n"
            f"- Estatus de la Cuenta: {perfil_usuario.get('estatus_cuenta')}\n"
            f"- Tickets Activos registrados:\n{tickets_fmt}\n\n"
        )

    instrucciones_herramientas = ""
    if resultados_tool:
        instrucciones_herramientas = (
            f"Adicionalmente, el departamento de sistemas ejecutó con éxito una herramienta para esta consulta:\n"
            f"Resultados de la Herramienta:\n{json.dumps(resultados_tool, indent=2, ensure_ascii=False)}\n"
            "DEBES incluir de forma clara en tu respuesta códigos de confirmación, IDs de tickets/quejas, plazos y estados de reembolso provistos por la herramienta."
        )

    historial_actual = historial_str if historial_str else "(No hay historial previo)"
    
    contexto_etiqueta = "[POLÍTICAS DE LA EMPRESA RECUPERADAS (RAG)]"
    if "[DATOS REALES E INMUTABLES DE LA TABLA DE PROCESOS" in contexto_rag:
        contexto_etiqueta = "[INFORMACIÓN EXCLUSIVA DE LA BASE DE DATOS DE PROCESOS]"
        
    prompt = (
        "[DIRECTIVA DE REDACCIÓN]\n"
        "Utiliza el contexto de políticas, resultados de herramientas e información del usuario de abajo para redactar de manera fluida y precisa la respuesta para el cliente. No inventes procedimientos ajenos a la política provista.\n\n"
        + bloque_perfil +
        "[HISTORIAL DE CONVERSACIÓN RECIENTE]\n"
        + historial_actual + "\n\n"
        "[CONSULTA ACTUAL DEL CLIENTE]\n"
        + usuario_mensaje + "\n\n"
        "[TEMA CLASIFICADO]\n"
        + tema + "\n\n"
        + contexto_etiqueta + "\n"
        + contexto_rag + "\n\n"
        + instrucciones_herramientas + "\n\n"
        "Escribe la respuesta dirigida formalmente al cliente:"
    )

    # Usar la librería oficial google-genai SDK
    if SDK_DISPONIBLE:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    temperature=0.3,
                    max_output_tokens=2048
                )
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            return f"[Error al generar la respuesta con Gemini SDK: {str(e)}]"

    return "[Error: Google GenAI SDK no está disponible para generar la respuesta]"

