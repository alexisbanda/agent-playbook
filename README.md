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

Activa la auto-actualización del marketplace en `/plugin` → Marketplaces para que cada versión nueva llegue sola.

## Uso en un repositorio

1. Abre Claude Code en el repo y ejecuta `/agent-playbook:setup-project`. Crea `.claude/agent-playbook.json`.
2. Versiona ese archivo para que todo el equipo use la misma configuración.

| Opción | Valores | Por defecto |
| --- | --- | --- |
| `profile` | `reduced`, `full` | `reduced` |
| `tracker.type` | `github`, `notion` (`jira`, `linear` reservados) | — |
| `hooks.mode` | `off`, `warn`, `block` | `warn` |
| `review_bot.enabled` | `true`, `false` | `false` |
| `environment` | `dev_url`, `test_command`, `deploy_check` | vacío |
| `journeys` | lista de `{name, command}` | `[]` |

El esquema completo está en [config/agent-playbook.schema.json](config/agent-playbook.schema.json).

## Estructura

```
.claude-plugin/   manifiesto del plugin y del marketplace
skills/           procedimientos (un directorio por skill, con references/)
config/           esquema y ejemplo de la configuración por repo
docs/             escalado, gestores de tickets
scripts/          utilidades de CI y de las corridas
```

## Roadmap

| Fase | Contenido | Estado |
| --- | --- | --- |
| 0 | Esqueleto, marketplace, configuración por repo, CI | Hecho |
| 1 | Skill `resolve-issue`, adaptadores de GitHub Issues y Notion, plantillas | Pendiente |
| 2 | `routing.json` con las tablas reducida y completa | Pendiente |
| 3 | Hooks: gate de modelos, gate de seguridad, telemetría | Pendiente |
| 4 | Motor: worktrees, baseline, review, merge gate, review bot opcional | Pendiente |
| 5 | Cierre con evidencia, journeys, métricas y tuning wave | Pendiente |

## Cómo cambiar el playbook

Cambiar cómo trabajan los agentes es editar Markdown: rama, PR, review y **bump de versión** en `.claude-plugin/plugin.json` y en `.claude-plugin/marketplace.json`. La CI rechaza un PR sin bump o con las dos versiones desalineadas. Anota el cambio en [CHANGELOG.md](CHANGELOG.md).
