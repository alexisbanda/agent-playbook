# Changelog

## 1.8.3

Corrige los índices duplicados de los lectores Gemini lanzados en paralelo (#30) y reduce sus denegaciones (#31). La hipótesis de que las comillas causaban las denegaciones se descartó con `agy` real: la causa es un comodín de shell sin comillas en un comando `git`.

- **`scripts/gemini_reader.py`:** nueva `reserve_packet()`, que reserva el número del lector de forma atómica (`O_CREAT | O_EXCL`, saltando a `n + 1` si el paquete ya existe) y la usa `read_repo()`; `append_log()` escribe cada línea con bloqueo `fcntl.flock` (se omite si `fcntl` no existe, en Windows). Añade `git branch` a `ALLOWED_COMMANDS` y deniega sus formas de escritura (`git branch -d`, `-D`, `-m`, `-M`, `--delete`; denegación suave, prefijos más largos que `git branch`). Nueva constante `SHAPE_RULES` en el prompt: con `git`, nada de comodines sin comillas (pasar `-- docs/` o `-- 'docs/08*'`) ni subcomandos fuera de la lista. El aviso del reintento tras una denegación repite las reglas de forma.
- **`scripts/metrics_report.py` y `metrics/tripwires.json`:** nuevo tripwire `gemini_readers_degraded_share_max` (0,2): lectores degradados / llamadas en la ventana, solo si alguna corrida tuvo lectores Gemini.
- **Documentación (`docs/GEMINI_READERS.md`, `docs/METRICS.md`):** `git branch` en la lista permitida, la regla de comodines con `git` (comprobada con `agy` 1.5.11), la reserva atómica de números en paralelo y el tripwire nuevo.
- **Tests (`tests/test_gemini_reader.py`, `tests/test_metrics.py`):** cubren `git branch` en `allow` y sus formas de escritura en `deny`, las reglas de forma en el prompt y en el reintento, dos `read_repo()` simultáneos con índices distintos, `reserve_packet()` sin sobrescribir paquetes existentes y el tripwire nuevo (salta con 2 de 5 lectores degradados; no aparece sin lectores).

## 1.8.2

Amplía la lista permitida de los lectores Gemini con los comandos de solo lectura que causaron las últimas denegaciones en `epic-2` (`git grep` en #8, `git status` en #7) y con `find` y `sed -n`.

- **`scripts/gemini_reader.py`:** añade `find`, `sed -n`, `git grep` y `git status` a `ALLOWED_COMMANDS`. Quita `sed` y `find` de `DENIED_COMMANDS`: en `agy` el `deny` gana al `allow` y se empareja por prefijo de palabras, así que bloqueaban también `sed -n` y `find` (comprobado con `agy`). En su lugar deniega `sed -i`, `sed -e`, `sed -E`, `sed -r` y `sed --in-place` (denegación suave). El prompt limita `sed` a `sed -n 'A,Bp'` y `find` a listar (sin `-exec`, `-execdir`, `-ok`, `-delete` ni `-fprint`); el sandbox bloquea igualmente sus escrituras.
- **Documentación (`docs/GEMINI_READERS.md`):** lista nueva y cómo empareja `agy` los permisos.
- **Tests (`tests/test_gemini_reader.py`):** cubren los nuevos `allow`, que `sed` y `find` no estén enteros en `deny` y la regla de `find` en el prompt.

## 1.8.1

Endurece los permisos de los lectores Gemini en `scripts/gemini_reader.py` (#27) para evitar abortos silenciosos de `agy` al intentar ejecutar intérpretes o herramientas no permitidas y recuperar automáticamente una vez los comandos no listados.

- **`scripts/gemini_reader.py`:** amplía `ALLOWED_COMMANDS` (`cat`, `ls`, `grep`, `head`, `tail`, `wc`, `git log`, `git show`, `git diff`, `git ls-files`) y añade `DENIED_COMMANDS` (`node`, `python`, `npm`, `pnpm`, `sed`, `find`, `gh`, `docker`, etc.) en `permissions.deny` para que `agy` devuelva una denegación suave sin cortar el turno. Refuerza el prompt para leer código/lockfiles o anotar dudas en `risks`, detecta también `denied_actions` sin `structured_output` en `parse_result()`, extrae el último `run_command` del transcript con `denied_command()`, guarda los últimos 4000 caracteres del stderr en `gemini-reader-<n>-stderr.log`, reintenta una vez avisando del comando denegado, registra `denied` en `gemini-readers.jsonl`, cuenta `recovered` en `summarize()` y lo muestra en `report()`.
- **Métricas (`config/metrics.schema.json`, `docs/METRICS.md`):** añade el campo opcional `recovered` dentro de `gemini_readers`.
- **Documentación y skills (`docs/GEMINI_READERS.md`, `skills/resolve-issue/SKILL.md`, `skills/resolve-epic/SKILL.md`):** documenta `allow` vs `deny` vs comandos no listados, el reintento único y cómo formular las preguntas («dónde está / qué dice», no «comprueba si funciona»).
- **Tests (`tests/test_gemini_reader.py`, `tests/test_hooks.py`):** cubren `build_command`, `parse_result` con `denied_actions`, `denied_command`, recuperación y doble denegación en `read_repo` y el contador `recovered` en `summarize`.

## 1.8.0

Lectores de código con Gemini vía `agy` (`docs/GEMINI_READERS.md`) y Gemini como **reviewer interno obligatorio** en tickets `critical` cuando `second_reviewer.enabled` es `true` (`second_reviewer.internal_review`, por defecto `true`), con caída automática a los agentes de Claude si `agy` falla.

- **`scripts/gemini_reader.py` (nuevo):** ejecuta un lector en solo lectura sobre el repositorio con `agy` (por defecto `gemini-3.8-flash` y `effort: "low"`), esquema JSON (`summary`, `files`, `risks`, `tests`), lista cerrada de permisos por llamada (`cat`, `ls`, `grep`, `git log`, `git show`), normalización de rutas, registro en `gemini-readers.jsonl` y tabla compacta para el orquestador. Si sale con código 1, indica caer a un lector Claude (`haiku`) y anotarlo en LÍMITES.
- **`scripts/second_review.py`:** añade `second_reviewer.internal_review` (por defecto `true`) y el rol de revisión (`role: "advisory"` en `standard`; `role: "internal"` en `critical` con `internal_review: true`). En modo `internal` su `APPROVE` sobre el `HEAD` actual es el del reviewer interno obligatorio y absorbe la revisión de `opus` (una sola revisión de Gemini por ronda); si sale con código 1, indica lanzar el reviewer `opus` de Claude y anotarlo en LÍMITES. `summarize()` añade el contador `internal`.
- **Configuración (`config/agent-playbook.schema.json`, `config/agent-playbook.example.json`):** añade `second_reviewer.internal_review` y la sección `gemini_readers` (`enabled`, `model`, `effort`, `timeout_seconds`).
- **Preflight (`scripts/preflight.py`, `references/preflight.md`):** añade el control 10 (`gemini_readers`) cuando `gemini_readers.enabled` es `true`.
- **Skills, motor y documentación (`skills/resolve-issue/SKILL.md`, `skills/resolve-epic/SKILL.md`, `skills/setup-project/SKILL.md`, `references/engine.md`, `docs/SECOND_REVIEWER.md`, `docs/GEMINI_READERS.md`, `docs/METRICS.md`, `README.md`):** integran los lectores Gemini y el rol de reviewer interno obligatorio con sus caídas a Claude.
- **Métricas (`config/metrics.schema.json`, `scripts/close_run.py`):** añade `gemini_readers` en `metrics.jsonl` y el campo opcional `internal` dentro de `second_review`.

## 1.7.0

Segundo reviewer **opcional y consultivo** con Gemini en solo lectura a través del CLI `agy` (`docs/SECOND_REVIEWER.md`). Nunca aprueba ni bloquea por sí mismo, y `merge_gate.py` no lo mira.

- **`scripts/second_review.py` (nuevo):** reúne sus propias entradas (`RUN_STATE.md`, cuerpo del PR e issue vía `gh`), construye el paquete de revisión (`second-review-input.md`), invoca `agy` en modo plan con `--sandbox`, esquema JSON estricto y lista de permisos de solo lectura por llamada, normaliza rutas, conserva solo hallazgos `blocker` y `major` (descarta el resto y corrige el veredicto si queda alguno), en `standard` revisa una sola vez por ticket y omite diffs vacíos, pequeños (`min_diff_lines`) o solo de documentación, registra `second-review.json` y `second-review.jsonl`, imprime la fila para `RUN_STATE.md` y resume totales para métricas (leyendo el triaje de `RUN_STATE.md`, incluyendo `skipped`).
- **Configuración (`config/agent-playbook.schema.json`, `config/agent-playbook.example.json`):** añade `second_reviewer` (`enabled`, por defecto `false`; `model`, por defecto `"gemini-4-argon"`; `timeout_seconds`, por defecto `300`; `min_diff_lines`, por defecto `50`).
- **Preflight (`scripts/preflight.py`, `references/preflight.md`):** añade el control 9 (`second_reviewer`), que solo aparece cuando `second_reviewer.enabled` es `true` (OK si `agy` está en el `PATH`, AVISO si falta sin bloquear nunca la corrida).
- **Motor, plantilla y setup:**
  - `references/engine.md` (verificación paso 5 y tabla de la sección 5): lanza el segundo reviewer tras pasar los tests sin preparar archivos previos, parte de su tabla de cobertura de criterios, tria hallazgos `blocker` y `major` en la tabla de `RUN_STATE.md`, hace una sola revisión por ticket en `standard` y realiza el paso 4 completo cuando se omite en diffs pequeños o solo de documentación.
  - `templates/RUN_STATE.md`: añade la sección `## Segundo reviewer`, donde se pega la fila que imprime el script y se registran aceptados y descartados que lee `close_run.py`.
  - `skills/setup-project/SKILL.md`: añade el paso 10 («Segundo reviewer», solo ofrecido si `agy` está en el `PATH`, avisando de qué datos salen hacia Google) y renumera los pasos 11 y 12.
- **Métricas (`config/metrics.schema.json`, `scripts/close_run.py`, `docs/METRICS.md`):** añade el campo opcional `second_review` en `metrics.jsonl` con los totales de `second_review.summarize(...)` (incluyendo `skipped`, o `null` si no hubo llamadas ni revisiones omitidas).

## 1.6.2

- **Preflight con Jira.** Hasta ahora el preflight solo comprobaba el conector de Notion. Con `tracker.type: "jira"` se comprueba también el de Atlassian (`references/preflight.md`, sección 4):
  1. el conector responde (`getAccessibleAtlassianResources`);
  2. el sitio configurado (`cloud_id` o `site_url`) es accesible;
  3. `project_key` aparece en `getVisibleJiraProjects`;
  4. el `cloudId` queda anotado en `RUN_STATE.md` para el adaptador.

  Si algo falla, la corrida se detiene antes de tocar el ticket. `preflight.py` no puede comprobar conectores MCP: `resolve-issue` y `resolve-epic` piden ahora hacerlo a mano después del script, tanto con Notion como con Jira.
- `references/trackers/jira.md`: documenta `tracker.jira.cloud_id`, que ya estaba en el esquema.

## 1.6.1

Documentación al día, sin cambios de comportamiento.

- **README:**
  - roadmap con la 1.3, 1.4, 1.5 y 1.6;
  - vuelve la sección «Límites conocidos», que desapareció en la 1.2, con lo que aún no se ha probado en real (Jira, perfil `full`, `resolve-epic`, `agy`, entorno desplegado, review bot, journeys);
  - la sección «Estructura» nombra `agents/coder.md` y los cuatro hooks;
  - el paso 1 menciona también `.agent-playbook.json`.
- **`docs/SCALING.md`:** la regla «los agentes nunca mergean» dice ahora que los subagentes nunca mergean y que el orquestador sí, solo con OK humano, `merge_gate.py` y `--match-head-commit` (como desde la 1.6.0).

## 1.6.0

Tuning wave del 2026-11-08 sobre 36 corridas (30 de castkit y recuerdos-artesanales, todas 1.2.0; aún ninguna con la 1.3.0–1.5.0). Saltan tres tripwires:
- `cost_per_run_usd_max` (5,14) y `e2e_first_pass_rate_min` (0,75): ya los atacan la 1.4.0 y la 1.5.0, sin datos nuevos para evaluarlas, así que se dejan como están;
- `human_wait_share_max` (0,92, desde 0,51 en la ola anterior): este es nuevo.

Detrás de las esperas no hay respuestas lentas: la mediana es de 2–3 minutos. Sí hay unas 8 paradas por corrida, y:
- **23 de 32 PRs los mergeó el usuario a mano.** Son todos los de recuerdos y 14 de 23 en castkit, porque el modo automático deniega `gh pr merge`: una parada más por PR.
- **Unas 13 preguntas «¿cómo va…?» en 12 corridas**, porque el orquestador terminaba el turno sin decir qué corría ni que avisaría solo.
- **El tripwire medía ausencias, no fricción**: la corrida #93 tiene 844 de sus 897 minutos en una sola espera nocturna.

Cambios:

- **Permiso de merge.** `skills/setup-project/SKILL.md` (paso 10) propone, con OK del usuario, `Bash(gh pr merge * --match-head-commit *)` en `.claude/settings.local.json`. `scripts/preflight.py` añade el control 8, «Permiso de merge», que avisa si falta y no requiere decisión (`references/preflight.md`). El OK explícito, `merge_gate.py` y el gate de seguridad (que bloquea el merge sin `--match-head-commit` o desde un subagente) no cambian.
- **Avisar de lo que corre en segundo plano.** `references/engine.md` (paso 8) y `skills/resolve-issue/SKILL.md` (fase 5): al terminar el turno con un agente en marcha, una línea con qué corre, cuánto suele tardar y que el orquestador avisará solo.
- **Esperas medidas sin ausencias.**
  - `hooks/telemetry.py` marca `automatic` en los mensajes que inyecta la herramienta (notificaciones de tareas); guarda solo la marca, no el texto.
  - `scripts/close_run.py` añade `human_stops`, `human_wait_active_minutes` y `human_absence_minutes` (paradas de más de 30 minutos). `human_wait_minutes` y `human_waits` mantienen su significado.
  - `scripts/metrics_report.py`: `human_wait_share_max` deja fuera las ausencias desde la 1.6.0, y hay un tripwire nuevo, `human_stops_per_run_max` (6), con su columna «Paradas».
  - Con los datos de 1.2.0: la #93 queda en 5 paradas, 45 min de espera activa y 844 de ausencia; la #78 en 8 paradas; la #32 en 6 paradas y 154 min de ausencia.
- Qué mirar en la próxima ola:
  - `prs_merged_outside` en 0;
  - la mediana de `human_stops` por debajo de 6;
  - ninguna pregunta «¿cómo va…?».

  La proporción de espera seguirá alta mientras los agentes sean rápidos: la señal útil son las paradas.
- 139 tests.

## 1.5.0

Segunda parte del análisis de tokens del 2026-11-07. Objetivo: gastar menos sin bajar la calidad, sobre todo en los tickets importantes. Los pasos que dan la calidad (plan aprobado, reviewer en `critical` con un 4 % del coste, Opus en `critical`, prueba en vivo) no cambian.

- **Chequeos de aceptación ejecutables antes del PR.** Las corridas con la prueba en vivo fallida costaron de media 13,8 USD, frente a unos 3,9 de las que pasaron a la primera. En castkit, 3 de esos 5 fallos (#7, #43, #56) tenían los tests en verde y fallaban con la entrada real: una malla con agujeros de 6 aristas, una altura de relieve y un número de caras. Los tres se podían ver en el worktree. Los otros dos fueron externos: un 403 de una API y un entorno que solo existe en producción.
  - `skills/resolve-issue/SKILL.md`: cada criterio del plan es un comando con tipo, entrada real (la misma de la prueba en vivo) y esperado medible. Lo que solo puede correr desplegado se marca «solo en cierre» y va a riesgos.
  - `templates/CODER_BRIEF.md` (regla 13): el coder ejecuta cada chequeo sobre el último commit antes del PR e informa del valor observado; si el esperado le parece mal, se detiene en lugar de cambiarlo.
  - `references/engine.md` (verificación, paso 3): sin los chequeos en verde sobre `HEAD`, el trabajo vuelve al coder. `references/closure.md`: la prueba en vivo repite el mismo comando y la misma entrada contra el entorno desplegado.
  - `templates/RUN_STATE.md` y `templates/PR_BODY.md`: tabla de chequeos con comando, entrada, esperado y observado.
- **Modelo del orquestador por carril.** En los tickets S, el orquestador en Opus es el 50–75 % del coste (unos 1,3 USD fijos por corrida). Al presentar el plan, `resolve-issue` recomienda `/model sonnet` en Fast-Track y `opus` en el carril crítico; nunca bajar de modelo en el crítico. Es una recomendación, no un bloqueo (`routing/ROUTING.md`, regla 7).
- **Métrica `orchestrator_model`** en `close_run.py`: el modelo que hizo la mayoría de las llamadas del orquestador. `metrics_report.py` la muestra en la columna «Orquestador».
- Qué mirar en la próxima ola:
  - `e2e_first_pass_rate` por encima de 0,8, y en los tickets `critical` que no baje;
  - el coste mediano de los tickets Fast-Track con orquestador `sonnet` frente a `opus`;
  - las rondas de revisión, sin cambios.
- 135 tests.

## 1.4.0

Análisis de tokens del 2026-11-07 sobre 31 corridas 1.2.0 (castkit, recuerdos-artesanales, pokemon-visiotech, kickoff-demo): 192 USD estimados, 6,20 USD de media y mediana de 5,14 sobre las últimas 10 (salta `cost_per_run_usd_max`). El 62 % del coste es lectura de caché, y por rol: coders 52 %, orquestador 43 %, reviewers 4 %, lectores 1 %.

El coder es la mayor partida y nadie la medía. Los coders largos hacen 93-236 llamadas y su contexto pasa de 44k a 213-428k tokens (castkit#56: dos coders releyeron 120M tokens, 27 de los 32 USD de la corrida). Lo que crece es, por este orden, el razonamiento que se conserva durante el bucle de herramientas, lo que escribe el propio coder (heredocs `cat >>`, `Edit`) y los resultados de herramientas. Además, la regla de pocos pasos no se cumplía: 36 ejecuciones de tests, 29 `grep` sueltos, 32 heredocs por trozos y el mismo archivo leído hasta 5 veces en un solo coder.

- **Agente `coder` del plugin** (`agents/coder.md`): solo Bash, Read, Edit, Write, Grep y Glob, y esfuerzo `medium`; en `critical` el orquestador pasa `effort: high`. `general-purpose` arrancaba con 44k tokens de contexto que se releían en cada llamada. `references/engine.md` (paso 3), `skills/resolve-issue/SKILL.md` y `skills/resolve-epic/SKILL.md` lanzan `agent-playbook:coder`; `agy` no cambia.
- **Vigilante de contexto** (`hooks/context_guard.py`, `PostToolUse`): dentro de un coder o patriot, al pasar de `hooks.coder_ctx_handback_k` (150k por defecto, nuevo en el esquema) u 80 llamadas, le pide commitear, dejar `HANDBACK.md` y terminar; avisa otra vez cada 50k más. No bloquea. `references/engine.md` (paso 8) describe el relevo con un coder nuevo y propone partir el ticket a partir del tercer relevo.
- **Brief del coder** (`templates/CODER_BRIEF.md`): reglas 10 a 12. Tests del módulo mientras itera y la suite completa una vez al final, salida recortada, lecturas por tramos sin releer, y relevo cuando avisa el vigilante. `templates/HANDBACK.md` cubre el relevo por contexto.
- **Métricas**: `close_run.py` añade `coder_calls_max`, `coder_ctx_peak_k` y `context_guard_warnings`; `metrics_report.py` muestra la columna «Coder: llamadas / pico (k)» y evalúa los tripwires nuevos `coder_calls_max` (80) y `coder_ctx_peak_k_max` (200). Con los datos de 1.2.0, castkit#56 daría 236 / 428, #94 93 / 214 y #1 28 / 74.
- Qué mirar en la próxima ola: la mediana de `coder_ctx_peak_k` por debajo de 200, la de `coder_calls_max` por debajo de 80 y el coste mediano por corrida por debajo de 5 USD.
- 134 tests.

## 1.3.0

Tuning wave del 2026-10-21 sobre 8 corridas de castkit (todas 1.2.0). Saltaron `cache_read_share_max` (0,982) y `human_wait_share_max` (0,51); el coste mediano (4,85 USD) seguía por debajo del umbral, pero las tres últimas corridas costaron 5,81, 8,37 y 11,97 USD.

- **Cada ticket en una sesión nueva.** El orquestador encadenaba tickets en la misma sesión: su contexto en la primera llamada de cada corrida pasó de 168k (corrida 1) a 417k (corrida 45) y 669k (corrida 55) tokens, y la lectura de caché de Opus de unos 5M a 28M por corrida. Sin compactaciones, porque la ventana es de 1M.
  - `scripts/preflight.py`: control 7, **Contexto de la sesión**. Busca el transcript de la sesión en `events.jsonl` y, si supera el tripwire `orchestrator_ctx_start_k_max`, avisa y no abre `active-run` (la corrida pertenece a la sesión, y `/clear` empieza otra). `--keep-session` la abre igualmente si el usuario decide seguir.
  - `skills/resolve-issue/SKILL.md` (Fase 1), `references/preflight.md`, `references/closure.md` (recomendar `/clear` al cerrar) y `skills/resolve-epic/SKILL.md` (sesión nueva al empezar; `/clear` entre olas por encima de unos 300k).
- **Tripwire recalibrado.** `cache_read_share_max` (0,97) saltaba incluso en la corrida más limpia (0,979): en un bucle agéntico la lectura de caché siempre domina. Se sustituye por `orchestrator_ctx_start_k_max` (150k), medido con la nueva métrica `orchestrator_ctx_start_k` de `scripts/close_run.py` (contexto del orquestador en su primera llamada de la corrida) y mostrado en `metrics_report.py`.
- Qué mirar en la próxima ola: la mediana de `orchestrator_ctx_start_k` por debajo de 150, y el coste mediano por corrida por debajo de 5 USD.
- 127 tests.

## 1.2.0

Adaptador **Jira Zero-Admin** (Ola 2), portabilidad **Dual-Runtime Claude Code + Google Antigravity `agy`** (Ola 3) y **escalado para proyectos mediano-grandes** (Ola 4):

- **Jira Zero-Admin (`tracker.type: "jira"`)**: `references/trackers/jira.md` con las 6 operaciones sobre el conector de Atlassian usando `labels` nativos (`type:*`, `risk:*`, `size:*`, `ready`), `config/agent-playbook.schema.json` con `tracker.jira` y `scripts/ticket_check.py` con normalización multi-tracker (`normalize_issue()` para GitHub, Notion y Jira ADF/Markdown + `--input`).
- **Dual-Runtime (`Claude Code` + `Google Antigravity agy`)**:
  - `routing/routing.json` y `scripts/route.py` con `runtime_aliases` por tier (`haiku`/`flash`, `sonnet`/`inherit`, `opus`/`pro`, `fable`/`pro`).
  - `hooks/common.py` con normalización automática de protocolo (`snake_case` de Claude Code y `camelCase` de `agy`), soporte de herramientas equivalentes (`Agent`/`Task`/`invoke_subagent`, `Bash`/`run_command`, `AskUserQuestion`/`ask_question`) en `hooks/model_gate.py`, `hooks/safety_gate.py`, `hooks/telemetry.py` y `hooks/hooks.json`.
  - `scripts/close_run.py` suma tokens tanto de sesiones `assistant` de Claude Code como de pasos `PLANNER_RESPONSE` de `agy`.
  - Manifiesto `plugin.json` en la raíz sincronizado con `.claude-plugin/plugin.json` (`scripts/check-version.py`) y lectura dual de `.agent-playbook.json` / `.claude/agent-playbook.json` en todos los scripts.
- **Escalado mediano-grande**:
  - **`scripts/repo_map.py`** (nuevo): genera y actualiza `.agent-playbook/repo-map.md` con el árbol de módulos, manifiestos y entrypoints para evitar re-exploraciones en frío.
  - **Skill `skills/resolve-epic/SKILL.md`** (nuevo): Wave Runner que resuelve los sub-issues de una épica por olas de dependencias y permite hasta 3 coders en paralelo en worktrees distintos cuando sus conjuntos de `archivos que toca` son disjuntos (`references/engine.md`, `docs/SCALING.md`).
  - **Exportación sanitizada para clientes**: `scripts/metrics_report.py --export-sanitized <archivo>` anonimiza IDs de corridas, rutas y motivos de override para usar `tuning-wave` sin exponer datos privados de clientes.
- 121 tests.

## 1.1.0

Eficiencia operativa para proyectos pequeños y medianos (**preflight en un paso**, **baseline cacheado por SHA** y **carril Fast-Track**):

- **`scripts/preflight.py` (nuevo)**: consolida los 6 controles del preflight (modelo de la sesión, versión del playbook con caché de 24 h en `.agent-playbook/cache/version-check.json`, configuración en `.agent-playbook.json` o `.claude/agent-playbook.json`, `gh auth status` con fallback ante tokens de entorno caducados, estado de `git` y apertura de `.agent-playbook/active-run`) en una sola llamada CLI y devuelve el bloque Markdown listo para `RUN_STATE.md`.
- **Baseline de tests cacheado por SHA base** (`references/engine.md` paso 2): guarda la salida en `.agent-playbook/cache/baseline-<sha>.log`; si otro ticket parte del mismo SHA de `origin/<rama-base>`, reutiliza el baseline sin volver a correr la suite.
- **Verificación sin duplicación** (`references/engine.md` paso 4): si el coder ya ejecutó el comando de tests del worktree sobre el SHA actual de `HEAD` en verde y el worktree está limpio, el orquestador no repite la ejecución completa por segunda vez.
- **Carril Fast-Track (`size: S` + `risk: ninguno`)** (`skills/resolve-issue/SKILL.md`): en tickets pequeños sin riesgo ni preguntas abiertas, el orquestador localiza los archivos con hasta 3 búsquedas directas (`Grep`/`Glob`) sin lanzar subagentes `Explore`, y soporta `--approve-plan` para ir directo a construcción manteniendo siempre el OK humano obligatorio antes del merge.
- 111 tests (4 nuevos).

## 1.0.3

Lo visto al revisar el coste de kickoff-demo#2 y #5: el informe de métricas daba la mitad del coste real ($2,67 y $4,17 frente a $4,84 y $8,11).

- **Tokens de salida bien contados** (`scripts/close_run.py`): Claude Code escribe cada respuesta en varios registros con el mismo id (uno por bloque mientras se genera), y solo el último trae los `output_tokens` finales. Se contaba el primero: en #5, 16.493 tokens de salida del coder en vez de 75.681.
- **El orquestador cuenta:** si la sesión empezó antes de que los hooks del repo la vieran (no hay `session_start`), su transcript se busca junto al de sus subagentes (`<dir>/<sesión>/subagents/…` → `<dir>/<sesión>.jsonl`); además, `user_prompt` guarda la ruta del transcript. Era cerca del 40 % del coste.
- **Brief del coder, regla 9 («pocos pasos»):** cada llamada a una herramienta relee todo el contexto (el 74 % del coste del coder en #5, con 124 llamadas). Agrupar lint, typecheck y tests en una llamada; archivos nuevos de una vez; `git add` y `commit` juntos, y push y PR al final; no releer lo que ya está en el contexto.
- `docs/METRICS.md`: qué incluyen los tokens por modelo.
- 107 tests (2 nuevos).

## 1.0.2

Lo visto en la corrida de alexisbanda/kickoff-demo#2, el primer **ticket 0 de un repo sin código** resuelto de punta a punta (kickoff de ticket-studio → `TECH.md` → `resolve-issue`; Next.js 16, Postgres, Prisma 7, Vitest y CI; 28 minutos, pruebas en vivo a la primera).

- **`setup-project` en un repo sin código:** no hay comando de tests que ejecutar. Si `TECH.md` fija el stack, propone el que creará el ticket 0 y lo guarda solo con OK, diciendo que no se ejecutó; si no, lo deja vacío. Comprueba también la versión del runtime.
- **Versión del runtime** (`references/test-runtimes.md`, `engine.md` paso 1): dónde leer la que pide el proyecto, avisar si `TECH.md` nombra una fuera de soporte (la corrida pedía Node 20, sin soporte desde abril de 2026), instalar la que falta en el espacio del usuario con la aprobación del plan y usar el mismo prefijo en baseline, coder y verificación.
- **Brief del coder, regla 8:** los generadores escriben configuración de agentes (`prisma init` creó `.claude/skills/`, `.windsurf/`, `.agents/`); no se commitea nada en `.claude/`, se borra lo que creen ahí, y lo que el framework regenera en cada arranque (`AGENTS.md` de `next dev`) se commitea y se dice. Los generadores que pisan archivos del repo se ejecutan fuera del worktree.
- **README:** el límite «proyecto desde cero sin probar» pasa a «probado una vez».

## 1.0.1

- Marketplace: la ficha de ticket-studio ya no menciona Jira (ticket-studio 1.0 trabaja con GitHub Issues y Notion).

## 1.0.0

Primera versión estable (MVP), junto con ticket-studio 1.0: del documento de kickoff al PR mergeado con evidencia en el ticket, con GitHub Issues o Notion.

- **Notion probado en real**: las seis operaciones del adaptador, con notas de la primera corrida (estado como select, URLs sin `?pvs=…`, prefijo `userDefined:` solo para `url`/`id`, evidencia como comentario corto más bloque al final).
- **Identificador de Notion**: carpetas y ramas usan los **8 últimos** caracteres del id de página; los 8 primeros se repiten dentro de un workspace y hacían chocar dos tickets.
- **README**: la fase 1b (arranque) queda sustituida por el ticket 0 de ticket-studio resuelto con `resolve-issue`; roadmap al día y **límites conocidos de la 1.0**.
- Compatible con el contrato de ticket v1.1 de ticket-studio (tipo `improvement`): `ticket_check.py` ya trata cualquier tipo que no sea épica con el mismo mínimo.

## 0.7.1

Lo visto en la corrida de alexisbanda/pokemon-visiotech#6, el primer ticket de ticket-studio resuelto de punta a punta.

- **Merge bloqueado por el modo automático:** el clasificador deniega `gh pr merge` aunque el usuario haya dado OK. `references/preflight.md` (Problemas conocidos) y `references/engine.md` (paso 7) dicen qué hacer: no esquivarlo, darle al usuario el comando del gate y seguir con el cierre cuando confirme.
- **Telemetría de merges hechos a mano:** `close_run.py` consulta en GitHub los PRs abiertos en la corrida; `prs_merged` incluye los que se mergearon fuera de la sesión y el nuevo campo opcional `prs_merged_outside` dice cuántos. Sin `gh` o sin red, cuenta solo los eventos, como antes.
- **Verificación:** `engine.md`, paso 4, pide contrastar la tabla criterio → prueba del PR con los tests reales (en la corrida, el PR decía comprobar campos que ningún test comprobaba).
- 104 tests (3 nuevos).

## 0.7.0

Integración **opcional** con [ticket-studio](https://github.com/alexisbanda/ticket-studio) (su fase 3). Desactivada por defecto: sin `tickets.contract: true`, el playbook se comporta igual que en la 0.6.

- Config: `tickets.contract` (por defecto `false`) y `tickets.ready_label` (por defecto `ready`).
- `scripts/ticket_check.py`: comprueba la etiqueta de listo y el mínimo del contrato con lógica propia; si Ticket Studio está instalado, añade su puntuación. Un Ticket Studio roto o incompatible nunca rompe la corrida. Avisa, no bloquea.
- `resolve-issue`: con la opción activa, comprueba el ticket y propone resolver los sub-issues de una épica en vez de la épica; con un ticket del contrato, usa sus criterios tal cual y lleva sus preguntas abiertas al plan. Lee `docs/product/BRIEF.md` y `TECH.md` si existen, con o sin la opción.
- Adaptador de GitHub: cómo leer las dos caras, preguntas abiertas, etiquetas, padre y sub-issues.
- Métricas: `ticket_quality` en `metrics.jsonl` y columna "Calidad del ticket" en el informe.
- 101 tests (14 nuevos).

## 0.6.1

- El marketplace lista también [ticket-studio](https://github.com/alexisbanda/ticket-studio), el plugin hermano para que el PM escriba tickets listos para agentes. Sin cambios en el comportamiento de agent-playbook.

## 0.6.0

- **Journeys de regresión** con evidencia: `scripts/run_journeys.py` corre los `journeys` de la configuración, guarda los logs por ticket e imprime la tabla para el comentario de evidencia. `setup-project` propone candidatos.
- **Informe de métricas** (`scripts/metrics_report.py`): tabla por corrida con coste estimado (tarifas en `metrics/prices.json`) y evaluación de 8 tripwires (`metrics/tripwires.json`) sobre las últimas 10 corridas.
- **Skill `tuning-wave`**: lee las métricas de uno o varios repos, mira detrás de cada tripwire que salta y propone de 1 a 3 cambios atados a una métrica, que con OK lleva a un PR en este repositorio.
- Cada línea de métricas registra `playbook_version`, para comparar antes y después de un cambio en los manuales.
- `docs/METRICS.md`, con la tabla de impacto medido de la guía. Tests: 87.

## 0.5.0

- **Gate de merge** (`scripts/merge_gate.py`): comprueba las 4 condiciones (veredicto fresco y anclado, checks en verde, mergeable, espaciado de deploys), imprime el comando de merge con `--match-head-commit` y distingue "todavía no" (1) de "no se puede sin un cambio" (2). Con `--watch` hace de vigilante en segundo plano.
- **Review bot opcional** (`templates/workflows/claude-review.yml`, Claude Code Action `@v1`): revisa los PRs que no están en borrador contra el ticket y sus criterios; su veredicto es el check `claude-review`, ligado al commit. Se monta y desmonta con `review_bot.enabled` y `setup-project`. `docs/REVIEW_BOT.md`.
- Motor: review concurrente con el bot en `standard`, en serie en `critical`; `promoted_at` en UTC; vigilante en lugar de esperar.
- Config: `review_bot.check_name`. Tests del gate de merge (74 en total).

## 0.4.1

Correcciones de la segunda corrida real (pokemon-visiotech#3):

- **Gate de seguridad**: reconoce `gh` y `git` detrás de una variable (`$GH pr merge`), de `env -u …` o con `git -C <dir> push` (comprobando la rama de ese directorio). Antes, un `$GH pr merge` se saltaba las reglas de merge y promoción.
- **Corridas por sesión**: el marcador `active-run` guarda `$CLAUDE_CODE_SESSION_ID`. Otra sesión en el mismo repo ya no contamina las métricas ni pasa por el gate de modelos de la corrida.
- **Telemetría precisa**: los comandos solo cuentan en posición de comando (no si aparecen en un `grep` o un heredoc); `pr_opened` exige la URL del PR en la salida.
- `subagent_done` pasa a `subagent_launched` (marca el lanzamiento; los subagentes corren en segundo plano). `close_run.py` acepta los dos nombres.
- El preflight y `resolve-issue` piden escribir `gh` y `git` literales, sin variables.
- Tests: 57, incluidos los casos de la corrida. Los comandos reales de esa corrida, repasados con los patrones nuevos, dan exactamente 1 worktree, 1 PR abierto, promovido y mergeado.

## 0.4.0

- Hooks (`hooks/hooks.json`), inactivos en repos sin `.claude/agent-playbook.json`:
  - **Gate de modelos** (`PreToolUse` sobre `Agent`/`Task`): aplica `routing.json` durante una corrida; inyecta el modelo que falta, avisa o bloquea según `hooks.mode`, registra los overrides.
  - **Gate de seguridad** (`PreToolUse` sobre `Bash`): push a la rama base, push forzado, merges y promociones desde subagentes, merges sin `--match-head-commit`, `rm -rf` fuera del repo y patrones de producción configurables. En `warn` pide confirmación; en `block` deniega.
  - **Telemetría**: hechos de cada evento en `.agent-playbook/events.jsonl`, sin guardar prompts ni comandos. Aviso al iniciar sesión si los alias de modelo no están fijados.
- `scripts/close_run.py`: al cerrar la corrida, cruza eventos y transcripts y añade una línea validada a `metrics.jsonl` (tiempos, espera al humano, subagentes, PRs, gates, tokens por modelo).
- Corridas con marcador `.agent-playbook/active-run`: lo abre `resolve-issue` tras el preflight y lo quita `close_run.py`.
- Config: `hooks.production_patterns`. Esquema de métricas en `config/metrics.schema.json`.
- `docs/HOOKS.md`. Tests de los hooks en `tests/test_hooks.py` (fallan si un hook registra un error interno).

## 0.3.0

- Ruteo de modelos: `routing/routing.json` (fuente de verdad) con cuatro niveles (`haiku`, `sonnet`, `opus`, `fable`) y las tablas de los perfiles `reduced` y `full`, su esquema y `routing/ROUTING.md`.
- `scripts/route.py`: decide para cada lanzamiento de subagente si inyecta, permite o bloquea el modelo, comprueba el modelo de la sesión y avisa de los alias sin fijar. Lo usará el gate de modelos de la fase 3.
- Reglas: encabezado `ROLE · CLASS` obligatorio, `OVERRIDE: <motivo>` registrado, `fable` nunca escribe código (no se puede saltar), clases de alto riesgo solo en `opus` en ambos perfiles.
- `resolve-issue`, el motor y las plantillas usan la tabla en lugar de modelos fijos. El coder de clase `critical` pasa a `opus`; el reviewer usa la clase `review`.
- CI: valida `routing.json` contra su esquema y corre los tests de `tests/`.

## 0.2.1

Correcciones de la primera corrida real (pokemon-visiotech#1):

- `setup-project` detecta el entorno de tests (local, Laravel Sail, Docker Compose), **ejecuta** el comando antes de guardarlo y propone `worktree_test_command`. Nueva referencia `test-runtimes.md`.
- Nuevo campo `environment.worktree_test_command` con `{worktree}`: los tests de un worktree ya no prueban por error el clon principal cuando el contenedor solo monta este. El motor se detiene si los tests corren en contenedor y el campo falta.
- `setup-project` propone commitear la configuración (con OK); el preflight ya no trata esos archivos como clon sucio.
- El preflight detecta commits locales sin push en la rama base y avisa de que no estarán en el PR.
- Problema conocido documentado: `GITHUB_TOKEN` del entorno que pisa la sesión de `gh`.
- Aprobar el plan autoriza explícitamente los commits, el push de la rama del ticket y el PR en borrador de esa corrida, también cuando hay una regla general de pedir OK antes de commit o push. El merge sigue necesitando OK.

## 0.2.0

- Skill `resolve-issue`: orquestador con preflight, lectores, plan con aprobación, construcción en worktree, review, merge con checklist y cierre con evidencia.
- Referencias compartidas: `preflight`, `engine` (perfil reducido), `closure` y adaptadores de tracker para GitHub Issues y Notion (este último sin probar contra una base real).
- Plantillas: `RUN_STATE`, `HANDBACK`, `CODER_BRIEF`, `REVIEW_BRIEF`, `PR_BODY`, `EVIDENCE`.
- `setup-project` resuelve rutas con `${CLAUDE_SKILL_DIR}`.

## 0.1.0

- Esqueleto del plugin y marketplace privado en el mismo repositorio.
- Configuración por repositorio (`.claude/agent-playbook.json`) con esquema JSON: perfil, gestor de tickets, modo de hooks, review bot, entorno y journeys.
- Skill `setup-project`.
- Documentación de escalado y de gestores de tickets.
- CI: validación estricta de manifiestos y skills, validación del esquema y control de bump de versión.
