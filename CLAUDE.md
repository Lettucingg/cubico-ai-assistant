# Cubico AI Assistant — Contexto del proyecto

## Qué es esto
Bot de WhatsApp para Cubico (empresa de paquetería en Panamá), construido con 
FastAPI + APScheduler + Claude AI. Corre en un servidor Hetzner con PM2.

## Stack
- Python / FastAPI
- APScheduler (scheduler de tareas)
- SQLAlchemy + PostgreSQL
- WhatsApp Cloud API (Meta)
- Claude AI (Anthropic) como motor del bot
- PM2 para gestión de procesos en producción

## Estructura clave
- app/scheduler.py — tareas programadas (ping diario 8am, revisión de pagos c/30min)
- app/api/whatsapp.py — webhook y lógica de mensajes
- app/ai/ — lógica de Claude AI
- app/db/ — modelos y sesiones
- app/tools/ — herramientas (facturas, paquetes, etc.)
- app/api/panel.py — backend del panel de administración (en desarrollo)

## Timezone
Siempre usar America/Panama. El servidor corre en UTC.

## Deploy
git push a main → SSH al servidor → git pull → pm2 restart cubico-bot

## Variables de entorno importantes
Ver .env.example — nunca commitear .env real.
PANEL_USUARIO y PANEL_CONTRASENA son requeridas para el panel web.

## Convenciones
- Mensajes fijos al usuario (ping, confirmaciones) van hardcodeados, no llaman a Claude API
- Logs con logging estándar de Python, nivel INFO/ERROR
- Zona horaria siempre explícita en CronTrigger
