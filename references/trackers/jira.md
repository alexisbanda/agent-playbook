<!-- Copyright (c) 2026 Alexis Banda. Todos los derechos reservados. Software propietario: uso sujeto a LICENSE, prohibida su redistribución. -->

# Adaptador: Jira (modo Zero-Admin)

Implementa las operaciones de `docs/TRACKERS.md` con el conector MCP de Atlassian (o `acli` / API REST) sobre el proyecto `tracker.jira.project_key`.

## Modo Zero-Admin (sin Custom Fields)

Por defecto (`tracker.jira.use_labels_for_metadata: true`), el adaptador usa las etiquetas nativas de Jira (`labels`) para leer el contrato de Ticket Studio (`type:*`, `risk:*`, `size:*`, `ready`, `needs-refinement`, `needs-breakdown`), sin exigir permisos de administrador de Jira ni campos personalizados (`customfield_*`). También reconoce el `issuetype` nativo (`Bug` → `type:bug`, `Task` → `type:task`, `Epic` → `type:epic`, `Story` → `type:feature`) y el estado nativo (`Ready for Dev` / `Ready` → `ready`) cuando un ticket fue escrito a mano en Jira.

## Configuración

| Clave | Por defecto |
| --- | --- |
| `tracker.jira.project_key` | *(obligatorio, p. ej. `PROJ`)* |
| `tracker.jira.site_url` | URL base del sitio (`https://miempresa.atlassian.net`) |
| `tracker.jira.cloud_id` | Cloud ID del sitio; si falta, el preflight lo resuelve con `getAccessibleAtlassianResources` y lo anota en `RUN_STATE.md` |
| `tracker.jira.in_progress_status` | `In Progress` |
| `tracker.jira.done_status` | `Done` |
| `tracker.jira.use_labels_for_metadata` | `true` |

## Operaciones

| Operación | Cómo |
| --- | --- |
| `read_ticket(id)` | Lee el issue por su clave (`PROJ-12`) con el conector de Jira (`getJiraIssue`). Toma `summary` (título), `description` (las dos caras del contrato), `labels`, `issuetype`, `status`, `parent` y los comentarios. Si `tickets.contract: true`, guarda el JSON del issue en `.agent-playbook/runs/<id>/jira_issue.json` y pásalo a `ticket_check.py <id> --input .agent-playbook/runs/<id>/jira_issue.json --save .agent-playbook/runs/<id>/ticket_check.json` |
| `start(id)` | Transiciona el issue a `<in_progress_status>` (`transitionJiraIssue`) y asígnalo al usuario actual si procede |
| `comment(id, md)` | Añade un comentario en el issue (`addCommentToJiraIssue`) con el Markdown del informe o aviso |
| `link_pr(id, url)` | Publica un comentario corto con el enlace al PR y añade la clave de Jira (`PROJ-12`) en el título/cuerpo del PR para que la integración nativa de Jira-GitHub lo enlace automáticamente |
| `finish(id)` | Transiciona el issue a `<done_status>` (`transitionJiraIssue`) solo después de publicar la evidencia con `comment` |
| `create_ticket(fields)` | Crea un issue en `tracker.jira.project_key` (`createJiraIssue`) con `summary`, `description`, `issuetype` y `labels` |

## Criterios de aceptación e Identificador

- **Criterios de aceptación:** búscalos en `description` bajo `### Criterios de aceptación` / `## Acceptance criteria` con su tipo de prueba (`[http]`, `[test]`, `[e2e]`, `[manual]`). Si no hay, propónlos en el plan.
- **Identificador:** usa la clave de Jira en minúsculas para ramas y worktrees (p. ej., `PROJ-12` → `feat/proj-12-record-combates`) y la clave tal cual (`PROJ-12`) para `.agent-playbook/runs/PROJ-12/`.
