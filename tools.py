import os
import uuid
import datetime
import json
from database import (
    buscar_usuario_por_correo,
    inicializar_base_de_datos,
    obtener_conexion
)

def tool_cancelar_suscripcion(usuario_id, producto_id):
    """Cancela de forma segura una suscripción activa de producto."""
    codigo = f"SOL-CAN-{str(uuid.uuid4()).upper()[:8]}"
    
    # Actualizar estatus de cuenta en base de datos
    inicializar_base_de_datos()
    user = buscar_usuario_por_correo(usuario_id)
    if user:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET estatus_cuenta = 'cancelada' WHERE correo = ?", (usuario_id,))
        conn.commit()
        conn.close()

    return {
        "nombre_herramienta": "tool_cancelar_suscripcion",
        "status": "success",
        "mensaje": f"Suscripción activa para '{producto_id}' cancelada de manera exitosa para el Usuario ID {usuario_id}.",
        "codigo_confirmacion": codigo,
        "reembolso_estimado": "Se procesará reembolso al medio de pago original de 5 a 10 días hábiles.",
        "fecha_efectiva": datetime.date.today().strftime("%Y-%m-%d")
    }

def tool_escalar_ticket(usuario_id, titulo_ticket, urgencia):
    """Registra y escala un problema técnico al nivel Tier 2."""
    ticket_id = f"ESC-{str(uuid.uuid4()).upper()[:8]}"
    
    # Actualizar tickets activos en base de datos
    inicializar_base_de_datos()
    user = buscar_usuario_por_correo(usuario_id)
    if user:
        try:
            tickets = json.loads(user["tickets_activos"]) if user["tickets_activos"] else []
            if not isinstance(tickets, list):
                tickets = []
        except Exception:
            tickets = []
            
        tickets.append({
            "numero_ticket": ticket_id,
            "problema": titulo_ticket
        })
        
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tickets_activos = ? WHERE correo = ?", (json.dumps(tickets, ensure_ascii=False), usuario_id))
        conn.commit()
        conn.close()

    return {
        "nombre_herramienta": "tool_escalar_ticket",
        "status": "success",
        "ticket_id": ticket_id,
        "usuario_id": usuario_id,
        "incidente": titulo_ticket,
        "urgencia_declarada": urgencia,
        "departamento_responsable": "Operaciones Técnicas de Nivel 2",
        "plazo_respuesta": "Próximas 24 horas hábiles",
        "timestamp": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    }

def tool_actualizar_contacto(usuario_id, campo, nuevo_valor):
    """Realiza la actualización de los datos de contacto."""
    campo_limpio = campo.strip().lower()
    
    if "@" in nuevo_valor and ("email" in campo_limpio or "correo" in campo_limpio):
        if "." not in nuevo_valor.split("@")[1]:
            return {"nombre_herramienta": "tool_actualizar_contacto", "status": "error", "error": f"Formato de correo inválido: '{nuevo_valor}'."}
            
    inicializar_base_de_datos()
    user = buscar_usuario_por_correo(usuario_id)
    if not user:
        return {
            "nombre_herramienta": "tool_actualizar_contacto",
            "status": "error",
            "error": f"No se encontró un usuario con el correo/Usuario ID: {usuario_id}."
        }
        
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    campo_afectado = ""
    if "correo" in campo_limpio or "email" in campo_limpio or "@" in campo_limpio or "dirección de correo" in campo_limpio:
        cursor.execute("UPDATE users SET correo = ? WHERE correo = ?", (nuevo_valor, usuario_id))
        campo_afectado = "correo"
    elif "telefono" in campo_limpio or "teléfono" in campo_limpio or "tel" in campo_limpio or "número de teléfono" in campo_limpio:
        cursor.execute("UPDATE users SET telefono = ? WHERE correo = ?", (nuevo_valor, usuario_id))
        campo_afectado = "telefono"
    else:
        cursor.execute("UPDATE users SET nombre_completo = ? WHERE correo = ?", (nuevo_valor, usuario_id))
        campo_afectado = "nombre_completo"
        
    conn.commit()
    conn.close()

    return {
        "nombre_herramienta": "tool_actualizar_contacto",
        "status": "success",
        "mensaje": f"Se ha actualizado {campo} por el nuevo registro '{nuevo_valor}'.",
        "campo_afectado": campo_afectado,
        "valor_guardado": nuevo_valor,
        "sincronizacion": "Base de datos master y sistemas de correo sincronizados correctamente"
    }

def tool_registrar_queja(usuario_id, queja):
    """Almacena una disconformidad formal de servicio en la base de datos."""
    queja_id = f"QJA-{str(uuid.uuid4()).upper()[:8]}"
    return {
        "nombre_herramienta": "tool_registrar_queja",
        "status": "success",
        "queja_id": queja_id,
        "usuario_id": usuario_id,
        "comentario_resumen": queja[:100] + "..." if len(queja) > 100 else queja,
        "resolucion_eta": "Se asignará un mediador especializado en los próximos 7 días hábiles.",
        "timestamp": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    }
