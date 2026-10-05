# Read tracking sin cuentas — 2026-10-05

## Decisión

Diferenciar noticias nuevas/leídas en el sitio público usando **localStorage, no cookies** y sin cuentas:

- Cada noticia lleva `data-change-id`; script embebido solo en páginas de proveedor (el index sigue sin JS).
- Marca automática: `IntersectionObserver` con umbral 0.5 + ~1s de permanencia en pantalla (evita marcar por un scroll rápido).
- Píldora NEW en no leídas; leídas atenuadas (opacity .45).
- Botón "Hide read" / "Show read" cuyo estado persiste (clave `vigia_hide_read`).
- Tope de 500 IDs en `vigia_read` para que no crezca sin límite.

## Por qué localStorage y no cookies

Mismo efecto para el visitante, pero no viaja al servidor (cero superficie), no caduca y no activa requisitos de banner de consentimiento. Si en el futuro hay cuentas (Pro), el tracking puede migrar al perfil del usuario.

## Implementación

`src/vigia/publish.py` (`_SITE_READ_TRACKER` + CSS `.change.read` / `.new-pill` / `body.hide-read`), tests en `tests/test_publish.py` (el index debe seguir sin `<script>`). Commit 54584b9.
