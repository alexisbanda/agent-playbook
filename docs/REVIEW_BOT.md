<!-- Copyright (c) 2026 Alexis Banda. Todos los derechos reservados. Software propietario: uso sujeto a LICENSE, prohibida su redistribución. -->

# Review bot

Un inspector externo que revisa cada PR desde la CI del repositorio, con [Claude Code Action](https://github.com/anthropics/claude-code-action). Solo revisa: nunca escribe código ni mergea. Es opcional y se monta o desmonta por configuración.

## Montarlo

1. En `.claude/agent-playbook.json`: `"review_bot": { "enabled": true }`.
2. Ejecuta `/agent-playbook:setup-project`: copia [`templates/workflows/claude-review.yml`](../templates/workflows/claude-review.yml) a `.github/workflows/claude-review.yml`.
3. Crea el secreto del repositorio (lo haces tú; el playbook nunca ve su valor):
   ```bash
   gh secret set ANTHROPIC_API_KEY
   ```
4. Commitea el workflow y llévalo a la rama base por PR. Solo corre a partir de ahí.

## Desmontarlo

`"review_bot": { "enabled": false }` y borra `.github/workflows/claude-review.yml` (`setup-project` lo propone). Desde ese momento, el veredicto del gate de merge es la revisión interna.

## Cómo da su veredicto

| Paso | Detalle |
| --- | --- |
| Cuándo corre | Al abrir, actualizar, reabrir o promover un PR que **no** está en borrador. Los borradores no lo disparan, así que abrir el PR temprano no cuesta nada |
| Qué lee | El PR, el ticket que cierra (`Closes #n`) con sus criterios, y el diff |
| Qué publica | Un comentario que empieza por `APPROVE <sha>` o `CHANGES_REQUESTED <sha>` con los problemas que bloquean |
| Veredicto formal | El propio check `claude-review` del job: verde con APPROVE, rojo con CHANGES_REQUESTED |
| Modelo | `claude-sonnet-5`, la clase `review` de [ROUTING.md](../routing/ROUTING.md). Se cambia en `claude_args` del workflow |
| Herramientas | Solo lectura del repo, `gh pr view/diff/comment`, `gh issue view` y escribir su archivo de veredicto |

El veredicto es un check y no una aprobación de GitHub porque, por defecto, un workflow no puede aprobar PRs con su token. Un check además queda **ligado al commit** que revisó.

## Fresco y anclado

`scripts/merge_gate.py` solo acepta el veredicto si:

- **Anclado:** el check `claude-review` es del HEAD actual del PR. Si alguien empuja otro commit, el veredicto anterior deja de valer y el bot vuelve a revisar.
- **Fresco:** terminó después de la última promoción (`promoted_at`).

Las dos trampas de la guía y cómo quedan:

| Trampa | Qué pasa aquí |
| --- | --- |
| Re-ejecutar la review aprueba código viejo con fecha nueva | Re-ejecutar el job vuelve a revisar el commit viejo y su check queda en ese commit, no en el HEAD: el gate no lo acepta. Aun así, para volver a disparar la review se hace un ciclo borrador → listo |
| Empujar a un borrador y promoverlo enseguida salta la review | Si el job quedó `skipped`, el gate espera y pide un ciclo borrador → listo |

## Coste

Cada review es una ejecución de Claude en la CI, facturada a la API key del secreto. Conviene fijar un límite de gasto mensual en la consola de Anthropic antes de activarlo.
