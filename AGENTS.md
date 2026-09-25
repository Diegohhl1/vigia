# AGENTS.md — Protocolo de agentes — Vigía

Herramienta que vigila precios, changelogs, deprecaciones y términos de servicio de proveedores cloud/SaaS, clasifica cada cambio por impacto con un LLM local y publica alertas (web con historial por proveedor, RSS, digest por email/Telegram). Producto B2B técnico en marcha blanca: gratis (digest semanal + 3 servicios) / Pro $12/mes (catálogo completo + alertas instantáneas) / Team $49/mes (URLs propias + API + webhooks firmados).

## Fuente de verdad

1. **Antes de actuar:** leer `Wiki/index.md` y `Wiki/estado.md`.
2. **Código y estado actual:** verificar en el repositorio y con pruebas reales. El README describe la arquitectura; el Wiki conserva el *porqué*.
3. **Tras una decisión, investigación o experimento relevante:** crear o actualizar la nota adecuada en `Wiki/` y enlazarla desde `Wiki/index.md`.
4. **Plan de ejecución:** `docs/superpowers/plans/2026-09-25-mvp.md` (TDD, un commit por tarea).

## Descubrimiento de código — el grafo

Esta máquina tiene **codebase-memory-mcp**. Cuando el repo tenga código indexable:

- Antes de explorar código, usar primero el grafo (`~/.local/bin/codebase-memory-mcp cli ...`).
- Tras cambiar código, reindexar.

## Reglas operativas

- **Scraping ético:** solo páginas públicas, respetando `robots.txt` y `ToS` del proveedor. Prohibido scrapear contenido tras login. Si un proveedor ofrece API/RSS de changelog, usarla antes de scrapear HTML.
- **Coste de inferencia:** la clasificación de impacto usa el LLM local (Ollama central vía systemd). Prohibido llamar a APIs de pago por cada check; LLM remoto solo para re-clasificación puntual.
- **Dinero:** el cálculo de facturación (límites de plan, contadores de uso) lo revisa Sol en cada bloque que lo toque.
- **Git:** commits por tarea, push a `origin/main` cuando la suite esté verde. Repo en `github.com/Diegohhl1/vigia`.
- **Sin secretos en git:** credenciales en `config/secrets.*` (gitignored) o keyring del sistema.
