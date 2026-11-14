# Segundo reviewer

Una segunda opinión sobre el diff de cada ticket, dada por un modelo de otro proveedor: Gemini, a través del CLI `agy` de Antigravity. Revisa en solo lectura, antes de promover el PR. Es **consultivo**: sus hallazgos van al orquestador, que los comprueba y decide. Nunca aprueba, nunca bloquea y el gate de merge no lo mira. Es opcional y se activa por configuración.

## Para qué sirve

| Qué aporta | Detalle |
| --- | --- |
| Otra mirada | Un modelo distinto del que escribió y verificó el código tiene puntos ciegos distintos. En `standard` cubre un hueco: ahí no hay reviewer independiente. En `critical` se suma al reviewer interno, sin sustituirlo |
| Cobertura de criterios | Devuelve una tabla criterio → test. El orquestador parte de ella en la verificación en lugar de leer todos los tests sobre su propio contexto |
| Sin gasto de Claude | La revisión corre en `agy` con la cuenta de Antigravity del usuario. El orquestador solo recibe una tabla corta |

Lo que **no** hace: no escribe código ni tests, no ejecuta la suite, no sustituye al reviewer interno ni al [review bot](REVIEW_BOT.md).

## Activarlo

1. Instala `agy` e inicia sesión en Antigravity con tu cuenta.
2. En la configuración del repo:
   ```json
   "second_reviewer": { "enabled": true }
   ```
   `/agent-playbook:setup-project` lo pregunta si encuentra `agy` en el PATH.

| Campo | Por defecto | Qué es |
| --- | --- | --- |
| `enabled` | `false` | Activa el segundo reviewer |
| `model` | `gemini-4-argon` | Modelo de `agy` (lista: `agy models`) |
| `timeout_seconds` | `300` | Tiempo máximo de una revisión |
| `min_diff_lines` | `50` | En `standard`, no revisa diffs con menos líneas cambiadas (`0` lo desactiva) |

El esfuerzo sale de la clase del ticket: `medium` en `standard`, `high` en `critical`.

Para desactivarlo: `"enabled": false`. No deja nada instalado en el repo.

## Qué sale del repo

Cada revisión envía a Google, con la cuenta con la que iniciaste sesión en Antigravity, el ticket con sus criterios, el plan, el cuerpo del PR, el diff y los archivos del worktree que el modelo decida leer. Si el repo no puede compartirse con ese proveedor, no lo actives. El script quita `GEMINI_API_KEY` y `GOOGLE_API_KEY` del entorno de la llamada para que nunca se facture a una API key por accidente.

## Cómo funciona

`scripts/second_review.py` hace una sola llamada a `agy` por revisión:

| Paso | Detalle |
| --- | --- |
| Paquete | El script reúne sus propias entradas sin que el orquestador prepare archivos: lee el plan y la clase desde `.agent-playbook/runs/<ticket>/RUN_STATE.md`, el cuerpo del PR con `gh pr view` en el worktree y el ticket con `gh issue view` si `tracker.type` es `github` (`--ticket-file`, `--plan-file`, `--pr-body-file` y `--class` son opcionales). Escribe `second-review-input.md` en `.agent-playbook/runs/<ticket>/` con el diff contra la rama base; un diff de más de 300 kB no se incluye y el modelo lo lee archivo por archivo |
| Llamada | `agy` en modo no interactivo desde el worktree, con `--mode plan`, `--sandbox`, salida JSON con esquema y tiempo máximo |
| Permisos | Una lista propia por llamada (`--settings`): solo `cat`, `ls`, `grep`, `git diff`, `git log` y `git show`. Sustituye a la lista global del usuario durante esa llamada, así que no puede correr tests, escribir con git ni usar `gh` aunque el usuario lo permita en general |
| Validación | Solo admite hallazgos `blocker` y `major` (descarta cualquier otro), normaliza las rutas y marca los hallazgos sobre archivos que no existen en el worktree. El veredicto se recalcula: `CHANGES_REQUESTED` si queda algún hallazgo y `APPROVE` si no |
| Registro | Guarda el resultado completo en `second-review.json`, añade una línea a `second-review.jsonl` e imprime la fila lista para pegar en la tabla «Segundo reviewer» de `RUN_STATE.md` |

`--mode plan` no basta para una revisión de solo lectura: en ese modo `agy` sigue ejecutando los comandos que el usuario tenga permitidos. Lo que la hace de solo lectura es la lista de permisos por llamada.

### Cuándo se omite

En tickets `standard` (sin `--force`):

- **Una sola revisión por ticket:** si ya hay una revisión con estado `ok`, el script sale con código 0 sin repetirla tras una corrección. En `critical` se relanza sobre el nuevo `HEAD` después de cada corrección.
- **Diff pequeño o de documentación:** si el diff está vacío, solo cambia documentación (`.md`, `.mdx`, `.rst`, `.txt`) o tiene menos de `min_diff_lines` líneas, registra `status: "skipped"` en `second-review.jsonl` y sale con código 0. No es un límite: el orquestador hace el paso 4 completo.

En `critical` siempre revisa. Con `--force` revisa aunque esté desactivado, el diff sea pequeño o el ticket ya tenga revisión.

### Cuando no hay revisión

El script termina con código 1 y una línea que dice por qué. La corrida sigue como si estuviera desactivado y se anota en LÍMITES.

| Estado | Causa |
| --- | --- |
| `missing` | `agy` no está instalado o no está en el PATH |
| `timeout` | No respondió en `timeout_seconds` |
| `denied` | El modelo intentó un comando fuera de la lista. `agy` aborta con la respuesta vacía y código 0; el script lo detecta |
| `invalid` | La respuesta no trae un veredicto válido. Se reintenta una vez |
| `error` | `git` falló en el worktree o no se pudo leer un archivo de entrada |

Todos se registran en `second-review.jsonl` y cuentan como `degraded` en las métricas.

## Qué hace el orquestador con el resultado

El procedimiento está en [`references/engine.md`](../references/engine.md), paso 5 de la verificación. En resumen:

- **Hallazgos (`blocker` y `major`):** comprueba cada uno leyendo las líneas que cita. Si es real, vuelve al coder y cuenta como una ronda de review. Si no, lo descarta con el motivo en `RUN_STATE.md`.
- **Tabla de cobertura:** lee solo los tests de las filas `partial` o `missing` y los de las filas donde su tabla y la del PR no coinciden.
- **Triaje:** pega en la tabla «Segundo reviewer» de `RUN_STATE.md` la fila que imprime el script y completa aceptados y descartados con el motivo; `close_run.py` lee esa tabla al cerrar la corrida.

## Cómo saber si merece la pena

`close_run.py` añade a la línea de métricas el campo `second_review` (ver [METRICS.md](METRICS.md)): llamadas (`calls`), llamadas sin revisión (`degraded`), revisiones omitidas (`skipped`), cambios pedidos (`changes_requested`), hallazgos, aceptados, descartados, tokens de Gemini y segundos.

| Señal | Qué mirar en la tuning wave |
| --- | --- |
| Precisión | `accepted / (accepted + discarded)`. Si la mayoría de los hallazgos se descarta, cuesta más triarlo de lo que aporta |
| Calidad | `e2e_first_pass` y las rondas de review, antes y después de activarlo |
| Fiabilidad | `degraded / calls`. Si falla a menudo, revisar la instalación de `agy` o el tiempo máximo |
| Coste | Contexto y coste del orquestador: deberían bajar algo, no subir |

Mientras sea consultivo, desactivarlo no cambia ninguna otra regla del playbook. Hacerlo bloqueante solo tiene sentido si la precisión medida lo justifica, y sería un cambio de versión aparte.

## Límites conocidos

- Solo funciona cuando el playbook corre en Claude Code con `agy` instalado en la misma máquina. No corre en la CI.
- El consumo de la cuenta de Antigravity no se puede consultar desde el script: solo se registran los tokens que `agy` declara en cada respuesta.
- Los nombres de modelo de `agy` cambian con sus versiones. Si `model` deja de existir, la revisión queda en `invalid` y la corrida sigue sin ella.
