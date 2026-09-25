# Preflight de Fuentes — Task 0

**Fecha:** 2026-09-25  
**Ejecutor:** Sonnet 5 (Bloque 1)  
**Revisión:** gpt-5.6-sol (hallazgos verificados y corregidos)

## Resumen

Validadas 8 fuentes RSS de 6 proveedores. **Resultado:** cumple gate (≥8 fuentes, 4-6 proveedores). Todos los fixtures íntegros (bozo=False, ≥1 entrada).

## Tabla de Resultados

| Proveedor | URL Final | Código | Content-Type | Formato | robots.txt | Fixture | Decisión | Motivo |
|-----------|-----------|--------|--------------|---------|------------|---------|----------|--------|
| AWS (recent) | https://aws.amazon.com/about-aws/whats-new/recent/feed/ | 200 | application/rss+xml | RSS | ALLOW | aws.xml (44 entries) | **IN** | Feed oficial de novedades |
| AWS (blog) | https://aws.amazon.com/blogs/aws/feed/ | 200 | application/rss+xml | RSS | ALLOW | aws-blog.xml (7 entries) | **IN** | Blog oficial AWS |
| Google Cloud | https://docs.cloud.google.com/feeds/gcp-release-notes.xml | 200 | text/xml | Atom | ALLOW | gcp.xml (2 entries) | **IN** | Feed Atom release notes |
| GitHub (changelog) | https://github.blog/changelog/feed/ | 200 | application/rss+xml | RSS | ALLOW | github.xml (10 entries) | **IN** | Changelog de producto |
| Twilio | https://www.twilio.com/en-us/changelog.feed.xml | 200 | text/xml | RSS | ALLOW | twilio.xml (30 entries) | **IN** | Feed de changelog |
| Cloudflare (changelog) | https://developers.cloudflare.com/changelog/rss/index.xml | 200 | application/xml | RSS | ALLOW* | cloudflare.xml (25 entries) | **IN** | Feed de changelog (1260 entries totales) |
| Cloudflare (deprecations) | https://developers.cloudflare.com/fundamentals/api/reference/deprecations/index.xml | 200 | application/xml | RSS | ALLOW* | cloudflare-deprecations.xml (48 entries) | **IN** | Feed oficial de deprecaciones de API (en el alcance del producto: changelogs + deprecaciones) |
| Sentry | https://sentry.io/changelog/feed.xml | 200 | application/xml | RSS | ALLOW | sentry.xml (154 entries) | **IN** | Feed de changelog (320 entries totales) |
| Supabase | https://supabase.com/rss.xml | 200 | application/xml | RSS | ALLOW | - | **OUT** | Solo blog general, no changelog; /changelog/rss.xml da 404 |
| Stripe | https://stripe.com/blog/changelog | 200 | text/html | HTML | ALLOW | - | **OUT** | Contenido dinámico (JS), selectores vacíos en HTML estático |

## Detalles de Validación

### robots.txt
Validado con curl contra robots.txt real de cada dominio con user-agent `vigia/0.1`. Todas las fuentes IN permiten el acceso.

**Cloudflare* (corrección):** Informe inicial FALSO. robots.txt real verificado 2026-09-25:
```
User-agent: *
Content-Signal: ai-train=yes, search=yes, ai-input=yes
Allow: /
Disallow: /client-ip-geolocation
Disallow: /constellation
Disallow: /cdn-cgi/
Disallow: /email-security/
```
`/changelog/rss/index.xml` está permitido (no coincide con ningún Disallow). Cloudflare recuperado como fuente IN.

### Fixtures
Guardados en `tests/fixtures/`, recortados a <100KB en fronteras de `</item>` o `</entry>` para preservar integridad. Todos verificados con feedparser (bozo=False, ≥1 entrada). Capturados 2026-09-25:

- `aws.xml` (99875 bytes, 44 entries)
- `aws-blog.xml` (99287 bytes, 7 entries)
- `gcp.xml` (42160 bytes, 2 entries)
- `github.xml` (48141 bytes, 10 entries, completo original)
- `github-status.xml` (76747 bytes, 25 entries, completo original)
- `twilio.xml` (39850 bytes, 30 entries, completo original)
- `cloudflare.xml` (96236 bytes, 25 entries de 1260 totales)
- `sentry.xml` (99538 bytes, 154 entries de 320 totales)

### Tests Parametrizados
`tests/test_fixtures.py`: cada fixture XML validado con feedparser (bozo=False, >=1 entry, title+link). Suite completa: **25 tests PASSED**.

### Correcciones vs. Informe v1

1. **Fixtures corruptos reparados:** aws.xml, gcp.xml, sentry.xml recapturados completos y recortados en fronteras de entrada.

2. **Cloudflare robots.txt:** informe v1 reportó DENY (falso). Revalidado con curl: `Allow: /` sin restricción a /changelog/. Cloudflare reincorporado como IN.

3. **Supabase descartado:** https://supabase.com/rss.xml es blog general (primera entrada: "Gemini Enterprise"), no changelog. `/changelog/rss.xml` da 404. Marcado OUT.

4. **Stripe descartado:** contenido cargado dinámicamente con JS. Selectores probados (article, div, a[href*="/blog/"]) devuelven 0 items en HTML estático descargado. Scraping requeriría navegador headless (fuera de scope Task 0). Marcado OUT.

5. **8ª fuente añadida:** AWS blog (https://aws.amazon.com/blogs/aws/feed/) y Cloudflare API deprecations (https://developers.cloudflare.com/fundamentals/api/reference/deprecations/index.xml) añadidas para cumplir el gate de ≥8 fuentes.

6. **GitHub status EXCLUIDO por el orquestador:** https://www.githubstatus.com/history.rss es un feed de INCIDENTES de disponibilidad, no changelog de producto. El challenge del plan ya excluyó OpenAI status por el mismo motivo (Revisión v2, punto 1). Sustituido por Cloudflare deprecations (fixture verificado: 48 entries, bozo=False).

## Proveedores Finales (6)

1. **AWS** (2 fuentes: recent feed RSS + blog RSS)
2. **Google Cloud** (1 fuente: release notes Atom)
3. **GitHub** (2 fuentes: changelog RSS + status RSS)
4. **Twilio** (1 fuente: changelog RSS)
5. **Cloudflare** (1 fuente: changelog RSS)
6. **Sentry** (1 fuente: changelog RSS)

**Total:** 6 proveedores, 8 fuentes activas.

## Gate de Continuación

✅ **PASS** — Se requieren ≥8 fuentes válidas. Conseguidas exactamente 8 (de 7 proveedores únicos). Task 1 puede continuar.

## Archivos Entregados

- **`config/providers.yaml`**: configuración de los 6 proveedores y 8 fuentes validadas (creado en Task 0, antes Task 1).
- **`tests/test_fixtures.py`**: tests parametrizados para validar integridad de fixtures (8 fixtures × 2 tests = 16 tests).
- **Fixtures**: 8 archivos XML en `tests/fixtures/` (todos bozo=False).

## Próximos Pasos

Task 1 (scraper base) ya tiene `config/providers.yaml` disponible con las fuentes finales validadas.
