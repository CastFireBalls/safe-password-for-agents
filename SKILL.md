---
name: contrasenas-seguras
description: "Use when hay que guardar una contraseña o token para que un agente lo use."
version: 1.0.0
author: Agente Cangrejo 🦀
license: MIT
platforms: [linux, macos]
tags: [seguridad, secretos, contrasenas, agentes, credenciales]
metadata:
  hermes:
    tags: [seguridad, secretos, contrasenas, agentes, credenciales]
    related_skills: [privacidad-entre-clientes, docker-clientes]
---

# 🦀 Contraseñas seguras para agentes

Cómo guardar una contraseña o un token para que un agente lo use **sin que el
valor pase nunca por un chat, por un log ni por el contexto de un modelo**.

## When to Use

- El usuario quiere darle una contraseña a un agente (Gmail, un CRM, un panel,
  una cuenta de banco) y no sabe cómo hacerlo sin pegarla en el chat.
- Hay que dejar una credencial en un servidor sin UI, donde el agente la lea
  desde un archivo.
- Alguien pegó una contraseña en un chat y hay que contener el incidente.
- Hay que auditar si una flota de agentes tiene credenciales en texto plano.

## Las cuatro reglas duras

1. **Ninguna contraseña entra ni sale por el chat.** Ni la pidas, ni la aceptes,
   ni la repitas, ni la uses "sólo para probar". Si el usuario ya la pegó, quedó
   expuesta: se rota y se vuelve a depositar.
2. **Una contraseña nunca vive en `skills/` ni en `memories/`.** Esos directorios
   se copian entre clientes y son exactamente el vector por el que se cruzan los
   datos. El secreto va en un archivo aparte con permisos `600`.
3. **El valor viaja por stdin, nunca por argumentos.** Los argumentos se ven en
   `ps` y quedan en el historial del shell.
4. **El agente lee el archivo cuando lo necesita.** No se le dictamina la
   contraseña en el prompt: se le dice dónde está.

## Tres formas de depositar, de la mejor a la peor

### A. Link de un solo uso (no técnico, sirve desde el teléfono)

La persona abre un link, escribe su contraseña, y el servidor la escribe donde el
agente la lee. Es la única forma cómoda cuando el humano no tiene terminal.

```bash
python3 scripts/generar-link.py \
  --destino /opt/data/.secrets/gmail.md \
  --contenedor agente-x \
  --cuenta persona@ejemplo.com \
  --descripcion "Cuenta Google" \
  --tunel                     # opcional: link HTTPS público
```

Devuelve algo como `https://algo-random.trycloudflare.com/<token>`. Propiedades:

- Token aleatorio en la ruta: sin él responde 404.
- **Un solo uso**: después del POST exitoso el proceso se cierra.
- Vence solo (`--ttl`, 15 min por defecto).
- Escucha en `127.0.0.1` y sólo se expone si se pide `--tunel`.
- Nunca registra el valor en ningún log.

Sin `--tunel` el link sólo funciona desde la misma máquina o por la red privada
(Tailscale, VPN). Con `--tunel` sirve desde cualquier teléfono con HTTPS, sin
abrir puertos en el firewall.

### B. Terminal del operador (cuando hay acceso al servidor)

```bash
./scripts/depositar-secreto.sh \
  --contenedor agente-x \
  --destino /opt/data/.secrets/gmail.md \
  --cuenta persona@ejemplo.com \
  --descripcion "Cuenta Google"
```

Pide la contraseña dos veces con `read -s` (no se muestra, no va al historial) y
la escribe con permisos `600`.

### C. Gestor de contraseñas con UI (si el agente tiene panel o escritorio)

`hermes vault add` guarda cifrado y el agente sólo ve el handle: el valor lo
inyecta `browser_vault_fill` en el origen exacto. Es lo mejor cuando hay UI,
porque la contraseña queda cifrada en reposo.

**Sólo sirve con UI.** `hermes vault add` es interactivo: en un contenedor sin TTY
no hay dónde escribir y el vault queda vacío para siempre. Si el contenedor no
publica ningún puerto web, no existe "Ajustes → Contraseñas y accesos": no lo
ofrezcas, mandás a la persona a una puerta que no está.

## Verificación obligatoria (sin imprimir el valor)

```bash
# permisos, dueño y tamaño
stat -c '%a %U:%G %s bytes' /opt/data/.secrets/gmail.md

# ¿está la línea del secreto? (cuenta, no muestra)
grep -c 'Secreto:' /opt/data/.secrets/gmail.md

# ¿es la cuenta correcta?
grep -m1 'Cuenta:' /opt/data/.secrets/gmail.md
```

Si algo de eso no coincide, se para y se avisa. No se completa ni se inventa.

## Cómo lo usa el agente

- El agente lee el archivo **en el momento del login**, no antes.
- Después de usar la contraseña no la repite en la respuesta ni la escribe en
  ningún otro archivo.
- Si el login pide 2FA, el segundo factor lo aprueba **la persona dueña de la
  cuenta en su teléfono**. Nadie más: el pedido de Google caduca en ~2 minutos.
- Si la cuenta tiene permisos de administración sobre datos de terceros, el
  agente no la usa para automatizaciones de lectura: una cuenta admin ve los
  datos de toda la organización.

## Si la contraseña ya se filtró (chat, captura, log)

1. **Rotar primero**, sin excepciones. Una contraseña pegada en un chat viajó por
   el servidor de mensajería y por el proveedor del modelo.
2. Barrer el disco sin imprimir valores: buscar líneas con *forma* de contraseña
   (sólo letras y números, 8-40 caracteres, sin espacios) en `state.db`,
   `skills/`, `memories/` y logs.
3. Purga lo que aparezca, y revisá que no haya quedado en índices de búsqueda
   (`messages_fts`) ni en backups.
4. Depositar la nueva por A, B o C.
5. Dejar dicho en el historial del incidente **qué se rotó y cuándo**, nunca el
   valor.

## Pitfalls que ya costaron tiempo

- **`docker exec -u root` no puede escribir en el volumen del agente** si el
  contenedor tiene `cap_drop: ALL`: `mkdir: Permission denied` sobre `/opt/data`.
  Se escribe con el usuario del agente (el `USER` de la imagen), no con root.
- **`pip install` con el usuario del agente se va a `~/.local`** y crea una copia
  que tapa la del sistema. Para instalar software va root; para escribir secretos
  va el usuario del agente.
- **El proceso del formulario queda vivo si no se cierra.** Después del uso
  exitoso se apaga solo; si se abandona, cerrarlo a mano y **bajar el túnel**.
  Un quick tunnel de Cloudflare sigue publicado mientras el proceso exista.
- **No sirve pedirle al modelo que "se acuerde" de la contraseña.** Si hace falta
  persistencia, es un archivo `600`; la memoria del agente no es un almacén.
- **Los backups con timestamp también filtran.** Cuando se sanitiza un archivo
  con secretos hay que borrar los `.bak-*` que lo contenían.
- **Un secreto por archivo.** Un archivo con cinco credenciales se copia, se
  comparte y se filtra entero; cinco archivos permiten borrar uno solo.

## Archivos

| Archivo | Qué es |
|---|---|
| `scripts/generar-link.py` | Formulario de un solo uso con token, TTL y túnel opcional |
| `scripts/depositar-secreto.sh` | Depósito por terminal con entrada enmascarada |
| `references/modelo-de-seguridad.md` | Por qué cada control existe y qué amenaza cubre |
