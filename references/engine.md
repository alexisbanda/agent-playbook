# Motor de ejecución (perfil `reduced`)

Reglas para construir, revisar y mergear una vez aprobado el plan. Las comparten todos los skills que escriben código. El perfil `full` (coders en paralelo, patriots, gate concurrente, tiers) se describe en `docs/SCALING.md` y se añade aquí sin cambiar estas reglas.

Actualiza `RUN_STATE.md` al terminar cada paso.

## 1. Worktree

Uno por ticket y por repositorio. Lo creas tú, a mano, no con la opción automática de la herramienta.

1. `git fetch origin` justo antes (entre el plan y la construcción puede haber pasado tiempo).
2. **Re-barrido anti-choque:** `gh pr list --state open --search "<palabras clave del ticket>"` y `git branch -r --list "*<ticket>*"`. Si otro PR o rama toca lo mismo, detente y muéstralo.
3. Crea el worktree con rama nueva (`-b` es obligatorio; sin él, el push falla al final):
   ```bash
   git worktree add -b <tipo>/<ticket>-<slug> ../<repo>.worktrees/<ticket>-<slug> origin/<rama-base>
   ```
   `<tipo>` es `feat` o `fix`. `<rama-base>` es la rama por defecto del repo salvo que el ticket diga otra cosa.
4. Revisa excepciones del entorno (detalle por entorno en `references/test-runtimes.md`):
   - Archivos no versionados que el proyecto necesita (`.env`, dependencias instaladas). Copia, enlaza o monta lo necesario y anótalo en `RUN_STATE.md`. Nunca copies secretos a un archivo versionado.
   - Versión del runtime que pide el proyecto frente a la instalada (`references/test-runtimes.md`, «Versión del runtime»). Si hace falta otra, ya va en el plan aprobado: instálala en el espacio del usuario y usa el mismo prefijo en el baseline, el brief del coder y la verificación.
   - Contenedores que montan solo el clon principal (Sail, Docker Compose). Ahí los tests del worktree se corren **siempre** con `environment.worktree_test_command`. Si los tests corren en un contenedor y ese campo está vacío, detente: sin él, el baseline y la verificación probarían el clon principal.

## 2. Baseline

**Comando de tests del worktree** (lo usan el baseline, el coder y la verificación): `environment.worktree_test_command` con `{worktree}` sustituido por la ruta absoluta del worktree, ejecutado desde la raíz del clon principal. Si está vacío, `environment.test_command` con el worktree como directorio de trabajo.

**Caché por SHA base:** obtén el SHA corto de `origin/<rama-base>` (`git rev-parse --short origin/<rama-base>`, o `origin_sha` del preflight). Si ya existe `.agent-playbook/cache/baseline-<sha>.log`, cópialo directamente a `.agent-playbook/runs/<ticket>/baseline.log` sin volver a ejecutar la suite de tests y anota en `RUN_STATE.md` que el baseline salió de caché para ese SHA.

Si no está en caché, córrelo antes de tocar nada y guarda la salida tanto en `.agent-playbook/runs/<ticket>/baseline.log` como en `.agent-playbook/cache/baseline-<sha>.log` (`mkdir -p .agent-playbook/cache`), con un resumen de qué falla. En la primera corrida de un repo, comprueba que de verdad prueba el worktree: por ejemplo, que el listado de tests incluye un archivo que solo existe ahí, o que la ruta en las trazas es la del worktree. Anótalo en `RUN_STATE.md`.

- Las fallas del baseline son **preexistentes**: no son culpa del coder.
- Si no hay `test_command` (por ejemplo, en un proyecto nuevo), anótalo: irá a la sección LÍMITES del cierre.

## 3. Coder

En `resolve-issue` corre un coder a la vez; en `resolve-epic` (o en el perfil `full`) pueden correr hasta 3 coders en paralelo en worktrees distintos **únicamente si** los conjuntos de `archivos que toca` del plan aprobado son estrictamente disjuntos (intersección vacía). Lánzalo con el Agent tool (Claude Code) o `invoke_subagent` (`TypeName: self` en `agy`):

- en Claude Code, `subagent_type: agent-playbook:coder`: el agente `coder` del plugin (`agents/coder.md`) solo carga las herramientas que necesita (Bash, Read, Edit, Write, Grep, Glob) y razona con esfuerzo `medium`. En `critical`, pasa además `effort: high`. Si ese tipo no está disponible (plugin sin recargar), usa `general-purpose`;
- primera línea del prompt: `ROLE: coder · CLASS: <clase del ticket>`;
- `model` / `Model`: el de la clase según `routing/ROUTING.md` (`sonnet`/`inherit` en `standard`, `opus`/`pro` en `critical`). `fable` nunca escribe código;
- el resto del prompt: `templates/CODER_BRIEF.md` rellenado (incluyendo la lista cerrada de archivos que puede tocar y la tabla de chequeos de aceptación del plan, con sus comandos y entradas tal cual).

Pásale en el brief el comando de tests del worktree ya resuelto (paso 2). El coder trabaja solo en su worktree, hace commits convencionales (`feat: …`, `fix: …`), corre los tests, arregla las fallas que él causó, empuja su rama y abre el PR **en borrador** con `templates/PR_BODY.md`. La aprobación del plan ya cubre esos commits, el push de la rama del ticket y el PR en borrador: no se vuelve a pedir OK. Nunca empuja a la rama base, nunca promueve y nunca mergea.

Las fallas preexistentes no las arregla: las lista en su informe. Tú las publicas en el ticket con `comment` o abres un ticket nuevo con `create_ticket`.

## 4. Verificación

Cuando el coder termina, tú verificas:

1. **Tests sin duplicación innecesaria:** comprueba que el worktree está limpio (`git status --porcelain` vacío) y que el coder ejecutó el comando de tests del worktree sobre el SHA actual de `HEAD` sin fallas nuevas respecto al baseline. Si el informe del coder incluye la salida en verde sobre ese mismo SHA y no se ha tocado ningún archivo después, no re-ejecutes toda la suite completa por segunda vez; si no la corrió sobre el commit final, hubo cambios posteriores o hay cualquier duda, corre el comando de tests del worktree (paso 2) y compara con el baseline. Cualquier falla nueva vuelve al coder.
2. Revisa el diff contra el plan aprobado (`git diff origin/<rama-base>...HEAD`). Si se salió del plan, vuelve al coder o, si el cambio es razonable, avísalo al usuario.
3. **Chequeos de aceptación:** el informe del coder trae, por cada chequeo que no es «solo en cierre», el valor observado sobre el SHA de `HEAD`. Si falta alguno, lo corrió sobre otro commit o no coincide con el esperado, vuelve al coder antes de seguir. Si tienes la menor duda, ejecuta tú ese chequeo (uno a uno, no la suite): es barato y es exactamente lo que fallaría en el cierre.
4. Contrasta el cuerpo del PR con el código: cada fila de la tabla criterio → prueba tiene que señalar un test o un assert que exista y compruebe lo que dice. Si el PR afirma más de lo que los tests prueban, pide al coder el assert que falta o corrige la tabla, y cubre la diferencia en la prueba en vivo del cierre.

## 5. Review

| Clase | Review | Orden con el review bot |
| --- | --- | --- |
| `standard` | Tu verificación más el review bot si `review_bot.enabled` | Concurrente: promueves en cuanto tu verificación pasa y el bot revisa mientras tanto |
| `critical` | Reviewer independiente (`ROLE: reviewer · CLASS: review`, `model: opus` porque revisa trabajo crítico, prompt `templates/REVIEW_BRIEF.md`) más el review bot si está activado | En serie: primero el reviewer interno da `APPROVE`, después promueves para que corra el bot |

Hacen falta las dos aprobaciones en cualquier caso; lo concurrente solo ahorra la espera.

El reviewer ve el ticket, los criterios y el diff. Devuelve solo `APPROVE` o `CHANGES_REQUESTED` con la lista de problemas. Las sugerencias menores no bloquean y nunca toca código. Con `CHANGES_REQUESTED`, el coder corrige y el reviewer revisa de nuevo. **Máximo 3 rondas**: si no converge, detente y muéstralo.

## 6. Promoción

Cuando la rama está verde y revisada:

1. `gh pr ready <pr>` y anota la hora UTC en `RUN_STATE.md` (`promoted_at`, por ejemplo con `date -u +%FT%TZ`). Esa hora prueba después que el veredicto del bot es posterior.
2. Si hay que re-disparar al review bot, haz un ciclo `gh pr ready --undo` → `gh pr ready`. **Nunca re-ejecutes la review** desde la UI o la API: revisaría el commit viejo con fecha nueva.
3. No empujes cambios a un PR en borrador para promoverlo enseguida: la review puede saltarse. Empuja, espera a que la CI arranque y después promueve.

## 7. Merge: gate de 4 condiciones

Solo tú mergeas, y solo con OK explícito del usuario. Las condiciones las comprueba `<plugin>/scripts/merge_gate.py`, desde la raíz del clon principal:

```bash
python3 <plugin>/scripts/merge_gate.py <pr> --promoted-at <promoted_at>
```

| # | Condición | Qué mira |
| --- | --- | --- |
| 1 | Veredicto fresco y anclado | Con review bot: el check `claude-review` sobre el HEAD actual del PR, en verde y terminado después de `promoted_at`. Sin bot: tu revisión interna sobre ese HEAD |
| 2 | Checks en verde | Ningún check del HEAD fallido ni pendiente. Sin checks configurados pasa, pero va a LÍMITES |
| 3 | Mergeable | Sin conflictos, no por detrás de la base, no en borrador |
| 4 | Espaciado de deploys | `environment.deploy_check`, o ningún workflow en curso en la rama base |

Resultados: código 0 = listo (imprime el comando de merge exacto, con `--match-head-commit`); 1 = todavía no; 2 = no se puede sin un cambio (PR cerrado, cambios pedidos por el bot, check fallido): **detén la corrida** y muestra la tabla.

**Vigilante.** Si hay que esperar al bot o a la CI, no te quedes esperando: lanza el gate en segundo plano con `--watch` (repite cada 30 s, hasta 1 hora) y sigue con otra cosa o termina tu turno. Te avisará cuando salga con 0 o 2.

Con el gate en 0, muestra su tabla y el SHA, pide el OK y ejecuta el comando que imprimió. `--match-head-commit` ata el merge al commit revisado: si alguien empujó después, falla.

Si el modo automático de Claude Code deniega el merge, no lo esquives: dale al usuario ese mismo comando para que lo ejecute él, y sugiere añadir la regla de permisos del paso 10 de `setup-project` para que la próxima vez no haga falta (ver [Problemas conocidos](preflight.md#problemas-conocidos)) y sigue con el cierre cuando confirme. La telemetría lo cuenta como `prs_merged_outside`.

## 8. Nada de agentes estacionados ni sesiones interminables

Un agente que tendría que esperar algo externo más de unos 5 minutos (una review, la CI, un deploy, una decisión) termina su turno y deja `HANDBACK.md` (plantilla en `templates/`) en su worktree. Para retomarlo, lanza un agente nuevo de la misma clase que empiece leyendo ese archivo. Un agente dormido acumula contexto que cuesta caro reescribir; uno nuevo con un resumen arranca liviano.

**Al terminar tu turno con trabajo en segundo plano** (un coder, un lector, el vigilante del merge, la CI), ciérralo con una línea que diga qué corre, cuánto suele tardar y que avisarás solo, por ejemplo: «El coder está en marcha (suele tardar 10–20 min). Te aviso cuando termine; no hace falta que preguntes». La notificación del agente te despierta, así que el usuario no necesita preguntar «¿cómo va?». En castkit y recuerdos hubo unas 13 preguntas así en 12 corridas, cada una una parada más y una llamada más del orquestador sobre todo su contexto. Si el usuario pregunta igualmente, contesta en una línea con el estado, sin relanzar nada.

**Relevo por contexto.** Lo mismo vale para un coder que trabaja demasiado tiempo: cada llamada relee todo su contexto, así que el coste crece casi con el cuadrado de su longitud (en castkit#56, dos coders llegaron a 428k tokens y costaron 27 de los 32 USD de la corrida). El vigilante `hooks/context_guard.py` avisa al coder cuando supera `hooks.coder_ctx_handback_k` (150k por defecto) u 80 llamadas, y el coder commitea, deja `HANDBACK.md` y termina. Si un coder vuelve con un `HANDBACK.md` en lugar de un PR:

1. Comprueba que el worktree está limpio y que el último commit existe (`git -C <worktree> log -1 --oneline`).
2. Lanza un coder nuevo de la misma clase con el mismo brief y, en la sección «Qué hacer», el contenido del `HANDBACK.md` como punto de partida. No le pases el informe largo del anterior.
3. Anota el relevo en `RUN_STATE.md`. Más de dos relevos en un ticket es señal de que el plan era demasiado grande: detente y propón partirlo.

## 9. Limpieza

Después del merge: `git worktree remove ../<repo>.worktrees/<ticket>-<slug>` y `git branch -D <rama>` en el clon principal. Anótalo en `RUN_STATE.md`.
