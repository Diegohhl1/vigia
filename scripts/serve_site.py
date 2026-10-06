#!/usr/bin/env python
"""Servidor estático para el sitio de Vigía.

``python -m http.server`` no atraviesa el symlink de publicación de
``build_site`` (``SimpleHTTPRequestHandler.translate_path`` deja de resolver
en cuanto el primer componente del path es un symlink), así que ``/aws/``
devolvía 404 aunque ``site/providers/aws/`` existiera. Este servidor traduce
las rutas contra ``os.path.realpath(out_dir)`` en cada petición, de modo que
el swap atómico del symlink (nuevo .site-<ns> en cada build) se sirve sin
reiniciar.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os


class VigiaRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        # Realpath en cada petición: sigue el symlink de publicación actual.
        self.directory = os.path.realpath(self.directory)
        return super().translate_path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Vigía static site")
    parser.add_argument("--directory", default="site", help="site directory (may be a symlink)")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()

    handler = functools.partial(VigiaRequestHandler, directory=os.path.abspath(args.directory))
    server = http.server.ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"vigia-site: serving {args.directory} on http://{args.bind}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
