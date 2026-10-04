# Gestores de tickets

Los skills nunca llaman directamente a un gestor de tickets. Usan un conjunto fijo de **operaciones**, y cada gestor las implementa en un adaptador (`references/trackers/<tipo>.md`). El gestor se elige con `tracker.type` en `.claude/agent-playbook.json`.

## Estado

| Tipo | Estado | Herramienta |
| --- | --- | --- |
| `github` | Soportado | `gh` CLI |
| `notion` | Soportado, pendiente de probar contra una base real | Conector de Notion (requiere autorizarlo en claude.ai) |
| `jira` | Reservado | Conector de Atlassian |
| `linear` | Reservado | Conector de Linear |

## Operaciones que debe cubrir un adaptador

| Operación | Qué hace |
| --- | --- |
| `read_ticket(id)` | Devuelve título, descripción, criterios de aceptación, etiquetas y estado |
| `start(id)` | Asigna el ticket al usuario y lo mueve a "en curso" |
| `comment(id, markdown)` | Publica un comentario: avisos de fallo, evidencia, informe final |
| `link_pr(id, url)` | Deja el PR enlazado en el ticket |
| `finish(id)` | Mueve el ticket a "terminado", solo después de la evidencia |
| `create_ticket(fields)` | Crea un ticket nuevo, por ejemplo para una falla preexistente que no se arregla en la corrida |

## Añadir un gestor nuevo

1. Escribir `references/trackers/<tipo>.md` con las seis operaciones, cada una con el comando o la llamada al conector exacta.
2. Añadir el bloque de configuración de `<tipo>` en `config/agent-playbook.schema.json`.
3. Marcarlo como soportado en la tabla de arriba y en `setup-project`.
4. Bump de versión y entrada en `CHANGELOG.md`.

Ningún otro archivo debería cambiar. Si hace falta tocar el resolver, es señal de que la interfaz se quedó corta y conviene ampliarla aquí primero.
