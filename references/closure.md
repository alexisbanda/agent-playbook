<!-- Copyright (c) 2026 Alexis Banda. Todos los derechos reservados. Software propietario: uso sujeto a LICENSE, prohibida su redistribución. -->

# Cierre: qué significa "terminado"

Un ticket está terminado cuando se probó en vivo, quedó evidencia en el ticket y no se rompió nada más. Mergear o tener los tests en verde no basta.

Esta fase la haces **tú**, no un subagente: la evidencia tiene que poder defenderse, y el resumen de un subagente sobre un fallo no es el fallo.

## 1. Gate de deploy

Antes de probar nada, confirma que el deploy del merge terminó en verde (`environment.deploy_check` o `gh run list`/`gh run view` del workflow de deploy). Probar contra código no desplegado mide la versión vieja y da un falso verde. Si el deploy falló por una causa transitoria, reintenta solo el paso fallido (`gh run rerun <id> --failed`).

Si el proyecto no tiene entorno desplegado (`dev_url` vacío), prueba contra la rama mergeada en local y decláralo en LÍMITES.

## 2. Prueba en vivo

Cada criterio de aceptación se prueba con el chequeo de aceptación del plan: **el mismo comando y la misma entrada** que el coder ya ejecutó en el worktree, ahora contra el código mergeado y desplegado (`dev_url` en los `http`). Si aquí aparece un resultado distinto del que el coder observó, anótalo: es una diferencia de entorno, y la siguiente tuning wave debe saberlo.

| Chequeo | Prueba | Evidencia |
| --- | --- | --- |
| `http` | `curl` contra `dev_url`, extracto con `jq` | Status HTTP y el extracto relevante |
| `test` | El log de tests sobre el commit mergeado | Resumen y SHA |
| `e2e` | La corrida del recorrido | Enlace o ruta del artefacto |
| `manual` | Pasos que hiciste y lo que observaste | Descripción; capturas si el tracker las admite |

**Higiene de secretos:** tokens, cookies y respuestas completas van a archivos en `.agent-playbook/runs/<ticket>/` y nunca se imprimen. En la evidencia solo van el status y el extracto.

**Si una prueba falla, la corrida para.** Publica en el ticket (`comment`) que falló y por qué, en ese momento. Después relanza al coder: el fix pasa por todo el motor otra vez (borrador → review → merge). La evidencia espera a que pase.

## 3. Journeys de regresión

Desde la raíz del clon principal, con el código mergeado:

```bash
python3 <plugin>/scripts/run_journeys.py <ticket>
```

Corre cada entrada de `journeys` de la configuración, guarda su log en `.agent-playbook/runs/<ticket>/journeys/` e imprime la tabla para la evidencia. Sale con 1 si alguno falla: **un ticket no se cierra si rompió un journey**; trátalo como una prueba en vivo fallida (paso 2). Si la lista está vacía, decláralo en LÍMITES y sugiere 2 o 3 recorridos concretos para añadir a `journeys`.

## 4. Evidencia en el ticket

Rellena `templates/EVIDENCE.md` y publícalo con `comment`. Incluye:

- la tabla caso → esperado → observado, explicando las divergencias inofensivas (por ejemplo, un 422 en dev frente a un 400 en el test unitario, ambos válidos según el contrato);
- los journeys y su resultado;
- **LÍMITES:** qué no se verificó, por qué y qué lo destrabaría. Si falta el dato para probar algo, va aquí. Esta sección nunca se omite; si no hay límites, escribe "Ninguno".

## 5. Escrituras en producción

Cualquier escritura en producción (UPDATE, backfill, cambio de flag) necesita confirmación explícita del usuario para esa acción concreta, aunque el plan la mencionara.

## 6. Cerrar

1. `finish` en el tracker, solo con la evidencia publicada.
2. Limpieza del worktree (ver `engine.md`, paso 9).
3. Informe final al usuario: qué se entregó, enlaces al PR y al comentario de evidencia, LÍMITES y fallas preexistentes detectadas.
4. Marca la corrida como cerrada en `RUN_STATE.md`.
5. Cierra la telemetría: `python3 <plugin>/scripts/close_run.py <ticket> --e2e-first-pass <yes|no|na>` desde la raíz del clon principal. `yes` si todas las pruebas en vivo pasaron a la primera, `no` si alguna falló y hubo que relanzar al coder, `na` si no hubo pruebas en vivo. Añade una línea validada a `.agent-playbook/metrics.jsonl` y quita el marcador `active-run`. Incluye en el informe final los minutos totales, los minutos esperando al humano y los tokens por modelo de esa línea.
6. Termina el informe recomendando `/clear` (o una sesión nueva) antes del siguiente ticket: lo que haga falta para retomarlo está en el tracker, en `RUN_STATE.md` y en el repositorio, y arrastrar este contexto encarece cada llamada de la próxima corrida.
