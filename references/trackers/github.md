# Adaptador: GitHub Issues

Implementa las operaciones de `docs/TRACKERS.md` con `gh`. `<repo>` es `tracker.github.repo` o, si falta, el remoto `origin`. `<label>` es `tracker.github.in_progress_label` (por defecto `in-progress`).

El cuerpo de los comentarios siempre va por archivo (`--body-file`), nunca en línea: así no se rompe con comillas y no queda en el historial del shell.

| Operación | Cómo |
| --- | --- |
| `read_ticket(id)` | `gh issue view <id> -R <repo> --json number,title,body,labels,state,assignees,url,comments` |
| `start(id)` | `gh issue edit <id> -R <repo> --add-assignee @me --add-label <label>` |
| `comment(id, md)` | Escribe el Markdown en `.agent-playbook/runs/<id>/comment-<n>.md` y ejecuta `gh issue comment <id> -R <repo> --body-file <archivo>` |
| `link_pr(id, url)` | El cuerpo del PR incluye `Closes #<id>`. Si el PR está en otro repo, usa `Closes <repo>#<id>` |
| `finish(id)` | `gh issue edit <id> -R <repo> --remove-label <label>`. El issue se cierra solo al mergear el PR con `Closes`; si no se cerró, `gh issue close <id> -R <repo> --reason completed` |
| `create_ticket(fields)` | Escribe el cuerpo en un archivo y ejecuta `gh issue create -R <repo> --title "<título>" --body-file <archivo> --label <etiquetas>` |

## Criterios de aceptación

Búscalos en el cuerpo del issue bajo un encabezado `Criterios de aceptación` o `Acceptance criteria`, o como lista de tareas (`- [ ]`). Si no hay, propónlos en el plan y, una vez aprobados, añádelos al issue con `comment`.

## Identificador

El `id` es el número del issue. Si el usuario pasa una URL (`https://github.com/<owner>/<repo>/issues/<n>`), extrae `<owner>/<repo>` y `<n>` de ella.

## Tickets con el contrato de Ticket Studio

Un issue escrito con Ticket Studio (o a mano siguiendo su contrato) tiene dos caras. No hace falta que el plugin esté instalado para leerlas.

| Parte | Dónde está | Cómo se usa |
| --- | --- | --- |
| Historia | `## Historia` (problema y resultado esperado, o pasos, comportamiento esperado y actual, entorno) | Contexto del plan, en palabras del stakeholder |
| Criterios | `### Criterios de aceptación`, líneas `- [ ] [http\|test\|e2e\|manual] …` | Tal cual, como tabla criterio → chequeo del plan y como filas de la evidencia |
| Fuera de alcance | `### Fuera de alcance` | Límite del plan: lo que no se toca |
| Preguntas abiertas | `### Preguntas abiertas`, `- [ ]` sin resolver | Se llevan al plan para que las decida el usuario antes de construir |
| Tipo, riesgo, tamaño, estado | Etiquetas `type:*`, `risk:*`, `size:*`, `needs-refinement` / `ready` | `risk:dinero`, `risk:seguridad`, `risk:contrato` o `risk:datos` → clase `critical` |
| Padre e hijos | `Parte de #N` al principio del cuerpo; sub-issues nativos | Una épica no se resuelve: se resuelven sus sub-issues. Lista: `gh api repos/<repo>/issues/<n>/sub_issues --jq '.[].number'` |

Con `tickets.contract: true` en la configuración, `scripts/ticket_check.py` comprueba el mínimo del contrato y la etiqueta de listo, y guarda el resultado para la métrica `ticket_quality`.
