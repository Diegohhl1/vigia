# Smoke Test — Vigía

Checklist de verificación de ejecución real antes de activar systemd timers.

## Prerrequisitos

- [ ] Repo clonado en `/home/diego/Desktop/vigia`
- [ ] venv creado y dependencias instaladas: `python3.12 -m venv .venv && .venv/bin/pip install -e .`
- [ ] Ollama corriendo: `curl -s http://127.0.0.1:11434/api/version`
- [ ] Modelo local disponible: `ollama list | grep qwen3.5:9b-hermes-64k`
- [ ] DB creado y catálogo cargado: `ls -lh vigia.sqlite3`
- [ ] Credenciales Telegram configuradas: `test -f config/secrets.toml`

## Pasos del smoke test

### 1. Smoke limitado (2 fuentes)

```bash
cd /home/diego/Desktop/vigia
.venv/bin/vigia smoke --limit 2
```

**Esperado:**
- `Sources processed: 2`
- `Errors: 0` (o errores de red comprensibles como timeout)
- `Duration:` < 30s
- Exit code 0

### 2. Run completo (todas las fuentes)

```bash
.venv/bin/vigia run
```

**Esperado:**
- Todas las fuentes enabled procesadas (8 fuentes / 6 proveedores según Wiki/estado.md)
- Changes detectados si hay ediciones reales (o 0 si todo está estable)
- Exit code 0

### 3. Generación del sitio estático

```bash
.venv/bin/vigia build-site
```

**Esperado:**
- Archivos generados en `public/`
- `public/index.html`, `public/feed.xml`, `public/providers/<slug>.html`
- HTML válido (spot check)

### 4. Digest a Telegram

```bash
.venv/bin/vigia digest --chat-id <ID_CANAL_TEST>
```

**Esperado:**
- Mensaje enviado a Telegram con formato correcto
- Links a cada change clicables
- Truncado si >4096 caracteres
- Exit code 0

## Post-smoke

Si todos los pasos pasan:
- [ ] Ejecutar `ops/install.sh` (sin `--enable` todavía)
- [ ] Verificar que units están instalados: `systemctl --user list-unit-files | grep vigia`
- [ ] Verificar que timers aparecen: `systemctl --user list-timers`
- [ ] **NO activar timers** hasta decisión del orquestador

Si algún paso falla: documentar el error, investigar la causa, no proceder a systemd.
