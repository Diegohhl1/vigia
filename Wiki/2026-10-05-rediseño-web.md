# 2026-10-05 — Rediseño del sitio (opción 1: CSS propio con referencias)

## Decisión
Tras investigar alternativas gratis (ver `.omh/research/vigia-site-templates-20261005-60d7-report.md`: templates MIT, daisyUI/Flowbite, migración a Astro, status pages self-hosted), se eligió **mantener el generador Python** y rediseñar solo el CSS/plantilla de `publish.py`:

- **Referencia estructural:** changelogs de Vercel/Linear — timeline agrupada por día con puntos en línea vertical, badge de severidad + hora + source por entrada.
- **Referencia visual:** tema Vercel dark — fondo `#0a0a0a`, superficies planas `#111113` con shadow-as-border (`inset 0 0 0 1px` en vez de `border`), tipografía con tracking negativo comprimido en titulares, badges pill sin borde, monospace para etiquetas técnicas.
- **Paleta de severidad:** pricing `#e2b344`, breaking `#ff5b4f` (Ship Red de Vercel), minor `#4da3ff`, siempre sobre fondo tintado al 12%.

## Descartadas
- **daisyUI/Flowbite:** exigen toolchain Tailwind (el sitio se autocontiene en un `<style>` inline; los tests prohíben assets externos).
- **Astro:** compensa solo si el sitio crece (páginas por proveedor, búsqueda); hoy son 14 páginas planas.
- **Status pages self-hosted (OpenStatusPage/openstatus):** resuelven uptime, no changelog.

## Implementación (commit 42af562)
- `src/vigia/publish.py`: `_SITE_CSS` reescrito; `_provider_html` agrupa por día (`detected_at[:10]`); index con `<title>` descriptivo.
- Contratos de tests respetados: badges `badge-minor`/`badge-pricing`, read-tracker (localStorage + IntersectionObserver), index sin scripts, sin assets externos.
- Suite: 119/119 PASS. Sitio regenerado (14 páginas) y verificado visualmente (screenshots headless Chrome del index y de /providers/sentry/).
