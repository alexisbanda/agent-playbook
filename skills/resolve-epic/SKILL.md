---
name: resolve-epic
description: Resuelve los tickets hijos de una épica por olas de dependencias (Wave Runner). Lee la épica y sus sub-issues, agrupa en olas los tickets listos (ready), presenta un plan maestro para aprobación y ejecuta cada ola con coders en worktrees aislados (en paralelo cuando sus archivos tocados son disjuntos). Úsalo cuando el usuario pida resolver una épica completa o un grupo de tickets de una épica en GitHub Issues, Notion o Jira.
argument-hint: "<id o URL de la épica> [--wave <N>]"
---

# resolve-epic

Eres el **orquestador de olas** (Wave Runner). Una épica (`type:epic`) no se resuelve con un único PR monolítico: se resuelve ejecutando sus sub-issues en orden topológico de dependencias (`### Dependencias`), agrupados en **olas** (waves).

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Configuración del repo | `.agent-playbook.json` o `.claude/agent-playbook.json` |
| Raíz del plugin (`<plugin>`) | `${CLAUDE_SKILL_DIR}/../..` |
| Mapa de arquitectura | `.agent-playbook/repo-map.md` (generado/actualizado con `python3 <plugin>/scripts/repo_map.py`) |
| Estado de la épica | `.agent-playbook/runs/epic-<id>/EPIC_STATE.md` |
| Estado de cada ticket hijo | `.agent-playbook/runs/<ticket>/RUN_STATE.md` |
| Coders paralelos máximos por ola | 3 (solo si los conjuntos de archivos que tocan son estrictamente disjuntos) |

## Fases

1. **Preflight y Mapa de Arquitectura.**
   - Ejecuta `python3 <plugin>/scripts/preflight.py --session-model <id del modelo de la sesión> --open-run epic-<id>`. La épica empieza en una sesión nueva: si el control de contexto avisa, propón `/clear` y repetir el preflight (`--keep-session` solo si el usuario decide seguir así).
   - Si el tracker es `notion` o `jira`, comprueba su conector como dice `references/preflight.md` (sección 4) antes de leer la épica.
   - Si no existe `.agent-playbook/repo-map.md` (o quedó desactualizado), ejecuta `python3 <plugin>/scripts/repo_map.py` para construir el mapa persistente del repositorio. Léelo junto con `docs/product/BRIEF.md` y `docs/product/TECH.md` si existen.

2. **Lectura de la épica y sus tickets hijos.**
   - Lee `references/trackers/<tracker.type>.md` y obtén la épica y todos los sub-issues listados en `## Tickets` (o vinculados como hijos en el tracker).
   - Si `tickets.contract: true`, pasa `scripts/ticket_check.py` sobre cada sub-issue. Los tickets sin `ready` o con preguntas abiertas sin resolver se reportan al usuario antes de armar las olas.

3. **Construcción del grafo de olas (DAG) y barrido de archivos.**
   - Ordena los tickets hijos según su sección `### Dependencias`:
     - **Ola 1:** tickets sin dependencias pendientes.
     - **Ola $k$:** tickets cuyas dependencias quedan resueltas en olas $\le k - 1$.
   - Para los tickets de la ola actual, determina qué archivos toca cada uno:
     - Tickets `size: S` + `risk: ninguno`: hasta 3 búsquedas directas sobre `.agent-playbook/repo-map.md` y el código.
     - Tickets `size: M/L` o con riesgo: lanza lectores en un solo mensaje pasando el resumen de `.agent-playbook/repo-map.md`. Si `gemini_readers.enabled` es `true`, usa `python3 <plugin>/scripts/gemini_reader.py epic-<id> --question "<ticket y ámbito>"` (si sale con código 1, cae a un subagente `ROLE: reader · CLASS: reader`, `haiku`, y anótalo en LÍMITES); si no, subagentes `ROLE: reader · CLASS: reader`.
   - **Partición de paralelismo intra-repo:** dos tickets de la misma ola pueden ejecutarse con coders en paralelo (cada uno en su propio worktree `../<repo>.worktrees/<ticket>-<slug>`) **únicamente si** la intersección de sus archivos tocados (`archivos que toca`) es vacía y no modifican la misma migración o configuración global. Si hay solapamiento de archivos, colócalos en sub-turnos secuenciales dentro de la ola.

4. **Plan Maestro de la Ola y aprobación.**
   - Presenta al usuario la tabla de olas de la épica y el detalle de la ola a ejecutar:
     - Tickets incluidos, clase de cada uno, archivos que toca cada ticket y cuáles corren en paralelo vs. en serie.
     - Tabla criterio → chequeo de cada ticket de la ola.
   - **Detente y espera la aprobación explícita del usuario** para la ola.

5. **Ejecución de la Ola (Construcción y Verificación).**
   - Sigue `references/engine.md` para cada ticket de la ola:
     - Crea los worktrees de la ola desde `origin/<rama-base>`.
     - Ejecuta o reutiliza el baseline cacheado por SHA (`baseline-<sha>.log`).
     - Lanza los coders autorizados en paralelo (máximo 3, con archivos disjuntos) o en serie usando `Agent` con `subagent_type: agent-playbook:coder` (Claude Code; ver `references/engine.md`, paso 3) o `invoke_subagent` (`agy`). Si un coder vuelve con `HANDBACK.md`, aplica el relevo por contexto de `references/engine.md`, paso 8.
     - Verifica cada worktree, pasa review según su clase (`standard` vs `critical`) y promueve cada PR cuando esté en verde.

6. **Merge ordenado y refresco entre olas.**
   - Para cada PR de la ola, ejecuta `python3 <plugin>/scripts/merge_gate.py <pr> --promoted-at <promoted_at>`, muestra la tabla y **pide OK explícito** antes de mergear.
   - Tras mergear cada PR y cerrar su ticket (`references/closure.md`), actualiza `origin/<rama-base>`, limpia su worktree y refresca `.agent-playbook/repo-map.md` (`python3 <plugin>/scripts/repo_map.py`) antes de arrancar la siguiente ola. Antes de esa ola, deja `RUN_STATE.md` al día con el punto de retoma: si la sesión supera unos 300k tokens de contexto, propón al usuario `/clear` y retomar la épica desde ahí, repitiendo el preflight con `--open-run epic-<id>` para que la corrida pase a la sesión nueva.

7. **Cierre de la épica.**
   - Cuando todos los tickets hijos estén cerrados con evidencia, publica un comentario resumen en la épica con la tabla de PRs mergeados, ejecuta `finish` sobre la épica y cierra la corrida con `scripts/close_run.py`.
