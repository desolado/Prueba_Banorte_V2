#!/usr/bin/env python3
import os
import sys
import json
import uuid
import datetime
import re

# Schemas and SDK configurations
from models import (
    ClasificacionPreguntaProceso,
    DatosContacto,
    DescripcionProblema,
    ClasificacionTema,
    SDK_DISPONIBLE,
    cargar_variables_env
)

# SQLite Database Functions
from database import (
    obtener_conexion,
    inicializar_base_de_datos,
    buscar_usuario_por_correo,
    buscar_usuario_por_telefono,
    registrar_o_actualizar_usuario,
    registrar_proceso_en_bd,
    agregar_mensaje_a_conversacion,
    obtener_memoria_conversacion,
    borrar_todas_las_conversaciones,
    obtener_todos_los_procesos
)

# RAG Module Functions and Specs
from rag import (
    TAMANO_FRAGMENTO,
    TRASLAPE,
    DIMENSION_EMBEDDING,
    CANTIDAD_TOP_K,
    consultar_motor_rag
)

# Execution Tools
from tools import (
    tool_cancelar_suscripcion,
    tool_escalar_ticket,
    tool_actualizar_contacto,
    tool_registrar_queja
)

## Import safe reference to genai layers
if SDK_DISPONIBLE:
    from google import genai
    from google.genai import types

# Inteligent Classifiers and Intent Extraction Module
from classifiers import (
    es_pregunta_especifica_de_procesos,
    extraer_datos_contacto_con_gemini,
    extraer_descripcion_problema_de_cuenta,
    clasificar_tema_con_gemini,
    generar_respuesta_compleja_gemini
)


# =====================================================================
# CICLO INTERNO MULTIAGENTE DE DECISIÓN Y EJECUCIÓN (ORQUESTADOR)
# =====================================================================

def ejecutar_bucle_agente(payload_peticion):
    """
    Toma un payload estructurado JSON:
    {
      "conversation_id": "string",
      "user_id": "string",
      "message": { "text": "string" },
      "metadata": { "channel": "string" }
    }
    Procesa la planificación secuencial (Agente 1), consulta RAG, toma
    de decisiones, disparo de herramientas (Agente 2) y síntesis en español.
    """
    conv_id = payload_peticion.get("conversation_id", "clip_conversacion_defecto")
    user_id = payload_peticion.get("user_id", "usuario_defecto")
    mensaje_texto = payload_peticion.get("message", {}).get("text", "")
    t_lower = mensaje_texto.lower()
    metadata = payload_peticion.get("metadata", {})
    canal = metadata.get("channel", "terminal")
    timestamp = metadata.get("timestamp", datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    
    trazas = []
    
    # 1. Almacenar mensaje del usuario en SQLite
    agregar_mensaje_a_conversacion(conv_id, user_id, "user", mensaje_texto, timestamp)
    
    # 2. Recuperar historial Conversacional basado en el correo del usuario (user_id)
    historial = obtener_memoria_conversacion(user_id)
    bloque_historial_str = ""
    for post in historial[:-1]:
        nom = "CLIENTE" if post["remitente"] == "user" else "SOPORTE"
        bloque_historial_str += f"- {nom}: {post['texto']}\n"
        
    # 3. Agente 1: Planificación Cognitiva y Descomposición del Problema
    tema = clasificar_tema_con_gemini(mensaje_texto)
    
    if tema == "Cancelación de Producto":
        politica_mapeada = "cancelacion_producto"
    elif tema == "Escalación de tickets":
        politica_mapeada = "escalacion_tickets"
    elif tema == "Actualización de contacto":
        politica_mapeada = "actualizar_contacto"
    elif tema == "Complaints / Quejas":
        politica_mapeada = "quejas"
    else:
        tema = "Soporte General"
        politica_mapeada = "soporte_cliente"
        
    pensamiento_agente_1 = f"El mensaje del cliente hace alusión a: '{tema}'. Activando búsqueda RAG sobre política '{politica_mapeada}' y coordinando ejecución de herramientas con Agente 2."
    trazas.append({
        "agent": "Agente 1 (Coordinador)",
        "phase": "Descomposición de Tarea",
        "description": f"Se clasificó el tema de la consulta como '{tema}'. Diseñando secuencia de ejecución.",
        "thoughts": pensamiento_agente_1
    })
    
    trazas.append({
        "agent": "Agente 1 (Coordinador)",
        "phase": "Delegación de Ejecución",
        "description": "Delegando tareas a Agente 2 para examinar manuales y ejecutar base de datos corporativa.",
        "data_sent": f"RAG_Búsqueda: '{politica_mapeada}' | Objetivo: '{mensaje_texto}'"
    })
    
    # RAG: Búsqueda Semántica Vectorial (Local)
    trazas.append({
        "agent": "Agente 2 (Ejecutor Técnico)",
        "phase": "Búsqueda Semántica Vectorial (RAG)",
        "description": "Calculando similitud de coseno en SQLite contra segmentos de documentos corporativos.",
        "rag_specs": {
            "chunk_size_chars": TAMANO_FRAGMENTO,
            "overlap_chars": TRASLAPE,
            "embedding_dimension": DIMENSION_EMBEDDING,
            "top_k": CANTIDAD_TOP_K,
            "search_strategy": "Similitud de Coseno sobre Vectores Oficiales de Gemini",
            "vector_store": "Caché e Indexador SQLite integrado"
        }
    })
    
    user_reg = buscar_usuario_por_correo(user_id)
    numeric_user_id = user_reg.get("user_id") if user_reg else None
    
    # Comprobar si es una consulta muy específica sobre procesos/herramientas de la base de datos (con Pydantic + Gemini)
    es_especifica_procesos, id_proceso_especifico = es_pregunta_especifica_de_procesos(mensaje_texto)
    
    bloque_contexto_recuperado = ""
    proceso_sqlite_registrado = None
    resultados_rag = []
    
    if es_especifica_procesos:
        # Recuperar datos reales e inmutables de la base de datos directamente de la nueva tabla procesos_operativos
        inicializar_base_de_datos()
        conn = obtener_conexion()
        cursor = conn.cursor()
        
        # Consultar de manera escalable y eficiente el proceso ID específico si Gemini con Pydantic lo identificó
        if id_proceso_especifico:
            cursor.execute("SELECT * FROM procesos_operativos WHERE id_del_proceso = ?", (id_proceso_especifico,))
            filas_procesos = cursor.fetchall()
            # Si no hubiera filas con ese ID por alguna razón, caer en traer todos por seguridad
            if not filas_procesos:
                cursor.execute("SELECT * FROM procesos_operativos")
                filas_procesos = cursor.fetchall()
        else:
            cursor.execute("SELECT * FROM procesos_operativos")
            filas_procesos = cursor.fetchall()
            
        conn.close()
        
        lista_procs = [dict(f) for f in filas_procesos]
        
        if lista_procs:
            bloque_contexto_recuperado = (
                "[DATOS REALES E INMUTABLES DE LA TABLA DE PROCESOS OPERATIVOS INTERNOS]\n"
                "ATENCIÓN: Se ha anulado la búsqueda de la política RAG corporativa general porque el usuario ha realizado "
                "una pregunta altamente específica de herramientas o procesos operativos internos inmutables clasificados con Pydantic + Gemini.\n"
                "Debes responder basándote ÚNICAMENTE en la información inmutable y certificada de la siguiente tabla de procesos operativos. "
                "No inventes datos, no uses texto del RAG ni asumas nada externo:\n\n"
            )
            for idx, proc in enumerate(lista_procs):
                bloque_contexto_recuperado += (
                    f"--- PROCESO OPERATIVO INMUTABLE #{idx + 1} ---\n"
                    f"- ID del Proceso (id_del_proceso): {proc.get('id_del_proceso')}\n"
                    f"- Nombre del Proceso (nombre_proceso): {proc.get('nombre_proceso')}\n"
                    f"- Área Responsable (area_responsable): {proc.get('area_responsable')}\n"
                    f"- Tiempo Promedio de Resolución (tiempo_promedio_resolución): {proc.get('tiempo_promedio_resolución')}\n"
                    f"- Canal de Atención (canal_de_atención): {proc.get('canal_de_atención')}\n"
                    f"- Nivel de Criticidad (nivel_de_criticidad): {proc.get('nivel_de_criticidad')}\n\n"
                )
            proceso_sqlite_registrado = {
                "process_id": lista_procs[0].get("id_del_proceso"),
                "process_name": lista_procs[0].get("nombre_proceso"),
                "area": lista_procs[0].get("area_responsable"),
                "expected_timeframe_for_solution": lista_procs[0].get("tiempo_promedio_resolución"),
                "channel": lista_procs[0].get("canal_de_atención"),
                "priority": lista_procs[0].get("nivel_de_criticidad")
            }
        else:
            bloque_contexto_recuperado = (
                "[DATOS REALES E INMUTABLES DE LA TABLA DE PROCESOS OPERATIVOS INTERNOS]\n"
                "Actualmente no se encuentran cargados los procesos operativos inmutables en la base de datos."
            )
            
        trazas.append({
            "agent": "Agente 2 (Ejecutor Técnico)",
            "phase": "Búsqueda Directa en Base de Datos de Procesos Operativos (RAG Omitido)",
            "description": f"Se detectó una consulta altamente específica evaluada mediante Pydantic + Gemini. Se omitió RAG y se consultó la tabla 'procesos_operativos' de SQLite (ID específico: '{id_proceso_especifico or 'TODOS'}').",
            "data_retrieved_from_db": lista_procs
        })
    else:
        # Lógica de RAG estándar
        resultados_rag = consultar_motor_rag(mensaje_texto, user_id=numeric_user_id)
        if resultados_rag:
            for idx, item in enumerate(resultados_rag):
                bloque_contexto_recuperado += f"[Documento: {item['source']} (Similitud: {item['score']})]\n{item['content']}\n\n"
                if not proceso_sqlite_registrado and "process_meta" in item:
                    proceso_sqlite_registrado = item["process_meta"]
        else:
            bloque_contexto_recuperado = "No se encontraron manuales explícitos en el sistema. Empleando directivas lógicas estándar de soporte."
 
        trazas.append({
            "agent": "Agente 2 (Ejecutor Técnico)",
            "phase": "Resultados RAG Obtención",
            "description": f"Se obtuvieron {len(resultados_rag)} fragmentos de manuales corporativos de forma exitosa.",
            "context_retrieved": bloque_contexto_recuperado,
            "sqlite_process_registered": proceso_sqlite_registrado
        })
    
    # Match y ejecución automática de herramientas relacionales
    ejecucion_tool = None
    resultados_tool = None
    
    if tema == "Cancelación de Producto":
        producto = "Suscripción Premium Empresa"
        for p in ["enterprise", "pro", "basic", "premium", "licencia", "mensual"]:
            if p in t_lower:
                producto = f"Suscripción {p.capitalize()}"
        resultados_tool = tool_cancelar_suscripcion(user_id, producto)
        ejecucion_tool = "tool_cancelar_suscripcion"
        
    elif tema == "Escalación de tickets":
        urgencia = "Tier 2 Crítico" if any(u in t_lower for u in ["urgente", "critico", "crítico", "ahora", "inmediato"]) else "Tier 1 Estándar"
        datos_prob = extraer_descripcion_problema_de_cuenta(mensaje_texto, bloque_historial_str)
        problema_especifico = datos_prob.get("problema")
        
        if problema_especifico:
            resultados_tool = tool_escalar_ticket(user_id, problema_especifico, urgencia)
            ejecucion_tool = "tool_escalar_ticket"
        else:
            resultados_tool = {
                "nombre_herramienta": "tool_escalar_ticket",
                "status": "pending_info",
                "problema_detectado": None,
                "mensaje": "Faltan detalles. Por favor, solicite respetuosamente al cliente que describa con precisión y detalle el problema o error específico que está experimentando con su cuenta para proceder con la escalación."
            }
            ejecucion_tool = None
        
    elif tema == "Actualización de contacto":
        datos = extraer_datos_contacto_con_gemini(mensaje_texto, bloque_historial_str)
        campo = datos.get("campo")
        valor = datos.get("valor")
        if campo and valor:
            resultados_tool = tool_actualizar_contacto(user_id, campo, valor)
            ejecucion_tool = "tool_actualizar_contacto"
        else:
            resultados_tool = {
                "nombre_herramienta": "tool_actualizar_contacto",
                "status": "pending_info",
                "campo_detectado": campo,
                "valor_detectado": valor,
                "mensaje": "Faltan detalles. Se requiere que el usuario indique en su mensaje qué campo de contacto desea cambiar (Nombre Completo, Correo o Teléfono) y el nuevo valor exacto a asignar."
            }
            ejecucion_tool = None
        
    elif tema == "Complaints / Quejas":
        resultados_tool = tool_registrar_queja(user_id, mensaje_texto)
        ejecucion_tool = "tool_registrar_queja"
        
    if ejecucion_tool:
        trazas.append({
            "agent": "Agente 2 (Ejecutor Técnico)",
            "phase": f"Ejecución de Herramienta: {ejecucion_tool}",
            "description": f"Se disparó una acción integrada en la base de datos maestra con éxito.",
            "results_report": resultados_tool
        })
        
    payload_reporte_agente_2 = {
        "rag_context": bloque_contexto_recuperado,
        "tool_executed": ejecucion_tool,
        "tool_results": resultados_tool,
        "process_logged": proceso_sqlite_registrado
    }
    
    trazas.append({
        "agent": "Agente 2 (Ejecutor Técnico)",
        "phase": "Entrega de Auditoría",
        "description": "Enviando reportes detallados y variables ambientales al Coordinador Principal para redacción final.",
        "report_payload": payload_reporte_agente_2
    })
    
    # Determinar si el correo cambió y buscar perfil de usuario correspondiente
    correo_final = user_id
    if resultados_tool and resultados_tool.get("status") == "success" and resultados_tool.get("campo_afectado") == "correo":
        correo_final = resultados_tool.get("valor_guardado")
        
    perfil_usuario = buscar_usuario_por_correo(correo_final)
    
    # Si el correo de sesión cambió, arrastramos ese cambio al user_id de este turno en adelante
    if correo_final != user_id:
        user_id = correo_final
        
    # 4. Agente 1: Redacción final y síntesis de respuesta en español (Generación via Gemini API)
    respuesta_definitiva = generar_respuesta_compleja_gemini(
        usuario_mensaje=mensaje_texto,
        tema=tema,
        historial_str=bloque_historial_str,
        contexto_rag=bloque_contexto_recuperado,
        resultados_tool=resultados_tool,
        perfil_usuario=perfil_usuario
    )
            
    # 5. Agregar respuesta final sintetizada por Agente 1 en la memoria SQLite
    agregar_mensaje_a_conversacion(conv_id, user_id, "agent1", respuesta_definitiva)
    
    trazas.append({
        "agent": "Agente 1 (Coordinador)",
        "phase": "Respuesta Sintetizada",
        "description": "Compilando respuestas amables y unificadas de cara al usuario final en español.",
        "synthesis": respuesta_definitiva
    })
    
    # 6. Compilar paquete de respuesta estándar
    retorno = {
        "status": "success",
        "conversation_id": conv_id,
        "user_id": user_id,
        "topic_classified": tema,
        "agent_1_response": respuesta_definitiva,
        "trace": trazas,
        "metadata": {
            "channel": canal,
            "timestamp": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        }
    }
    return retorno


# =====================================================================
# INTERFAZ INTERACTIVA PARA EJECUCIÓN DIRECTA EN TERMINAL (CLI)
# =====================================================================

def mostrar_banner_consola():
    cyan = "\033[96m"
    negrita = "\033[1m"
    reset = "\033[0m"
    
    line1 = " ╔══════════════════════════════════════════════════════════════════════════════╗"
    line2 = " ║                              Evaluación Técnica                              ║"
    line3 = " ║                    desarrollo de agentes conversacionales                    ║"
    line4 = " ╚══════════════════════════════════════════════════════════════════════════════╝"
    
    banner = f"{cyan}{negrita}\n{line1}\n{line2}\n{line3}\n{line4}\n{reset}"
    print(banner)

def renderizar_paso_de_traza(paso):
    magenta = "\033[95m"
    cyan = "\033[96m"
    amarillo = "\033[93m"
    verde = "\033[92m"
    negrita = "\033[1m"
    reset = "\033[0m"
    
    agente = paso.get("agent", "Agente")
    fase = paso.get("phase", "Procesamiento")
    desc = paso.get("description", "")
    
    color_agente = magenta
    if "Agente 1" in agente:
        color_agente = cyan
    elif "Agente 2" in agente:
        color_agente = amarillo
        
    print(f"\n[{color_agente}{negrita}{agente}{reset} > {negrita}{fase}{reset}]")
    print(f"  {desc}")
    
    if "thoughts" in paso:
         print(f"  {color_agente}Pensamientos:{reset} {paso['thoughts']}")
    if "data_sent" in paso:
         print(f"  {color_agente}Payload enviado:{reset} {paso['data_sent']}")
    if "rag_specs" in paso:
         print(f"  {color_agente}Detalles Técnicos RAG:{reset} {json.dumps(paso['rag_specs'], indent=2, ensure_ascii=False)}")
    if "context_retrieved" in paso:
         print(f"  {color_agente}Contexto RAG Recuperado:{reset}\n")
         lineas = paso["context_retrieved"].strip().split("\n")
         for linea in lineas[:12]:
              print(f"    {linea}")
         if len(lineas) > 12:
              print(f"    ... [truncado {len(lineas)-12} líneas]")
    if "sqlite_process_registered" in paso and paso["sqlite_process_registered"]:
         p = paso["sqlite_process_registered"]
         print(f"  {verde}Proceso SQLite Guardado:{reset} ID: {p.get('assigned_process_id_db')}, Prioridad: {p.get('priority')}, Área: {p.get('area')}")
    if "results_report" in paso:
         print(f"  {verde}Reporte de Herramienta:{reset} {json.dumps(paso['results_report'], indent=2, ensure_ascii=False)}")
    if "synthesis" in paso:
         print(f"  {verde}Síntesis Generada:{reset} {paso['synthesis']}")

def loop_terminal_principal():
    inicializar_base_de_datos()
    mostrar_banner_consola()
    
    verde = "\033[92m"
    cyan = "\033[96m"
    amarillo = "\033[93m"
    negrita = "\033[1m"
    reset = "\033[0m"
    
    print(f"{cyan}{negrita}Por favor, ingrese su correo electrónico para iniciar la sesión:{reset}")
    while True:
        try:
            email_input = input(f"{negrita}Correo electrónico: {reset}").strip()
            if not email_input:
                print("El correo electrónico no puede estar vacío.")
                continue
            if "@" not in email_input or "." not in email_input:
                print("El correo electrónico debe tener un formato válido (ej. usuario@dominio.com). Intente de nuevo.")
                continue
            break
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{cyan}Sesión interrumpida por teclado. ¡Hasta luego!{reset}")
            sys.exit(0)
            
    # Buscar el correo electrónico en la tabla de usuarios
    user = buscar_usuario_por_correo(email_input)
    
    if user:
        print(f"\n{verde}{negrita}¡Hola de nuevo, {user['nombre_completo']}!{reset}")
        print(f"Hemos recuperado su información registrada de manera segura:")
        print(f"  - Correo: {user['correo']}")
        print(f"  - Teléfono: {user['telefono']}")
        print(f"  - Estatus de Cuenta: {user['estatus_cuenta']}")
        try:
            t_act = json.loads(user['tickets_activos'])
            print(f"  - Tickets Activos: {len(t_act)}")
        except Exception:
            print(f"  - Tickets Activos: {user['tickets_activos']}")
    else:
        print(f"\n{amarillo}No encontramos un registro para el correo '{email_input}'. Creando una nueva cuenta...{reset}")
        while True:
            try:
                nombre_input = input(f"{negrita}Nombre completo: {reset}").strip()
                if not nombre_input:
                    print("El nombre completo es requerido.")
                    continue
                # Verificación: solo letras, espacios y '.' (sin números ni otros caracteres especiales)
                if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\.]+$", nombre_input):
                    print("El nombre completo solo debe incluir letras, espacios y el carácter '.'. No se permiten números ni otros caracteres especiales. Intente de nuevo.")
                    continue
                break
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n{cyan}Sesión interrumpida por teclado. ¡Hasta luego!{reset}")
                sys.exit(0)
                
        while True:
            try:
                telefono_input = input(f"{negrita}Número de teléfono: {reset}").strip()
                if not telefono_input:
                    print("El número de teléfono es requerido.")
                    continue
                # Verificación: solo números (dígitos) y no sobrepasar 10 dígitos
                if not re.match(r"^\d+$", telefono_input):
                    print("El número de teléfono tiene un formato incorrecto. Solo debe contener números de hasta 10 dígitos.")
                    continue
                if len(telefono_input) > 10:
                    print("El número de teléfono no debe sobrepasar los 10 dígitos.")
                    continue
                
                # Verificación secundaria: evitar duplicados de teléfono entre distintos clientes
                usuario_duplicado = buscar_usuario_por_telefono(telefono_input)
                if usuario_duplicado:
                    print(f"Error: El número de teléfono {telefono_input} ya está registrado para otro usuario. Por favor ingrese un número distinto.")
                    continue
                break
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n{cyan}Sesión interrumpida por teclado. ¡Hasta luego!{reset}")
                sys.exit(0)
                
        registrar_o_actualizar_usuario(email_input, nombre_input, telefono_input, "activa", "[]")
        print(f"\n{verde}{negrita}¡Registro Exitoso! Bienvenido, {nombre_input}.{reset}")
        
    # El ID de usuario se basa estrictamente en el correo electrónico del contacto y conv_id es un chat nuevo único
    user_id = email_input
    conv_id = f"cli_{str(uuid.uuid4())[:8]}"
    
    print("-" * 80)
    print("¡Bienvenido! Escribe tu consulta de soporte aquí abajo en español.")
    print("Temas automáticos disponibles:")
    print(" - Asistencia a dudas")
    print(" - Actualizar mi información")
    print(" - Cancelar mi suscripción")
    print(" - Problemas urgentes")
    print(" - Quejas")
    print("Ingresa el comando '/procesos' para ver el registro estructural de SQLite.")
    print("Ingresa el comando '/borrar_historial' para eliminar todo el historial de conversaciones.")
    print("Escribe '/salir' o presiona Ctrl+C para finalizar la aplicación.")
    print("-" * 80)
 
    while True:
        try:
            print(f"\n{negrita}cliente@agente-shell:~$ {reset}", end="")
            entrada = input().strip()
            
            if not entrada:
                continue
                
            if entrada.lower() in ["/salir", "salir", "exit", "quit"]:
                print(f"\n{cyan}Conexión cerrada. ¡Muchas gracias por utilizar el Agente!{reset}")
                break
                
            if entrada.lower() == "/procesos":
                procs = obtener_todos_los_procesos()
                print(f"\n{cyan}{negrita}--- PROCESOS DE NEGOCIO EN TABLA SQLITE: processes ---{reset}")
                if not procs:
                    print("La tabla está vacía. Realice consultas primero para registrar procesos.")
                for p in procs:
                    usr_str = f" | User ID: {p.get('user_id')}" if p.get('user_id') is not None else ""
                    ts_str = f" | Timestamp: {p.get('timestamp')}" if p.get('timestamp') else ""
                    print(f"ID: {p['process_id']} | Nombre: {p['process_name']} | Área: {p['area']} | Prioridad: {p['priority']} | Plazo de Resolución: {p['expected_timeframe_for_solution']}{usr_str}{ts_str}")
                print("-" * 80)
                continue
 
            if entrada.lower() == "/borrar_historial":
                borrar_todas_las_conversaciones()
                print(f"\n{verde}{negrita}--- HISTORIAL DE CONVERSACIONES BORRADO ---{reset}")
                print("Se han eliminado todos los registros de la tabla 'conversations' de forma exitosa.")
                print("-" * 80)
                continue
                
            cuerpo = {
                "conversation_id": conv_id,
                "user_id": user_id,
                "message": {"text": entrada},
                "metadata": {
                    "channel": "terminal",
                    "timestamp": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                }
            }
            
            retorno = ejecutar_bucle_agente(cuerpo)
            
            # Si el correo cambió, actualizamos las variables locales del loop para mantener la consistencia
            if retorno.get("user_id") and retorno.get("user_id") != user_id:
                user_id = retorno["user_id"]
            
            # Dibujar el rastro cognitivo multi-agente
            print(f"\n{negrita}{cyan}--- TRAZA DE RAZONAMIENTO COGNITIVO MULTI-AGENTE ---{reset}")
            for paso in retorno.get("trace", []):
                renderizar_paso_de_traza(paso)
                
            print("-" * 80)
            print(f"\n{verde}{negrita}Respuesta Unificada (Agente 1):{reset}")
            print(retorno["agent_1_response"])
            print("-" * 80)
            
        except KeyboardInterrupt:
            print(f"\n\n{cyan}Sesión interrumpida por teclado. ¡Hasta luego!{reset}")
            break
        except Exception as e:
            print(f"\n\033[91mFallo inesperado del sistema de agentes: {e}\033[0m")


if __name__ == "__main__":
    inicializar_base_de_datos()
    
    # Soporte bridge para recibir argumentos JSON desde el servidor NodeJS
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        try:
            if len(sys.argv) > 2:
                payload_raw = sys.argv[2]
            else:
                payload_raw = sys.stdin.read().strip()
                
            if not payload_raw:
                print(json.dumps({"status": "error", "message": "Payload JSON vacío desde stdin."}))
                sys.exit(0)
                
            payload_json = json.loads(payload_raw)
            respuesta_json = ejecutar_bucle_agente(payload_json)
            # Volcar salida serializada a stdout libre de ruido
            print(json.dumps(respuesta_json, ensure_ascii=False))
        except Exception as err:
            print(json.dumps({"status": "error", "message": f"Fallo en el puente python: {str(err)}"}))
    else:
        # Iniciar consola interactiva estándar
        loop_terminal_principal()
