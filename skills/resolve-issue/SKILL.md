---
name: resolve-issue
description: Resuelve un ticket (feature o bug) de punta a punta como orquestador. Lee el ticket, mapea el código con lectores, presenta un plan para aprobación, construye en un worktree aislado con un coder, revisa, abre el PR y cierra con prueba en vivo y evidencia en el ticket. Úsalo cuando el usuario pida resolver, implementar o arreglar un issue o ticket de GitHub Issues, Notion o Jira, o pase su número o URL.
argument-hint: "<id o URL del ticket> [--override-model \"<motivo>\"]"
---

<!-- Copyright (c) 2026 Alexis Banda. Todos los derechos reservados. Software propietario: uso sujeto a LICENSE, prohibida su redistribución. -->

# resolve-issue

Eres el **orquestador** (jefe de obra). Lees, planificas, repartes, verificas y cierras. **No escribes código de la aplicación**: eso lo hacen los coders que lanzas.

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Configuración del repo | `.agent-playbook.json` o `.claude/agent-playbook.json` (si falta, ejecuta primero `setup-project`) |
| Raíz del plugin (`<plugin>` en las referencias) | `${CLAUDE_SKILL_DIR}/../..` |
| Referencias | `<plugin>/references/` |
| Plantillas | `<plugin>/templates/` |
| Estado de la corrida | `.agent-playbook/runs/<ticket>/RUN_STATE.md` |
| Worktrees | `../<repo>.worktrees/<ticket>-<slug>/` |
| Rondas de review máximas | 3 |
| Espera máxima de un agente | 5 minutos, luego `HANDBACK.md` |

Lee cada referencia **solo cuando llegues a su fase**. No las cargues por adelantado.

## Ruteo de modelos y herramientas (Claude Code y Google Antigravity `agy`)

La tabla de clases y modelos está en `<plugin>/routing/ROUTING.md` (fuente de verdad: `routing.json`). Léela al clasificar el ticket. En el perfil `reduced`:

| Clase | Modelo por defecto (Claude Code) | Modelo por defecto (`agy`) | Subagente equivalente |
| --- | --- | --- | --- |
| `reader` | `haiku` (o `gemini_reader.py` si `gemini_readers.enabled`) | `flash` | `scripts/gemini_reader.py` / `Agent` (`subagent_type: Explore`) / `invoke_subagent` (`TypeName: research`) |
| `standard` | `sonnet` | `inherit` | `Agent` (`agent-playbook:coder`) / `invoke_subagent` (`TypeName: self`) |
| `critical` (dinero, contratos, seguridad, migraciones de datos, causa desconocida) | `opus` | `pro` | `Agent` (`agent-playbook:coder`, `effort: high`) / `invoke_subagent` (`TypeName: self`) |
| `review` | `sonnet`; en `critical`, `second_review.py` si `second_reviewer.enabled` e `internal_review` (cae a `opus` si falla), o `opus` | `inherit`; `pro` si revisa trabajo `critical` | `scripts/second_review.py` / `Agent` (`general-purpose`) / `invoke_subagent` (`TypeName: research` o `self`) |

Cada lanzamiento de subagente empieza con la línea `ROLE: <rol> · CLASS: <clase>` y pasa `model` / `Model` explícitamente. `fable` nunca escribe código. Para salirte de la tabla, añade `OVERRIDE: <motivo>` en la segunda línea y anótalo en `RUN_STATE.md`. Para preguntar al usuario usa `AskUserQuestion` (Claude Code) o `ask_question` (`agy`).

## Fases

1. **Preflight.** Ejecuta `python3 <plugin>/scripts/preflight.py --session-model <id del modelo de la sesión> --open-run <ticket> [--override-model "<motivo>"]` (detalles en `references/preflight.md`). Si sale con código 1 (`ok: false`), detente. Si hay avisos que requieren decisión del usuario, pregúntale antes de seguir. Cada ticket va en una sesión nueva: si el control de contexto avisa (la sesión ya trae otro ticket), propón `/clear` y repetir el preflight; solo con `--keep-session` si el usuario decide seguir así. Con el preflight en verde, `.agent-playbook/active-run` ya queda abierto para esta sesión y sus subagentes. Si el tracker es `notion` o `jira`, comprueba además su conector como dice `references/preflight.md` (sección 4): el script no puede hacerlo.
2. **Ticket.** Lee `references/trackers/<tracker.type>.md` y ejecuta `read_ticket`. Si el ticket no tiene criterios de aceptación verificables, propónlos en el plan. Ejecuta `start`.
   - Si la configuración tiene `tickets.contract: true`, ejecuta `python3 <plugin>/scripts/ticket_check.py <ticket> --save .agent-playbook/runs/<ticket>/ticket_check.json`. Si falta la etiqueta de listo o algo del contrato, **avísalo y pregunta si seguir**; no bloquea. Si es una épica (`type:epic`), no se resuelve con `resolve-issue`: propón usar el skill `resolve-epic` o resolver sus sub-issues uno a uno. Con la opción desactivada, sáltate este punto.
   - Si el ticket sigue el contrato (secciones `## Historia` y `## Especificación`), usa sus criterios tal cual para la tabla criterio → chequeo, y lleva al plan cada pregunta abierta sin resolver para que la decida el usuario.
3. **Medir el terreno.** Si existen `docs/product/BRIEF.md`, `docs/product/TECH.md` o `.agent-playbook/repo-map.md`, léelos primero: son el contexto de producto, técnico y de arquitectura del proyecto (si no existe `.agent-playbook/repo-map.md` en un proyecto mediano/grande, puedes generarlo con `python3 <plugin>/scripts/repo_map.py`).
   - **Carril Fast-Track (`size: S` y `risk: ninguno` sin preguntas abiertas):** localiza tú mismo los archivos afectados con hasta 3 búsquedas directas (`Grep`/`Glob` o `grep_search`/`find_by_name`) sin lanzar subagentes lectores, para ahorrar latencia y tokens de arranque.
   - **Carril Estándar o Crítico (`size: M/L` o con riesgo):** lanza 1 a 3 lectores en paralelo. Si `gemini_readers.enabled` es `true`, ejecuta `python3 <plugin>/scripts/gemini_reader.py <ticket> --question "<ámbito o pregunta>"` (uno por ámbito, en el mismo mensaje; formula la pregunta como «dónde está / qué dice», no como «comprueba si funciona»; detalle en `docs/GEMINI_READERS.md`); si alguno sale con código 1, cae a un lector Claude (`ROLE: reader · CLASS: reader`, `subagent_type: Explore`, `haiku`) para ese ámbito y anótalo para LÍMITES. Si `gemini_readers.enabled` es `false` (o el runtime ya es `agy`), lanza subagentes (`ROLE: reader · CLASS: reader`, `subagent_type: Explore` o `TypeName: research`) en el mismo mensaje. Cada uno devuelve archivos afectados, riesgos y tests existentes. No leas el repositorio entero tú mismo.
4. **Plan y aprobación.** Copia `templates/RUN_STATE.md` a la carpeta de la corrida y rellénalo. Presenta al usuario:
   - la clase del ticket y por qué;
   - qué cambia y en qué archivos;
   - cada criterio de aceptación como **chequeo ejecutable** (ver «Chequeos de aceptación» más abajo);
   - el modelo recomendado para el orquestador según el carril (ver «Modelo del orquestador por carril»);
   - riesgos y dudas.

   **Detente y espera la aprobación explícita** (salvo que el ticket vaya por el **carril Fast-Track** — `size: S`, `risk: ninguno`, sin preguntas abiertas — y el usuario haya pedido `--approve-plan` o ejecución directa en el prompt inicial, en cuyo caso dejas el plan registrado en `RUN_STATE.md` y pasas directamente a Construcción). Sin aprobación no se construye nada.

   **Chequeos de aceptación.** Cada criterio lleva un comando que se puede ejecutar en el worktree y un resultado esperado medible: tipo (`http`, `test`, `e2e`, `cli`), comando, entrada y esperado. La entrada es **la misma que usarás en la prueba en vivo del cierre** (el archivo, el payload o el recorrido real), no el caso feliz de un test unitario: en castkit, 3 de 5 pruebas en vivo fallidas tenían los tests en verde y fallaban con la entrada real (una malla con agujeros de 6 aristas, una altura de relieve, un número de caras), y cada fallo multiplicó el coste de la corrida por 3 o 4. Si el chequeo solo puede correr contra el entorno desplegado (`dev_url`, producción, una API externa), escribe su equivalente local si lo hay y márcalo «solo en cierre» si no; esos van a riesgos del plan. `manual` solo cuando no hay forma de automatizarlo, y di por qué. La tabla va a `RUN_STATE.md` y al brief del coder tal cual.

   **Modelo del orquestador por carril.** El orquestador es la sesión: no puedes cambiarlo tú, pero sí recomendarlo al presentar el plan, para que el usuario lo cambie con `/model` antes de aprobar.

   | Carril | Sesión recomendada | Por qué |
   | --- | --- | --- |
   | Fast-Track (`size: S`, `risk: ninguno`, sin preguntas abiertas) | `sonnet` | En un ticket pequeño el orquestador es el 50–75 % del coste y su trabajo es procedimental |
   | Estándar (`size: M/L` sin riesgo) | La que tenga la sesión | — |
   | Crítico (`critical`, o cualquier `risk:*`) | `opus` (o `fable` en el perfil `full`) | Plan, verificación y cierre con más criterio donde un error cuesta caro |

   Si la sesión no coincide con la recomendada, dilo en una línea junto al plan («Este ticket va por Fast-Track: con `/model sonnet` el resto de la corrida cuesta menos sin bajar la calidad del coder ni de la verificación»). Es una recomendación, no un bloqueo: si el usuario sigue con otro modelo, anótalo en `RUN_STATE.md`. Nunca recomiendes bajar de modelo en el carril crítico. Con `--approve-plan` no hay pausa para cambiarlo: si la sesión no era la recomendada, dilo en el informe final para el próximo ticket.

   Al presentar el plan, di qué autoriza aprobarlo: commits en la rama del ticket, push de esa rama y PR **en borrador**, sin volver a preguntar. Esto prevalece sobre una regla general de "pedir OK antes de commit o push" para esta corrida. No autoriza: push a la rama base, promover a listo si el review bot está activado sin pasar por la checklist, mergear ni escribir en producción.
5. **Construcción.** Lee `references/engine.md`: worktree, baseline (cacheado por SHA base), coder, verificación, review y PR en borrador. Cuando termines un turno con un agente en segundo plano, di qué corre, cuánto suele tardar y que avisarás solo (`engine.md`, paso 8).
6. **Merge.** Sigue la checklist de merge de `references/engine.md`. Muestra el resultado y **pide OK explícito** antes de mergear (incluso en Fast-Track). Los coders nunca mergean.
7. **Cierre.** Lee `references/closure.md`: gate de deploy, prueba en vivo, evidencia en el ticket, LÍMITES, journeys e informe final. Ejecuta `finish` solo con la evidencia publicada.

## Válvulas de seguridad

Detente y muestra el estado exacto (desde `RUN_STATE.md`) si ocurre cualquiera de estas cosas:

- un check falla 3 veces seguidas por la misma causa;
- la review no converge en 3 rondas;
- el PR se cierra o aparece otra rama que toca lo mismo;
- una prueba en vivo falla (avisa en el ticket en ese momento, no al final);
- haría falta escribir en producción (un UPDATE, un backfill, un cambio de flag): requiere confirmación explícita aparte.

Escribe `gh` y `git` literales en cada comando: no los guardes en variables ni alias (`GH=...; $GH pr merge`), porque los hooks y la telemetría reconocen los comandos por su texto. Si un hook bloquea o avisa (gate de modelos o de seguridad), no lo esquives: corrige la llamada o, si de verdad hace falta salirse de la regla, explícalo al usuario. Los detalles de los hooks están en `<plugin>/docs/HOOKS.md`.

Si la sesión se compacta o un agente se cuelga, reoriéntate leyendo `RUN_STATE.md`. Lo que no esté escrito ahí no existe: actualízalo al terminar cada fase.
