#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# depositar-secreto.sh — Guardar una contraseña desde una terminal, sin que se
# muestre, sin que quede en el historial del shell y sin pasar por ningún chat.
#
# Uso:
#   depositar-secreto.sh --destino RUTA [--contenedor NOMBRE] [--cuenta TEXTO]
#                        [--descripcion TEXTO] [--formato md|env|txt]
#                        [--variable NOMBRE]
#
# Ejemplos:
#   ./depositar-secreto.sh --destino ~/agente/.secrets/gmail.md \
#       --cuenta persona@ejemplo.com --descripcion "Cuenta Google"
#
#   ./depositar-secreto.sh --contenedor agente-x \
#       --destino /opt/data/.secrets/gmail.md \
#       --cuenta persona@ejemplo.com --descripcion "Cuenta Google"
#
# El valor viaja por stdin: no aparece en `ps`, ni en el historial, ni en logs.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DESTINO=""; CONTENEDOR=""; CUENTA=""; DESCRIPCION="Acceso"; FORMATO="md"; VARIABLE="SECRETO"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --destino)     DESTINO="$2"; shift 2 ;;
    --contenedor)  CONTENEDOR="$2"; shift 2 ;;
    --cuenta)      CUENTA="$2"; shift 2 ;;
    --descripcion) DESCRIPCION="$2"; shift 2 ;;
    --formato)     FORMATO="$2"; shift 2 ;;
    --variable)    VARIABLE="$2"; shift 2 ;;
    -h|--help)     sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DESTINO" ] || { echo "✗ Falta --destino" >&2; exit 2; }

if [ -n "$CONTENEDOR" ]; then
  if command -v docker >/dev/null 2>&1; then DOCKER="docker"; else DOCKER="sudo docker"; fi
  $DOCKER ps --format '{{.Names}}' | grep -qx "$CONTENEDOR" || {
    echo "✗ El contenedor '$CONTENEDOR' no está corriendo." >&2; exit 1; }
fi

echo "Destino      : ${CONTENEDOR:+$CONTENEDOR:}$DESTINO"
[ -n "$CUENTA" ] && echo "Cuenta       : $CUENTA"
echo "Descripción  : $DESCRIPCION"
echo "Formato      : $FORMATO"
echo

read -r -s -p "Contraseña (no se muestra): " P1; echo
read -r -s -p "Repetila: " P2; echo
[ -n "${P1}" ] || { echo "✗ Vacía, no hago nada." >&2; exit 1; }
[ "${P1}" = "${P2}" ] || { echo "✗ No coinciden, no hago nada." >&2; exit 1; }

case "$FORMATO" in
  env) CONTENIDO="${VARIABLE}=${P1}"$'\n' ;;
  txt) CONTENIDO="${P1}"$'\n' ;;
  *)
    CONTENIDO="# ${DESCRIPCION}"$'\n\n'"- Cuenta: ${CUENTA:-"(sin especificar)"}"$'\n'"- Secreto: ${P1}"$'\n\n'
    CONTENIDO+="Este archivo no se copia a otros agentes ni va dentro de skills/ o memories/."$'\n'
    ;;
esac

if [ -n "$CONTENEDOR" ]; then
  printf '%s' "$CONTENIDO" | $DOCKER exec -i "$CONTENEDOR" sh -c "
    mkdir -p \"\$(dirname '$DESTINO')\"
    umask 077
    cat > '$DESTINO.tmp.\$\$' && mv '$DESTINO.tmp.\$\$' '$DESTINO' && chmod 600 '$DESTINO'
  "
  unset P1 P2 CONTENIDO
  DETALLE=$($DOCKER exec "$CONTENEDOR" sh -c "stat -c '%a %U:%G %s bytes' '$DESTINO'")
else
  mkdir -p "$(dirname "$DESTINO")"
  ( umask 077; printf '%s' "$CONTENIDO" > "$DESTINO" )
  chmod 600 "$DESTINO"
  unset P1 P2 CONTENIDO
  DETALLE=$(stat -c '%a %U:%G %s bytes' "$DESTINO")
fi

echo
echo "✓ Guardado en $DESTINO ($DETALLE)"
echo "  El valor no se mostró, no quedó en el historial y no está en ningún log."
