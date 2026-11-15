# Hooks

Un skill es un manual que el modelo elige seguir. Un hook es un script que Claude Code ejecuta solo cuando ocurre un evento, lo quiera el modelo o no. Lo que de verdad importa del playbook está en los dos sitios: explicado en los skills y garantizado por estos hooks.

Los hooks se registran en [`hooks/hooks.json`](../hooks/hooks.json) y son Python sin dependencias.

## Cuándo están activos

| Situación | Gate de modelos | Gate de seguridad | Vigilante de contexto | Telemetría |
| --- | --- | --- | --- | --- |
| Repo sin `.claude/agent-playbook.json` | Inactivo | Inactivo | Inactivo | Inactiva |
| Repo configurado, sin corrida abierta | Solo registra | Activo | Inactivo | Activa |
| Corrida abierta (`.agent-playbook/active-run`), en la sesión que la abrió o sus subagentes | Activo | Activo | Activo en los coders | Activa, etiquetada con el ticket |
| Corrida abierta, pero desde **otra** sesión en el mismo repo | Solo registra | Activo | Inactivo | Activa, sin etiquetar |

El plugin se instala por usuario, así que los hooks se disparan en todos los proyectos: por eso no hacen nada donde el playbook no está configurado.

`resolve-issue` abre la corrida al terminar el preflight escribiendo `<ticket> <id de sesión>` en el marcador (`$CLAUDE_CODE_SESSION_ID`), y `close_run.py` la cierra. Guardar la sesión evita que otra sesión que trabaje en el mismo repo (por ejemplo, una que vigila la corrida) contamine sus métricas o pase por su gate. Un marcador sin sesión, del formato anterior, se aplica a todas las sesiones.

## Modos (`hooks.mode`)

| Modo | Gate de modelos | Gate de seguridad |
| --- | --- | --- |
| `warn` (por defecto) | Deja pasar y añade un aviso al contexto del modelo | Pide confirmación al usuario |
| `block` | Deniega el lanzamiento y le dice al modelo por qué | Deniega el comando |
| `off` | Solo registra | Solo registra |

En los tres modos, si un lanzamiento de subagente no indica modelo, el gate **inyecta** el de su clase.

Para endurecer: deja `warn` hasta que la telemetría muestre pocos falsos positivos (eventos `model_gate` y `safety_gate` en `events.jsonl`), y entonces cambia a `block`. Un hook nuevo entra siempre en `warn`.

## Gate de modelos

`PreToolUse` sobre `Agent` y `Task`. Aplica [`routing/routing.json`](../routing/ROUTING.md) con `scripts/route.py`:

| Situación | Resultado |
| --- | --- |
| Sin modelo | Inyecta el de la clase |
| Modelo que la clase no permite | Bloquea (o avisa en `warn`) |
| `fable` para un `coder` o `patriot` | Bloquea siempre, también con `OVERRIDE` |
| Sin encabezado `ROLE · CLASS` o clase inexistente | Bloquea (o avisa) |
| `OVERRIDE: <motivo>` en las primeras líneas | Deja pasar y registra el motivo |

## Gate de seguridad

`PreToolUse` sobre `Bash`. Activo en cualquier repo configurado, haya corrida o no.

| Regla | Por qué |
| --- | --- |
| Push directo a la rama base (`main`, `master` o la de `origin/HEAD`), explícito o con un `git push` estando en ella | Todo cambio entra por PR. Compensa no tener protección de rama |
| Push forzado (`--force`, `--force-with-lease`, `-f`, `+refspec`) | Reescribe historia ajena |
| `gh pr merge` desde un subagente | Solo el orquestador mergea, con OK del usuario |
| `gh pr merge` sin `--match-head-commit` | El merge tiene que atarse al commit revisado |
| `gh pr ready` desde un subagente | Los coders no promueven |
| `rm -rf` fuera del repo y de su carpeta de worktrees (o sobre ellos mismos) | Borrado irreversible |
| Comandos que coinciden con `hooks.production_patterns` | Escrituras en producción: confirmación explícita |

El análisis es por expresiones sobre el texto del comando y es deliberadamente amplio: reconoce `gh` y `git` con ruta, detrás de `env -u …`, de una variable (`$GH`, `${GIT}`) y `git -C <dir> push` (comprobando la rama de ese directorio). Un falso positivo solo pide confirmación; un falso negativo dejaría pasar la acción. Atrapa los errores honestos, no a alguien decidido a saltárselo.

## Vigilante de contexto del coder

`PostToolUse` sobre `Bash`, `Read`, `Edit`, `Write`, `Grep` y `Glob`, solo en Claude Code, durante una corrida abierta y solo dentro de un subagente cuyo prompt empieza con `ROLE: coder` o `ROLE: patriot` ([`hooks/context_guard.py`](../hooks/context_guard.py)).

Lee el transcript del propio subagente y, cuando su contexto supera `hooks.coder_ctx_handback_k` (150k por defecto) o pasa de 80 llamadas, añade al contexto del coder la instrucción de commitear lo que esté en verde, dejar `HANDBACK.md` y terminar su turno. Vuelve a avisar cada 50k tokens más. Nunca bloquea una llamada y no hace nada en modo `off`. Cada aviso queda como evento `context_guard` y `close_run.py` los cuenta en `context_guard_warnings`.

Por qué: cada llamada de un agente relee todo su contexto. En castkit, coders de 200 llamadas llegaron a 428k tokens y fueron la mayor parte del coste de la corrida. El orquestador retoma con un coder nuevo desde el `HANDBACK.md` (ver `references/engine.md`, paso 8).

## Telemetría

Una línea por evento en `.agent-playbook/events.jsonl` (no versionado). **No guarda el contenido** de prompts ni comandos: solo los hechos.

| Evento de Claude Code | Qué se registra |
| --- | --- |
| `SessionStart` / `SessionEnd` | Inicio y fin, ruta del transcript |
| `UserPromptSubmit` | Que el usuario escribió (longitud, no el texto). `automatic: true` si el mensaje empieza por una etiqueta (`<task-notification>`, `<system-reminder>`…): es la herramienta despertando la sesión, no el humano respondiendo |
| `Stop` | Fin de turno: el modelo espera al humano |
| `SubagentStart` / `SubagentStop` | Subagentes lanzados y terminados |
| `PostToolUse` sobre `Agent` | `subagent_launched`: rol, clase, modelo y override. Los subagentes corren en segundo plano, así que este evento marca el lanzamiento; el final es `SubagentStop` |
| `PostToolUse` sobre `Bash` | PR abierto (solo si la salida trae la URL del PR), promovido o mergeado; worktree creado o borrado. Solo cuenta un comando **ejecutado**: el texto que lo menciona (un `grep`, un heredoc, un brief) no cuenta |
| `PostToolUse` sobre `AskUserQuestion` | Pregunta al humano |
| `PreCompact` | Compactación de contexto |
| Gates | Cada decisión `model_gate` y `safety_gate` |

En `SessionStart`, si los alias de modelo no están fijados (`ANTHROPIC_DEFAULT_*_MODEL`), añade un aviso al contexto.

## Métricas de la corrida

Al cerrar, `scripts/close_run.py <ticket>` cruza los eventos con los transcripts y añade **una línea validada** (esquema en [`config/metrics.schema.json`](../config/metrics.schema.json)) a `.agent-playbook/metrics.jsonl`:

- minutos totales y minutos esperando al humano;
- subagentes por modelo, PRs abiertos, promovidos y mergeados, worktrees, compactaciones;
- decisiones de los gates y overrides;
- tokens por modelo (entrada, salida, lectura y escritura de caché), leídos de los transcripts;
- `second_review` y `gemini_readers` (llamadas, degradadas, tokens y segundos de Gemini vía `agy`, leídos de `second-review.jsonl`, `RUN_STATE.md` y `gemini-readers.jsonl`, ya que corren por CLI y no pasan por `model_gate.py`);
- `e2e_first_pass`, el único campo declarado por el orquestador, marcado como tal.

## Errores de los hooks

Un hook que falla **no rompe la sesión**: deja la traza en `.agent-playbook/hook-errors.log` y sale sin bloquear. El preflight de `resolve-issue` avisa si ese archivo tiene entradas. Los tests (`tests/test_hooks.py`) fallan si algún hook escribe en él.

## Probar los hooks

```bash
python3 -m unittest discover -s tests -v
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","cwd":"'$PWD'","tool_input":{"command":"git push origin main"}}' | python3 hooks/safety_gate.py
```
