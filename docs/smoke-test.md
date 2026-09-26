# Smoke Test — Vigía

Checklist de verificación de ejecución real antes de activar systemd timers.

## Prerrequisitos

- [ ] Repo en `/home/diego/Desktop/vigia`
- [ ] venv creado y dependencias instaladas: `python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- [ ] Ollama corriendo: `curl -s http://127.0.0.1:11434/api/version`
- [ ] Modelo REAL del clasificador disponible: `ollama list | grep qwen2.5:7b` (DEFAULT_MODEL en src/vigia/classify.py). Si falta: `ollama pull qwen2.5:7b`
- [ ] Catálogo cargado en la BD: `.venv/bin/python -c "from vigia.db import get_conn; from vigia.providers import load_providers; c = get_conn('vigia.sqlite3'); print(load_providers(c, 'config/providers.yaml'))"`
- [ ] Credenciales Telegram en el entorno o en `config/secrets.env`: `VIGIA_TG_TOKEN`, `VIGIA_TG_CHAT_ID` (solo para el paso 4)

## Pasos del smoke test

### 1. Smoke limitado (2 fuentes)

```bash
cd /home/diego/Desktop/vigia
.venv/bin/vigia smoke --limit 2
```

**Esperado:**
- `Sources processed: 2`
- `Errors: 0`
- Duración: puede superar 30s (rate limit de 2s/host entre robots.txt y feed, más timeouts)
- Exit code 0
- Nota: la primera pasada es baseline → `Changes created: 0` es lo esperado

### 2. Run completo (todas las fuentes)

```bash
.venv/bin/vigia run
```

**Esperado:**
- Las 8 fuentes enabled procesadas (6 proveedores según Wiki/estado.md)
- Exit code 0 aunque HAYA errores puntuales de red: `run` sale 1 solo si errors es no vacío; ante timeouts transitorios re-ejecutar antes de investigar
- Veredictos: con Ollama caído NO aparece error — los changes quedan `needs_review` (verificar en SQLite: `SELECT verdict, summary, review_status FROM changes ORDER BY id DESC LIMIT 10`)

### 3. Generación del sitio estático

```bash
.venv/bin/vigia build-site
```

**Esperado:**
- `Pages written: N` con N ≥ 1
- Ficheros en `site/`: `index.html`, `rss.xml`, `providers/<slug>/index.html`, `providers/<slug>/history.json`
- HTML válido (spot check) y sin changes `needs_review` publicados

### 4. Digest a Telegram

```bash
VIGIA_TG_TOKEN=... VIGIA_TG_CHAT_ID=... .venv/bin/vigia digest
```

**Esperado:**
- `Digest sent` y mensaje en el chat con formato correcto (agrupado por proveedor)
- Sin cambios relevantes → mensaje "Sin cambios relevantes en las últimas 24h" (también cuenta como éxito)
- Exit code 0; si falla el envío → stderr `Digest send failed` y exit 1

## Post-smoke

Si todos los pasos pasan:
- [ ] Ejecutar `ops/install.sh` (sin `--enable` todavía)
- [ ] Verificar units instalados: `systemctl --user list-unit-files | grep vigia`
- [ ] Verificar timers: `systemctl --user list-timers`
- [ ] **NO activar timers** hasta decisión del orquestador

Si algún paso falla: documentar el error, investigar la causa, no proceder a systemd.
