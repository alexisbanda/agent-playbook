# agent-playbook

Plugin de Claude Code para orquestar el desarrollo de software con agentes: manuales versionados, ruteo de modelos por clase de tarea, hooks que hacen cumplir las reglas, un motor de ejecución con worktrees aislados y un cierre con evidencia.

Sirve para proyectos nuevos y para construir features o corregir bugs en proyectos existentes. Arranca en un perfil reducido, pensado para un dev en solitario o un equipo pequeño, y escala al modelo completo cambiando configuración. Ver [docs/SCALING.md](docs/SCALING.md).

## Instalación

El repositorio es a la vez el plugin y su marketplace privado. Hace falta acceso de lectura al repo (con `gh auth login` o una clave SSH).

En Claude Code:

```
/plugin marketplace add alexisbanda/agent-playbook
/plugin install agent-playbook@agent-playbook
```

El mismo marketplace publica [ticket-studio](https://github.com/alexisbanda/ticket-studio), para que el PM escriba tickets que cumplan el contrato que este playbook espera (`/plugin install ticket-studio@agent-playbook`).

Activa la auto-actualización del marketplace en `/plugin` → Marketplaces para que cada versión nueva llegue sola.

## Uso en un repositorio

1. Abre Claude Code en el repo y ejecuta `/agent-playbook:setup-project`. Crea `.claude/agent-playbook.json`.
2. Versiona ese archivo para que todo el equipo use la misma configuración.
3. Para resolver un ticket: `/agent-playbook:resolve-issue <número o URL>`. También se activa solo si pides resolver o implementar un issue.
4. Cada semana, o cada 10 corridas: `/agent-playbook:tuning-wave` para revisar las métricas y mejorar los manuales. Ver [docs/METRICS.md](docs/METRICS.md).

| Opción | Valores | Por defecto |
| --- | --- | --- |
| `profile` | `reduced`, `full` | `reduced` |
| `tracker.type` | `github`, `notion` (`jira`, `linear` reservados) | — |
| `hooks.mode` | `off`, `warn`, `block` | `warn` |
| `hooks.production_patterns` | expresiones de comandos que tocan producción | `[]` |
| `review_bot.enabled` | `true`, `false` (ver [docs/REVIEW_BOT.md](docs/REVIEW_BOT.md)) | `false` |
| `environment` | `dev_url`, `test_command`, `worktree_test_command`, `deploy_check` | vacío |
| `journeys` | lista de `{name, command}` | `[]` |

El esquema completo está en [config/agent-playbook.schema.json](config/agent-playbook.schema.json).

## Estructura

```
.claude-plugin/   manifiesto del plugin y del marketplace
skills/           procedimientos que se invocan (setup-project, resolve-issue, tuning-wave)
references/       capítulos compartidos que los skills leen por fases: preflight, motor, cierre, adaptadores de trackers
templates/        RUN_STATE, HANDBACK, briefs de coder y reviewer, cuerpo de PR, evidencia, workflow del review bot
hooks/            gate de modelos, gate de seguridad y telemetría (ver docs/HOOKS.md)
routing/          tabla de ruteo de modelos (routing.json), su esquema y su explicación
metrics/          precios para el coste estimado y umbrales (tripwires) de la tuning wave
config/           esquema y ejemplo de la configuración por repo
docs/             escalado, gestores de tickets, hooks, review bot, métricas
scripts/          utilidades de CI y de las corridas (route.py: modelo de cada subagente; merge_gate.py: condiciones de merge; run_journeys.py: regresión; close_run.py y metrics_report.py: métricas)
tests/            tests de los scripts
```

## Roadmap

| Fase | Contenido | Estado |
| --- | --- | --- |
| 0 | Esqueleto, marketplace, configuración por repo, CI | Hecho |
| 1 | Skill `resolve-issue`, adaptadores de GitHub Issues y Notion, motor y cierre reducidos, plantillas | Hecho |
| 1b | Skill `bootstrap-project` para arrancar proyectos nuevos | Pendiente |
| 2 | `routing.json` con las tablas reducida y completa, resolvedor y tests | Hecho |
| 3 | Hooks: gate de modelos, gate de seguridad, telemetría y métricas por corrida | Hecho |
| 4 | Motor: gate de merge con vigilante, review bot opcional con Claude Code Action | Hecho |
| 5 | Journeys con evidencia, informe de métricas con coste estimado, tripwires y skill `tuning-wave` | Hecho |

## Cómo cambiar el playbook

Cambiar cómo trabajan los agentes es editar Markdown: rama, PR, review y **bump de versión** en `.claude-plugin/plugin.json` y en `.claude-plugin/marketplace.json`. La CI rechaza un PR sin bump o con las dos versiones desalineadas. Anota el cambio en [CHANGELOG.md](CHANGELOG.md).
