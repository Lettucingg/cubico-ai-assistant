"""
Script de prueba TEMPORAL. Simula un mensaje entrante de WhatsApp
con tu número real como remitente, para probar el envío de la
respuesta automática sin depender del panel de pruebas de Meta.
"""

import httpx

payload_simulado = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "0",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15551409009",
                            "phone_number_id": "1270095726182762",
                        },
                        "contacts": [
                            {
                                "profile": {"name": "Alexander"},
                                "wa_id": "50760348962",
                            }
                        ],
                        "messages": [
                            {
                                "from": "50760348962",
                                "id": "wamid.PRUEBA123",
                                "timestamp": "1786412949",
                                "type": "text",
                                "text": {"body": "Hola, quiero saber cuáles son mis paquetes. Mi código es CBC-0006"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

respuesta = httpx.post(
    "http://127.0.0.1:8000/webhook",
    json=payload_simulado,
)

print("Status code:", respuesta.status_code)
print("Respuesta:", respuesta.json())