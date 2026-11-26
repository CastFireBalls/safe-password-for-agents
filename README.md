# Safe password for agents

Herramientas para darle una contraseña a un agente de IA **sin que el valor pase
por un chat, por un log o por el contexto de un modelo**.

El problema concreto: si le pegás una contraseña a un agente en el chat, ese
valor viaja al servidor de mensajería, queda guardado en el historial de la
conversación y se envía al proveedor del modelo. Ya está expuesta, aunque el
agente se niegue a usarla.

Este paquete resuelve el paso previo: **depositar el secreto** de forma segura,
para que el agente lo lea desde un archivo con permisos `600` cuando lo necesite.

## Cómo funciona

```
persona ──[link de un solo uso, HTTPS]──▶ servidor ──▶ archivo 600 ──▶ agente
                (o terminal con read -s)                 │
                                                         └─ nunca pasa por el chat
```

## Uso rápido

### 1. Link de un solo uso (sirve desde el teléfono)

```bash
python3 scripts/generar-link.py \
  --destino /opt/data/.secrets/gmail.md \
  --contenedor agente-x \
  --cuenta persona@ejemplo.com \
  --descripcion "Cuenta Google" \
  --tunel
```

Salida:

```
[generar-link] escuchando en http://127.0.0.1:8791/<token>
[generar-link] LINK PÚBLICO: https://algo-random.trycloudflare.com/<token>
[generar-link] vence en 15 min, un solo uso
```

Le pasás el link a la persona, escribe la contraseña, toca Guardar, y el proceso
se cierra solo.

Sin `--tunel` sólo escucha en `127.0.0.1` (usalo por SSH o por una VPN como
Tailscale). Con `--tunel` necesita [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
y da un link HTTPS público sin abrir puertos.

### 2. Terminal del operador

```bash
./scripts/depositar-secreto.sh \
  --contenedor agente-x \
  --destino /opt/data/.secrets/gmail.md \
  --cuenta persona@ejemplo.com \
  --descripcion "Cuenta Google"
```

Pide la contraseña dos veces sin mostrarla y la escribe con permisos `600`.

### 3. Archivo local (sin Docker)

```bash
python3 scripts/generar-link.py --destino ~/.agente/.secrets/api.md \
  --cuenta yo@ejemplo.com --descripcion "API token" --formato env --variable API_KEY
```

Formatos: `md` (archivo comentado, por defecto), `env` (`VAR=valor`), `txt` (sólo
el valor).

## Controles de seguridad

| Control | Qué evita |
|---|---|
| Token aleatorio en la URL | Que alguien escanee el puerto y encuentre el formulario |
| Un solo uso (el proceso se cierra) | Que el link se reuse o quede publicado |
| TTL de 15 minutos | Ventana de exposición acotada |
| Escucha en `127.0.0.1` por defecto | Exponer el formulario sin querer |
| Valor por `stdin` | Que la contraseña aparezca en `ps` o en el historial |
| Permisos `600` | Que otro usuario del servidor lo lea |
| Sin logging del cuerpo ni del path | Que la contraseña quede en un log |
| `--tunel` opcional y explícito | Publicar sin TLS a la intranet pública |

## Verificación

```bash
stat -c '%a %U:%G %s bytes' /opt/data/.secrets/gmail.md   # 600 usuario:grupo
grep -c 'Secreto:' /opt/data/.secrets/gmail.md            # 1 (sin mostrar el valor)
grep -m1 'Cuenta:' /opt/data/.secrets/gmail.md            # la cuenta esperada
```

## Requisitos

- Python 3.9+ (sólo librería estándar; no instala nada)
- `docker` si el secreto va dentro de un contenedor
- `cloudflared` sólo si usás `--tunel`

## Qué NO hace

- No cifra el archivo en reposo: es un archivo `600`. Si necesitás cifrado, usá un
  gestor de contraseñas con UI (`hermes vault`, 1Password, Bitwarden), que guarda
  cifrado e inyecta el valor sin que el agente lo vea.
- No rota contraseñas solo. Si una contraseña se filtró, se rota a mano y se
  vuelve a depositar.
- No reemplaza el 2FA: el segundo factor lo aprueba la persona dueña de la cuenta.

## Si una contraseña ya se filtró

1. Rotarla **antes** de cualquier otra cosa.
2. Buscar líneas con forma de contraseña (8-40 caracteres alfanuméricos, sin
   espacios) en la base de conversaciones, en `skills/`, en `memories/` y en los
   logs — imprimiendo sólo la forma, nunca el valor.
3. Purgar lo encontrado, backups incluidos.
4. Depositar la nueva con este paquete.

## Licencia

MIT. Ver `LICENSE`.
