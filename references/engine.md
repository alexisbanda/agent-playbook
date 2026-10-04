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
   - Contenedores que montan solo el clon principal (Sail, Docker Compose). Ahí los tests del worktree se corren **siempre** con `environment.worktree_test_command`. Si los tests corren en un contenedor y ese campo está vacío, detente: sin él, el baseline y la verificación probarían el clon principal.

## 2. Baseline

**Comando de tests del worktree** (lo usan el baseline, el coder y la verificación): `environment.worktree_test_command` con `{worktree}` sustituido por la ruta absoluta del worktree, ejecutado desde la raíz del clon principal. Si está vacío, `environment.test_command` con el worktree como directorio de trabajo.

Antes de tocar nada, córrelo y guarda la salida en `.agent-playbook/runs/<ticket>/baseline.log`, con un resumen de qué falla. En la primera corrida de un repo, comprueba que de verdad prueba el worktree: por ejemplo, que el listado de tests incluye un archivo que solo existe ahí, o que la ruta en las trazas es la del worktree. Anótalo en `RUN_STATE.md`.

- Las fallas del baseline son **preexistentes**: no son culpa del coder.
- Si no hay `test_command` (por ejemplo, en un proyecto nuevo), anótalo: irá a la sección LÍMITES del cierre.

## 3. Coder

Uno a la vez. Lánzalo con el Agent tool:

- primera línea del prompt: `ROLE: coder · CLASS: <standard|critical>`;
- `model`: `sonnet` en ambas clases (`opus` nunca escribe código);
- el resto del prompt: `templates/CODER_BRIEF.md` rellenado.

Pásale en el brief el comando de tests del worktree ya resuelto (paso 2). El coder trabaja solo en su worktree, hace commits convencionales (`feat: …`, `fix: …`), corre los tests, arregla las fallas que él causó, empuja su rama y abre el PR **en borrador** con `templates/PR_BODY.md`. La aprobación del plan ya cubre esos commits, el push de la rama del ticket y el PR en borrador: no se vuelve a pedir OK. Nunca empuja a la rama base, nunca promueve y nunca mergea.

Las fallas preexistentes no las arregla: las lista en su informe. Tú las publicas en el ticket con `comment` o abres un ticket nuevo con `create_ticket`.

## 4. Verificación

Cuando el coder termina, tú verificas, no confías en su resumen:

1. Corre el comando de tests del worktree (paso 2) y compara con el baseline. Cualquier falla nueva vuelve al coder.
2. Revisa el diff contra el plan aprobado. Si se salió del plan, vuelve al coder o, si el cambio es razonable, avísalo al usuario.

## 5. Review

| Clase | Review |
| --- | --- |
| `standard` | Tu verificación más el review bot si `review_bot.enabled` |
| `critical` | Reviewer independiente (`ROLE: reviewer · CLASS: critical`, `model: opus`, prompt `templates/REVIEW_BRIEF.md`) más el review bot si está activado |

El reviewer ve el ticket, los criterios y el diff. Devuelve solo `APPROVE` o `CHANGES_REQUESTED` con la lista de problemas. Las sugerencias menores no bloquean y nunca toca código. Con `CHANGES_REQUESTED`, el coder corrige y el reviewer revisa de nuevo. **Máximo 3 rondas**: si no converge, detente y muéstralo.

## 6. Promoción

Cuando la rama está verde y revisada:

1. `gh pr ready <pr>` y anota la hora en `RUN_STATE.md` (`promoted_at`). Esa hora prueba después que el veredicto del bot es posterior.
2. Si hay que re-disparar al review bot, haz un ciclo `gh pr ready --undo` → `gh pr ready`. **Nunca re-ejecutes la review** desde la UI o la API: revisaría el commit viejo con fecha nueva.
3. No empujes cambios a un PR en borrador para promoverlo enseguida: la review puede saltarse. Empuja, espera a que la CI arranque y después promueve.

## 7. Merge: checklist de 4 condiciones

Solo tú mergeas, y solo con OK explícito del usuario.

| # | Condición | Cómo se comprueba |
| --- | --- | --- |
| 1 | Veredicto fresco y anclado | Con review bot: su review `APPROVED` tiene `submitted_at` posterior a `promoted_at` y `commit_id` igual al HEAD del PR. Sin bot: el `APPROVE` del reviewer (o tu verificación en `standard`) es sobre el HEAD actual |
| 2 | Checks en verde | `gh pr checks <pr>` sin fallos ni pendientes |
| 3 | Mergeable | `gh pr view <pr> --json mergeable,mergeStateStatus` → `MERGEABLE` y no `BEHIND`/`DIRTY` |
| 4 | Espaciado de deploys | No hay un deploy en curso del mismo repo (`environment.deploy_check`, o `gh run list` del workflow de deploy) |

Muestra la tabla con el resultado de cada fila y el SHA. Con el OK:

```bash
gh pr merge <pr> --squash --delete-branch --match-head-commit <sha>
```

`--match-head-commit` ata el merge al commit revisado: si alguien empujó después, falla.

## 8. Nada de agentes estacionados

Un agente que tendría que esperar algo externo más de unos 5 minutos (una review, la CI, un deploy, una decisión) termina su turno y deja `HANDBACK.md` (plantilla en `templates/`) en su worktree. Para retomarlo, lanza un agente nuevo de la misma clase que empiece leyendo ese archivo. Un agente dormido acumula contexto que cuesta caro reescribir; uno nuevo con un resumen arranca liviano.

## 9. Limpieza

Después del merge: `git worktree remove ../<repo>.worktrees/<ticket>-<slug>` y `git branch -D <rama>` en el clon principal. Anótalo en `RUN_STATE.md`.
