# Estado — Vigía

Actualizado: 2026-09-25 (post Bloque 2)

- Fase: **Bloques 1-2 completados y merged a main**. Bloque 3 = Tasks 5, 5b, 6 (clasificador structured outputs, evaluación de 50-100 casos, orquestador).
- Repo: `~/Desktop/vigia` → github.com/Diegohhl1/vigia (main). Bloque 1: 25/25; Bloque 2: 48/48 PASS en Python 3.12.
- Fuentes validadas: 8 fuentes / 6 proveedores (AWS×2, GCP, GitHub, Twilio, Cloudflare×2, Sentry). Evidencia: `docs/preflight-fuentes.md`.
- Bloque 2: catálogo YAML upsert, fetch por entrada con baseline durable/ETag/Last-Modified/retry/rate limit/robots, diff bidireccional con presupuesto único 4000. Sol aprobó tras 2 ciclos REVISE y fixes adicionales verificados.
- Lección: comprobar rutas de robots individualmente aunque el parser se cachee por dominio; streaming debe limitar cuerpos en todos los status y conservar retry HTTP 429/5xx.
- Cadencia adaptativa: tras REVISE, revisión individual hasta dos slices limpias seguidas; luego vuelve a revisión de bloque.
