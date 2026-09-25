# Challenge del plan MVP — Sol (gpt-5.6-sol), 2026-09-25

Veredicto: **REVISE** — el plan es ejecutable pero con enmiendas obligatorias. Nota completa del challenge en la sesión de codex del 25-sep (12:59+). Enmiendas incorporadas como sección "Revisión v2" del plan.

## Hallazgos que cambian diseño (no parches)

1. **7 URLs de feed eran incorrectas o subóptimas** (Cloudflare, GitHub, Twilio, Sentry, Google Cloud, Azure, Vercel). Azure además prohíbe /blog/feed/ en robots.txt. → Task 0 preflight de fuentes con evidencia real, empezar con 4-6 proveedores, no 12.
2. **RSS como documento completo genera falsos cambios** → ingestión por entrada (guid/link) con tabla `entries`.
3. **El diff solo-extra-añadidos pierde ELIMINACIONES** (quitar un plan/API es breaking) → estructura added/removed/before/after.
4. **Ollama soporta structured outputs nativo** (`format` con JSON Schema, temperature=0) en vez de parsear el primer JSON.
5. **Telegram no es el canal del negocio** — el KPI es suscriptores EMAIL → digest por email (proveedor con formulario alojado), Telegram queda como canal interno de Diego.
6. **Falta el eslabón comercial**: landing + email capture + payment link. Sin eso el reloj de validación no puede arrancar → nueva Task 11.
7. **Evaluación del clasificador**: 50-100 casos etiquetados con gate (recall ≥90% en pricing/breaking, FP <10%) antes de autopublicar — un 7B clasifica mal sin evaluar.
8. Contradicciones internas corregidas (primera ingesta = baseline con 0 cambios; send_digest separado de record_delivery; dos units systemd; Wiki la actualiza Claude, no los ejecutores).

## YAGNI aplicado

Fuera del MVP: 12 proveedores nominales (→4-6 verificados), scraper HTML universal, browser automation, history.json, score sin regla de uso, instalador elaborado antes del soak.

## Gate de arranque

No empezar Task 1 hasta que Task 0 cierre con ≥4 proveedores y ≥8 fuentes válidas con fixtures reales, cero bloqueos robots/ToS conocidos. El reloj GO/KILL de 60 días solo arranca cuando Task 11 (web+email+pago) esté operativa.
