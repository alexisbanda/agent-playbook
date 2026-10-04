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
