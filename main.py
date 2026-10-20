import os
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai
import requests

app = Flask(__name__)

# Configuración mediante Variables de Entorno (se configuran en Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kigkkjpvtnsjalhvyoaz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_h-D9PMPwgsenp1he3gDPpA_pmJmnfwp")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializar clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def send_telegram_message(user_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN no configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

@app.route('/', methods=['GET'])
def health_check():
    return "Bot Mail2Telegram-Pro activo y listo 🚀", 200

@app.route('/webhook/email', methods=['POST'])
def process_email():
    data = request.json or {}
    recipient = data.get("recipient", "")
    sender = data.get("sender", "Desconocido")
    subject = data.get("subject", "Sin asunto")
    body = data.get("body", "")

    try:
        user_id_str = recipient.split("@")[0].replace("user_", "")
        user_id = int(user_id_str)
    except Exception:
        return jsonify({"status": "error", "message": "Alias inválido"}), 400

    # Consultar usuario en Supabase
    response = supabase.table("mail2telegram_users").select("*").eq("id", user_id).execute()
    users = response.data

    if not users:
        return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404

    user_config = users[0]
    summarize_enabled = user_config.get("summarize_enabled", True)
    bills_only = user_config.get("bills_only", False)

    # Procesar con Gemini AI si está activado
    resumen_text = body[:300]
    if summarize_enabled and ai_client:
        prompt = f"""
        Analiza este correo:
        De: {sender}
        Asunto: {subject}
        Cuerpo: {body}

        1. ¿Es una factura, recibo o compra? (SI/NO)
        2. Escribe un resumen ejecutivo de máximo 3 oraciones.
        
        Responde en este formato:
        ES_FACTURA: [SI/NO]
        RESUMEN: [Resumen]
        """
        ai_resp = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        ).text
        
        is_bill = "ES_FACTURA: SI" in ai_resp.upper()
        if bills_only and not is_bill:
            return jsonify({"status": "ignored", "reason": "Filtro de facturas activo"}), 200

        for line in ai_resp.split("\n"):
            if line.startswith("RESUMEN:"):
                resumen_text = line.replace("RESUMEN:", "").strip()

    # Enviar a Telegram
    msg = f"📩 *Nuevo Correo Recibido*\n\n👤 *De:* `{sender}`\n📌 *Asunto:* {subject}\n\n🤖 *Resumen:* \n{resumen_text}"
    send_telegram_message(user_id, msg)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
