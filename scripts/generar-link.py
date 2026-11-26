#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generar-link.py — Depositar una contraseña en un agente sin que pase por el chat.

Levanta un formulario de UN SOLO USO: la persona abre el link, escribe su
contraseña, y el valor viaja sólo hasta este proceso, que lo escribe donde el
agente lo va a leer. Nunca entra en un chat, en un log, ni en el contexto de un
modelo.

Uso mínimo (archivo local):
    python3 generar-link.py --destino ~/.agente/.secrets/micuenta.md \
        --cuenta persona@ejemplo.com --descripcion "Cuenta Google"

Dentro de un contenedor Docker (el agente lo lee de ahí):
    python3 generar-link.py --contenedor agente-x \
        --destino /opt/data/.secrets/micuenta.md \
        --cuenta persona@ejemplo.com --descripcion "Cuenta Google"

Con link público HTTPS (Cloudflare quick tunnel, requiere `cloudflared`):
    python3 generar-link.py ... --tunel

Opciones:
    --destino RUTA        Dónde se escribe el secreto (obligatorio).
    --contenedor NOMBRE   Si va dentro de un contenedor (docker exec -i).
    --cuenta TEXTO        Identificador de la cuenta (va documentado, no es secreto).
    --descripcion TEXTO   Título del archivo / para qué es.
    --formato md|env|txt  md = archivo comentado (default), env = VAR=valor, txt = sólo el valor.
    --variable NOMBRE     Nombre de la variable si --formato env (default: SECRETO).
    --bind IP             Interfaz donde escuchar (default 127.0.0.1).
    --puerto N            Puerto (default 8791).
    --ttl SEGUNDOS        Vida del link (default 900 = 15 min).
    --tunel               Abre un quick tunnel de Cloudflare y muestra el link HTTPS.
"""

from __future__ import annotations

import argparse
import hmac
import html
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


def cuerpo_md(cuenta: str, descripcion: str) -> str:
    return (
        f"# {descripcion}\n\n"
        f"- Cuenta: {cuenta}\n"
        "- Secreto: "
    )


def armar_archivo(valor: str, a: argparse.Namespace) -> str:
    if a.formato == "env":
        return f"{a.variable}={valor}\n"
    if a.formato == "txt":
        return valor + "\n"
    return (
        f"# {a.descripcion}\n\n"
        f"- Cuenta: {a.cuenta}\n"
        f"- Secreto: {valor}\n\n"
        "Este archivo no se copia a otros agentes ni va dentro de skills/ o memories/.\n"
        "Si el secreto se filtró (chat, captura, log), se rota y se vuelve a depositar.\n"
    )


def escribir_local(ruta: str, contenido: str) -> tuple[bool, str]:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        os.chmod(ruta, 0o600)
        st = os.stat(ruta)
        return True, f"{oct(st.st_mode & 0o777)} {st.st_uid}:{st.st_gid} {len(contenido)}b"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def escribir_contenedor(cont: str, ruta: str, contenido: str) -> tuple[bool, str]:
    """El contenido viaja por stdin: no aparece en `ps` ni en el historial."""
    script = (
        f"mkdir -p {os.path.dirname(ruta) or '/tmp'}\n"
        "umask 077\n"
        f"cat > {ruta}.tmp.$$ && mv {ruta}.tmp.$$ {ruta} && chmod 600 {ruta}\n"
    )
    r = subprocess.run(
        ["docker", "exec", "-i", cont, "sh", "-c", script],
        input=contenido, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        return False, (r.stderr or "error al escribir").strip()[:200]
    chk = subprocess.run(
        ["docker", "exec", cont, "sh", "-c", f"stat -c '%a %U:%G %s' {ruta}"],
        capture_output=True, text=True, timeout=60,
    )
    return True, chk.stdout.strip()


PAGINA = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Depositar secreto</title>
<style>
 :root{{color-scheme:light dark}}
 body{{font-family:system-ui,-apple-system,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1.2rem;line-height:1.5}}
 h1{{font-size:1.3rem;margin-bottom:1rem}} .dato{{background:#8881;padding:.8rem 1rem;border-radius:.6rem;font-size:.9rem}}
 input{{width:100%;padding:.75rem;font-size:1rem;border:1px solid #8888;border-radius:.6rem;box-sizing:border-box;background:#8881}}
 button{{margin-top:1.1rem;padding:.85rem 1.5rem;font-size:1rem;border:0;border-radius:.6rem;background:#111;color:#fff;cursor:pointer}}
 @media (prefers-color-scheme:dark){{button{{background:#eee;color:#111}}}}
 .aviso{{font-size:.83rem;opacity:.75;margin-top:1.2rem}}
</style>
<h1>Depositar contraseña</h1>
<div class="dato"><b>Cuenta:</b> {cuenta}<br><b>Destino:</b> {destino}</div>
<form method="post" autocomplete="off">
 <p><label for="p"><b>Contraseña</b></label>
 <input id="p" name="p" type="password" autocomplete="new-password" spellcheck="false" autofocus></p>
 <button type="submit">Guardar</button>
</form>
<p class="aviso">Link de un solo uso, vence en {minutos} minutos. El valor no se muestra, no se
registra y no queda en ningún log. No lo pegues en un chat.</p>
</html>"""

EXITO = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:32rem;margin:3rem auto;padding:0 1.2rem;line-height:1.5">
<h1>✅ Guardado</h1><p>El secreto quedó en <code>{destino}</code> ({detalle}).</p>
<p>Podés cerrar esta ventana.</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    args: argparse.Namespace
    token: str
    evento = threading.Event()
    ultimo: dict = {}

    def log_message(self, *a):  # nunca loguear el path (lleva el token) ni el cuerpo
        return

    def _simple(self, code: int, texto: str = ""):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if texto:
            self.wfile.write(texto.encode())

    def do_GET(self):
        if not hmac.compare_digest(self.path.strip("/"), self.token):
            return self._simple(404, "no")
        a = self.args
        cuerpo = PAGINA.format(
            cuenta=html.escape(a.cuenta or "(sin especificar)"),
            destino=html.escape(a.destino),
            minutos=max(1, a.ttl // 60),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        if not hmac.compare_digest(self.path.strip("/"), self.token):
            return self._simple(404, "no")
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._simple(400, "largo invalido")
        if largo <= 0 or largo > 8192:
            return self._simple(400, "cuerpo invalido")
        datos = parse_qs(self.rfile.read(largo).decode("utf-8", "replace"))
        valor = (datos.get("p") or [""])[0]
        if not valor.strip():
            return self._simple(400, "vacia")
        a = self.args
        contenido = armar_archivo(valor, a)
        if a.contenedor:
            ok, detalle = escribir_contenedor(a.contenedor, a.destino, contenido)
        else:
            ok, detalle = escribir_local(a.destino, contenido)
        if not ok:
            print(f"[generar-link] ✗ {detalle}", flush=True)
            return self._simple(500, "error")
        self.ultimo = {"detalle": detalle}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(EXITO.format(destino=html.escape(a.destino), detalle=html.escape(detalle)).encode())
        print(f"[generar-link] ✓ escrito {a.destino} ({detalle})", flush=True)
        Handler.evento.set()


def abrir_tunel(puerto: int) -> tuple[subprocess.Popen | None, str]:
    if not shutil.which("cloudflared"):
        print("[generar-link] aviso: no hay cloudflared, sigo sin túnel", flush=True)
        return None, ""
    p = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{puerto}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    inicio = time.time()
    patron = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    while time.time() - inicio < 40:
        linea = p.stdout.readline() if p.stdout else ""
        if not linea:
            break
        m = patron.search(linea)
        if m:
            return p, m.group(0)
    return p, ""


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description="Formulario de un solo uso para depositar un secreto.")
    ap.add_argument("--destino", required=True)
    ap.add_argument("--contenedor", default="")
    ap.add_argument("--cuenta", default="")
    ap.add_argument("--descripcion", default="Acceso")
    ap.add_argument("--formato", choices=["md", "env", "txt"], default="md")
    ap.add_argument("--variable", default="SECRETO")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=8791)
    ap.add_argument("--ttl", type=int, default=900)
    ap.add_argument("--tunel", action="store_true")
    a = ap.parse_args()

    token = secrets.token_urlsafe(24)
    Handler.args = a
    Handler.token = token

    srv = ThreadingHTTPServer((a.bind, a.puerto), Handler)
    srv.timeout = 5
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"[generar-link] escuchando en http://{a.bind}:{a.puerto}/{token}", flush=True)
    destino_txt = f"{a.contenedor}:{a.destino}" if a.contenedor else a.destino
    print(f"[generar-link] destino: {destino_txt}", flush=True)
    print(f"[generar-link] vence en {a.ttl // 60} min, un solo uso", flush=True)

    proc, publico = (None, "")
    if a.tunel:
        proc, publico = abrir_tunel(a.puerto)
        if publico:
            print(f"[generar-link] LINK PÚBLICO: {publico}/{token}", flush=True)
        else:
            print("[generar-link] aviso: no pude abrir el túnel", flush=True)

    try:
        if Handler.evento.wait(a.ttl):
            print("[generar-link] listo, cerrando (un solo uso)", flush=True)
            return 0
        print("[generar-link] venció sin uso", flush=True)
        return 1
    finally:
        srv.shutdown()
        if proc:
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
