# Preflight de Fuentes — Task 0

**Fecha:** 2026-09-25  
**Ejecutor:** Sonnet 5 (Bloque 1)

## Resumen

Probadas 9 URLs candidatas según Revisión v2 del plan. **Resultado:** 8 fuentes válidas de 7 proveedores únicos, cumple gate (≥8 fuentes).

## Tabla de Resultados

| Proveedor | URL Final | Código | Content-Type | Formato | robots.txt | Fixture | Decisión | Motivo |
|-----------|-----------|--------|--------------|---------|------------|---------|----------|--------|
| Stripe (blog) | https://stripe.com/blog/changelog | 200 | text/html; charset=utf-8 | HTML | ALLOW | stripe-blog.html | **IN** | Página de changelog oficial, selector extraíble |
| Stripe (docs) | https://docs.stripe.com/changelog | 200 | text/html; charset=utf-8 | HTML | ALLOW | stripe-docs.html | **IN** | Changelog de API docs, complementa el blog |
| AWS | https://aws.amazon.com/about-aws/whats-new/recent/feed/ | 200 | application/rss+xml | RSS | ALLOW | aws.xml | **IN** | Feed oficial de novedades (alt: URL original 404, usamos /recent/feed/) |
| Supabase | https://supabase.com/rss.xml | 200 | application/xml | RSS | ALLOW | supabase.xml | **IN** | RSS principal (alt: /changelog/rss.xml 404) |
| Sentry | https://sentry.io/changelog/feed.xml | 200 | application/xml | RSS | ALLOW | sentry.xml | **IN** | Feed de changelog oficial |
| Cloudflare | https://developers.cloudflare.com/changelog/rss/index.xml | 200 | application/xml | RSS | **DENY** | - | **OUT** | robots.txt prohíbe explícitamente, scraping ético |
| GitHub | https://github.blog/changelog/feed/ | 200 | application/rss+xml | RSS | ALLOW | github.xml | **IN** | Feed oficial de changelog de producto |
| Twilio | https://www.twilio.com/en-us/changelog.feed.xml | 200 | text/xml | RSS | ALLOW | twilio.xml | **IN** | Feed de changelog (redirect 443, URL final guardada) |
| Google Cloud | https://docs.cloud.google.com/feeds/gcp-release-notes.xml | 200 | text/xml | Atom | ALLOW | gcp.xml | **IN** | Feed Atom oficial de release notes |

## Detalles de Validación

### robots.txt
Validado con `urllib.robotparser` usando user-agent `vigia/0.1`. Todas las fuentes IN permiten el acceso excepto Cloudflare (DENY explícito).

### Fixtures
Guardados en `tests/fixtures/` con tamaño recortado a ≤50KB. Ficheros reales capturados el 2026-09-25:
- `stripe-blog.html` (50000 bytes)
- `stripe-docs.html` (50000 bytes)
- `aws.xml` (50000 bytes)
- `supabase.xml` (50000 bytes)
- `sentry.xml` (38889 bytes, completo)
- `github.xml` (48141 bytes, completo)
- `twilio.xml` (39850 bytes, completo)
- `gcp.xml` (50000 bytes)

### Correcciones Realizadas

1. **AWS:** URL original `https://aws.amazon.com/about-aws/whats-new/feed/` devolvió 404. Alternativa funcional: `.../recent/feed/` (probadas también `/new/feed/` y `/blogs/aws/feed/`, todas OK, elegimos recent por estar más cerca de la URL original).

2. **Supabase:** URL original `https://supabase.com/changelog/rss.xml` devolvió 404. Alternativa funcional: `https://supabase.com/rss.xml` (RSS principal del sitio).

3. **Cloudflare:** Aunque la URL responde 200 y contiene RSS válido, `robots.txt` del dominio `developers.cloudflare.com` deniega explícitamente el acceso a bots. Descartada por política de scraping ético (AGENTS.md).

## Proveedores Finales (7)

1. **Stripe** (2 fuentes: blog HTML + docs HTML)
2. **AWS** (1 fuente: RSS recent feed)
3. **Supabase** (1 fuente: RSS principal)
4. **Sentry** (1 fuente: RSS changelog)
5. **GitHub** (1 fuente: RSS changelog)
6. **Twilio** (1 fuente: RSS changelog)
7. **Google Cloud** (1 fuente: Atom release notes)

**Total:** 7 proveedores, 8 fuentes activas.

## Gate de Continuación

✅ **PASS** — Se requieren ≥8 fuentes válidas. Conseguidas exactamente 8 (de 7 proveedores únicos). Task 1 puede continuar.

## Próximos Pasos

- Estos proveedores y URLs irán a `config/providers.yaml` en Task 1.
- El selector HTML para Stripe (blog y docs) se definirá tras inspección manual del DOM en Task 3.
- Cloudflare queda descartado del MVP; si en futuro se quiere incluir, requiere contacto directo con el proveedor para obtener permiso de scraping o usar API oficial si existe.
