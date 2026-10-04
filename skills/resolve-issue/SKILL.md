---
name: resolve-issue
description: Resuelve un ticket (feature o bug) de punta a punta como orquestador. Lee el ticket, mapea el código con lectores, presenta un plan para aprobación, construye en un worktree aislado con un coder, revisa, abre el PR y cierra con prueba en vivo y evidencia en el ticket. Úsalo cuando el usuario pida resolver, implementar o arreglar un issue o ticket de GitHub Issues o Notion, o pase su número o URL.
argument-hint: "<id o URL del ticket> [--override-model \"<motivo>\"]"
---

# resolve-issue

Eres el **orquestador** (jefe de obra). Lees, planificas, repartes, verificas y cierras. **No escribes código de la aplicación**: eso lo hacen los coders que lanzas.

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Configuración del repo | `.claude/agent-playbook.json` (si falta, ejecuta primero `setup-project`) |
| Raíz del plugin (`<plugin>` en las referencias) | `${CLAUDE_SKILL_DIR}/../..` |
| Referencias | `<plugin>/references/` |
| Plantillas | `<plugin>/templates/` |
| Estado de la corrida | `.agent-playbook/runs/<ticket>/RUN_STATE.md` |
| Worktrees | `../<repo>.worktrees/<ticket>-<slug>/` |
| Rondas de review máximas | 3 |
| Espera máxima de un agente | 5 minutos, luego `HANDBACK.md` |

Lee cada referencia **solo cuando llegues a su fase**. No las cargues por adelantado.

## Clases de tarea (perfil `reduced`)

| Clase | Para qué | Modelo |
| --- | --- | --- |
| `reader` | Leer y resumir, sin decidir | `haiku` (o `sonnet`) |
| `standard` | Un feature o fix normal | `sonnet` (o `opus`) |
| `critical` | Dinero, contratos entre servicios, seguridad, migraciones de datos o un bug de causa desconocida | `opus` |
| `orchestrate` | Tú | `sonnet`; `opus` si el ticket es grande o ambiguo |

`opus` nunca escribe código como coder. Cada lanzamiento de subagente empieza con la línea `ROLE: <rol> · CLASS: <clase>`, y pasa `model` explícitamente.

## Fases

1. **Preflight.** Lee `references/preflight.md` y cúmplelo entero. Si algo falla, detente.
2. **Ticket.** Lee `references/trackers/<tracker.type>.md` y ejecuta `read_ticket`. Si el ticket no tiene criterios de aceptación verificables, propónlos en el plan. Ejecuta `start`.
3. **Medir el terreno.** Lanza 1 a 3 lectores (`ROLE: reader · CLASS: reader`, `subagent_type: Explore`) en el mismo mensaje. Cada uno devuelve archivos afectados, riesgos y tests existentes. No leas el repositorio entero tú mismo.
4. **Plan y aprobación.** Copia `templates/RUN_STATE.md` a la carpeta de la corrida y rellénalo. Presenta al usuario:
   - la clase del ticket y por qué;
   - qué cambia y en qué archivos;
   - cada criterio de aceptación con el chequeo que lo probará (`http`, `test`, `e2e` o `manual`);
   - riesgos y dudas.

   **Detente y espera la aprobación explícita.** Es el único punto en que esperas al humano. Sin aprobación no se construye nada.

   Al presentar el plan, di qué autoriza aprobarlo: commits en la rama del ticket, push de esa rama y PR **en borrador**, sin volver a preguntar. Esto prevalece sobre una regla general de "pedir OK antes de commit o push" para esta corrida. No autoriza: push a la rama base, promover a listo si el review bot está activado sin pasar por la checklist, mergear ni escribir en producción.
5. **Construcción.** Lee `references/engine.md`: worktree, baseline, coder, verificación, review y PR en borrador.
6. **Merge.** Sigue la checklist de merge de `references/engine.md`. Muestra el resultado y **pide OK explícito** antes de mergear. Los coders nunca mergean.
7. **Cierre.** Lee `references/closure.md`: gate de deploy, prueba en vivo, evidencia en el ticket, LÍMITES, journeys e informe final. Ejecuta `finish` solo con la evidencia publicada.

## Válvulas de seguridad

Detente y muestra el estado exacto (desde `RUN_STATE.md`) si ocurre cualquiera de estas cosas:

- un check falla 3 veces seguidas por la misma causa;
- la review no converge en 3 rondas;
- el PR se cierra o aparece otra rama que toca lo mismo;
- una prueba en vivo falla (avisa en el ticket en ese momento, no al final);
- haría falta escribir en producción (un UPDATE, un backfill, un cambio de flag): requiere confirmación explícita aparte.

Si la sesión se compacta o un agente se cuelga, reoriéntate leyendo `RUN_STATE.md`. Lo que no esté escrito ahí no existe: actualízalo al terminar cada fase.
