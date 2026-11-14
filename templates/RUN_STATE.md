# Corrida <ticket>

> Mapa de la corrida. Si la sesión se compacta o un agente se cuelga, se retoma desde aquí. Actualízalo al terminar cada fase.

| Campo | Valor |
| --- | --- |
| Ticket | <id> · <título> · <url> |
| Tracker | github / notion |
| Clase | reader / standard / critical |
| Carril | Fast-Track / estándar / crítico |
| Modelo del orquestador | <recomendado> · <usado> |
| Perfil | reduced / full |
| Fase actual | preflight / ticket / terreno / plan / construcción / merge / cierre / cerrada |
| Inicio | <fecha y hora> |

## Preflight

| Control | Resultado |
| --- | --- |
| Modelo de la sesión | |
| Versión del playbook | |
| Configuración | |
| Herramientas y permisos | |
| Clon principal | |

## Overrides

<!-- Motivo de cada OVERRIDE o --override-model. Vacío si no hubo. -->

## Plan aprobado

- Aprobado por el usuario: <fecha y hora>
- Cambios:
- Chequeos de aceptación (el coder los ejecuta antes del PR; el cierre los repite contra el entorno):

| # | Criterio | Tipo (http / test / e2e / cli / manual) | Comando en el worktree | Entrada | Esperado | En cierre |
| --- | --- | --- | --- | --- | --- | --- |

## Agentes

| Rol | Clase | Modelo | Worktree | Rama | Estado |
| --- | --- | --- | --- | --- | --- |

## PRs

| Repo | PR | HEAD revisado | promoted_at | Review | Checks | Mergeado |
| --- | --- | --- | --- | --- | --- | --- |

## Segundo reviewer

<!-- Solo si second_reviewer.enabled (en standard es consultivo; en critical con internal_review: true es el reviewer interno obligatorio). Pega la fila que imprime second_review.py y completa aceptados y descartados: close_run.py lee esta tabla. Sin revisión: anótalo también en LÍMITES. -->

| HEAD | Veredicto | Hallazgos | Aceptados | Descartados (motivo) |
| --- | --- | --- | --- | --- |

## Fallas preexistentes

<!-- Del baseline. Dónde se reportaron (comentario o ticket nuevo). -->

## Punto de retoma

<!-- Qué es lo siguiente que hay que hacer, exactamente. -->
