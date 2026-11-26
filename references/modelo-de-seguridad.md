# Modelo de seguridad

Qué amenaza cubre cada control, y qué queda fuera de alcance. Corto y concreto:
esto no es un análisis formal, es la lista de decisiones y por qué.

## Activos y adversarios

- **Activo:** la contraseña de una persona, que da acceso a su correo, su CRM o
  su panel.
- **Adversario realista:** no un atacante sofisticado. Son tres cosas aburridas:
  1. El historial de una conversación (Telegram, WhatsApp) que queda en un
     servidor, en un backup y en el proveedor del modelo.
  2. Un log de aplicación que registra cuerpos de request.
  3. Un archivo copiado de un cliente a otro porque vivía en `skills/`.

La mayoría de las filtraciones de credenciales en flotas de agentes no vienen de
un exploit: vienen de que el secreto estaba donde no tenía que estar.

## Decisiones y qué evitan

### El valor nunca entra por el chat

Un mensaje de chat se persiste (base de la conversación), se loguea (entrante y
saliente) y se envía al proveedor del modelo. Una vez ahí no se puede recuperar:
rotar la contraseña es la única salida. Por eso el depósito ocurre por un canal
que no es la conversación.

### Token en la URL, un solo uso, TTL

- **Token:** el puerto puede recibir escaneos. Sin token, el formulario no existe
  (404), así que no hay superficie para probar contraseñas al azar.
- **Un solo uso:** el proceso termina después del POST exitoso. Un link que no
  existe no se puede reusar ni compartir por error.
- **TTL:** acota la ventana. Si la persona se distrae, el link muere y se genera
  otro; no queda un formulario colgado por días.

### Escuchar en `127.0.0.1` por defecto

Lo que no está expuesto no se puede atacar. Exponer requiere un acto explícito
(`--bind` o `--tunel`).

### `--tunel` en vez de abrir puertos

Abrir un puerto en el firewall deja un servicio HTTP en texto plano en internet.
Un quick tunnel de Cloudflare da HTTPS sin tocar el firewall y sin certificados
propios. El túnel vive mientras vive el proceso: al cerrarse, la URL muere.

### Valor por `stdin`, no por argumentos

Los argumentos de un proceso son visibles para cualquier usuario del sistema
(`ps aux`). Los argumentos también quedan en el historial del shell. `stdin` no.

### Permisos `600`

`600` = sólo el dueño lee y escribe. El usuario del agente, no root: en
contenedores con `cap_drop: ALL` root ni siquiera puede escribir en el volumen.

### Sin logging del cuerpo ni del path

El path lleva el token; el cuerpo lleva la contraseña. `log_message` del handler
se anula a propósito. Los logs de aplicación son el lugar más común donde
aparecen credenciales "sin que nadie las ponga".

### Un secreto por archivo

Facilita borrar uno sin tocar los demás, y evita que copiar un archivo se lleve
toda la vida digital de una persona.

### Fuera de `skills/` y `memories/`

Esos directorios son el mecanismo de reutilización entre agentes: se copian, se
clonan y se comparten. Un secreto ahí se multiplica. Un secreto en
`<volumen>/.secrets/` no viaja.

## Lo que este paquete NO resuelve

- **Cifrado en reposo.** El archivo es `600`, no cifrado. Si el atacante es root
  en el servidor, lo lee. Para eso hace falta un gestor con UI (vault, 1Password,
  Bitwarden) donde el valor se inyecta sin que el agente lo vea.
- **El 2FA.** Lo aprueba la persona dueña de la cuenta. Un agente no puede
  aprobar un segundo factor, y si pudiera, ya no sería un segundo factor.
- **Rotación automática.** Rotar exige conocer el flujo de la cuenta y, casi
  siempre, la intervención del humano.
- **Un agente comprometido.** Si el agente ya ejecuta código arbitrario de un
  tercero, puede leer cualquier secreto al que tenga acceso. La mitigación es
  darle sólo los secretos que necesita, uno por archivo.

## Procedimiento ante filtración

1. Rotar la contraseña (primero, siempre).
2. Barrer: buscar líneas con forma de contraseña en la base de conversaciones, en
   `skills/`, `memories/`, logs y backups. Imprimir sólo la forma (letras → `L`,
   números → `9`), nunca el valor.
3. Purgar lo encontrado, incluidos índices de búsqueda y `.bak-*`.
4. Depositar la nueva.
5. Registrar qué se rotó y cuándo, nunca el valor.
