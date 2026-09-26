# Estado — Vigía

Actualizado: 2026-09-26 (post smoke test real)

- Fase: **MVP funcional de punta a punta verificado en vivo**. Tasks 0-10 ejecutadas y merged. Pendiente: activar systemd timers (decisión del orquestador/diego), deploy del sitio y validación comercial (Task 11 del plan v2).
- Smoke real (2026-09-26): catálogo 6 proveedores / 8 fuentes cargadas; run completo **8/8 procesadas, 0 errores**; segundo run idempotente (0 changes); sitio generado (14 páginas, site/); clasificador real con Ollama qwen3.5:9b → veredicto `pricing` correcto en diff de prueba (20s de latencia con modelo en frío).
- Fixes derivados del smoke (evidencia real): CDNs que sirven gzip crudo → descompresión defensiva; feeds >2MB (Cloudflare changelog 7.7MB) → parseo del prefijo truncado en frontera de ítem; DEFAULT_MODEL cambiado a qwen3.5:9b (ya presente en el host).
- Suite: 113/113 PASS en Python 3.12. Bloques 1-5 revisados por Sol (rondas 1-4 según bloque, con escalación a Opus 5.5 en el bloque 3).
- Kanban de validación (Wiki/go-kill.md): GO ≥300 suscriptores + ≥5 pago; KILL <100 y 0 pagos tras 3 comunidades.
