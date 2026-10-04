# Adaptador: Notion

Implementa las operaciones de `docs/TRACKERS.md` con el conector de Notion. Los tickets son páginas de la base de datos `tracker.notion.database_url`. Nombres de configuración:

| Clave | Por defecto |
| --- | --- |
| `tracker.notion.status_property` | `Status` |
| `tracker.notion.in_progress_value` | `In progress` |
| `tracker.notion.done_value` | `Done` |

Si el conector no está autorizado, detente y pide al usuario que lo autorice en los conectores de claude.ai. No uses la API de Notion con un token propio.

| Operación | Cómo |
| --- | --- |
| `read_ticket(id)` | `notion-fetch` con la URL o el id de la página. Toma título, propiedades, contenido y comentarios (`notion-get-comments`) |
| `start(id)` | `notion-update-page`: pon `<status_property>` en `<in_progress_value>` y, si la base tiene una propiedad de persona asignada, asígnate con el usuario actual (`notion-get-users`) |
| `comment(id, md)` | `notion-create-comment` sobre la página. Si el comentario es largo (evidencia, informe final), añádelo además como bloque al final de la página con `notion-update-page`, bajo un encabezado con la fecha |
| `link_pr(id, url)` | Si la base tiene una propiedad de URL para el PR, rellénala; si no, publícalo con `comment`. El cuerpo del PR enlaza la página de Notion |
| `finish(id)` | `notion-update-page`: pon `<status_property>` en `<done_value>` |
| `create_ticket(fields)` | `notion-create-pages` en la base de datos, con título, estado inicial y el cuerpo como contenido |

## Criterios de aceptación

Búscalos en una propiedad `Acceptance criteria` / `Criterios de aceptación` o, si no existe, en el contenido de la página bajo ese encabezado o como lista de tareas. Si no hay, propónlos en el plan y, una vez aprobados, añádelos a la página.

## Identificador

El `id` es la URL de la página o su id. En los nombres de carpetas y ramas usa los 8 primeros caracteres del id, por ejemplo `notion-1a2b3c4d`.

## Estado

Adaptador escrito pero **no probado contra una base real** todavía. La primera corrida con Notion debe revisar cada operación y corregir este archivo si algo difiere.
