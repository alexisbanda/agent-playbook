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

1. Abre Claude Code en el repo y ejecuta `/agent-playbook:setup-project`. Crea `.claude/agent-playbook.json` (también se lee `.agent-playbook.json` en la raíz).
2. Versiona ese archivo para que todo el equipo use la misma configuración.
3. Para resolver un ticket: `/agent-playbook:resolve-issue <número o URL>`. También se activa solo si pides resolver o implementar un issue. Al presentar el plan recomienda el modelo de la sesión según el carril: `sonnet` para tickets pequeños sin riesgo y `opus` para los críticos (se cambia con `/model`).
4. Cada semana, o cada 10 corridas: `/agent-playbook:tuning-wave` para revisar las métricas y mejorar los manuales. Ver [docs/METRICS.md](docs/METRICS.md).

| Opción | Valores | Por defecto |
| --- | --- | --- |
| `profile` | `reduced`, `full` | `reduced` |
| `tracker.type` | `github`, `notion`, `jira` (`linear` reservado) | — |
| `tickets.contract` | `true`, `false`: comprobar el contrato de ticket de [ticket-studio](https://github.com/alexisbanda/ticket-studio) y medir `ticket_quality` | `false` |
| `tickets.ready_label` | etiqueta con la que el tech lead marca un ticket como listo | `ready` |
| `hooks.mode` | `off`, `warn`, `block` | `warn` |
| `hooks.production_patterns` | expresiones de comandos que tocan producción | `[]` |
| `hooks.coder_ctx_handback_k` | miles de tokens de contexto a partir de los cuales el coder deja `HANDBACK.md` y sigue uno nuevo | `150` |
| `review_bot.enabled` | `true`, `false` (ver [docs/REVIEW_BOT.md](docs/REVIEW_BOT.md)) | `false` |
| `environment` | `dev_url`, `test_command`, `worktree_test_command`, `deploy_check` | vacío |
| `journeys` | lista de `{name, command}` | `[]` |

El esquema completo está en [config/agent-playbook.schema.json](config/agent-playbook.schema.json).

## Estructura

```
.claude-plugin/   manifiesto del plugin y del marketplace (Claude Code)
plugin.json       manifiesto en raíz compatible con Google Antigravity (agy)
skills/           procedimientos que se invocan (setup-project, resolve-issue, resolve-epic, tuning-wave)
references/       capítulos compartidos que los skills leen por fases: preflight, motor, cierre, adaptadores de trackers (github, notion, jira)
agents/           coder.md: subagente coder del plugin (solo Bash, Read, Edit, Write, Grep y Glob; esfuerzo medium, high en critical)
templates/        RUN_STATE, HANDBACK, briefs de coder y reviewer, cuerpo de PR, evidencia, workflow del review bot
hooks/            model_gate.py y safety_gate.py (gates de modelos y de seguridad), context_guard.py (vigilante de contexto del coder) y telemetry.py (telemetría dual-runtime); ver docs/HOOKS.md
routing/          tabla de ruteo de modelos (routing.json con runtime_aliases claude/agy), su esquema y su explicación
metrics/          precios para el coste estimado y umbrales (tripwires) de la tuning wave
config/           esquema y ejemplo de la configuración por repo (.agent-playbook.json o .claude/agent-playbook.json)
docs/             escalado, gestores de tickets, hooks, review bot, métricas
scripts/          utilidades de CI y de las corridas (preflight.py: controles iniciales en un paso; repo_map.py: mapa de arquitectura; route.py: modelo de cada subagente; ticket_check.py: contrato de ticket opcional; merge_gate.py: condiciones de merge; run_journeys.py: regresión; close_run.py y metrics_report.py: métricas y exportación sanitizada)
tests/            tests de los scripts
```

## Roadmap

| Fase | Contenido | Estado |
| --- | --- | --- |
| 0 | Esqueleto, marketplace, configuración por repo, CI | Hecho |
| 1 | Skill `resolve-issue`, adaptadores de GitHub Issues y Notion, motor y cierre reducidos, plantillas | Hecho |
| 1b | Arranque de proyectos nuevos | Sustituida: el ticket 0 de cimientos que crea el `kickoff` de ticket-studio se resuelve con `resolve-issue` |
| 2 | `routing.json` con las tablas reducida y completa, resolvedor y tests | Hecho |
| 3 | Hooks: gate de modelos, gate de seguridad, telemetría y métricas por corrida | Hecho |
| 4 | Motor: gate de merge con vigilante, review bot opcional con Claude Code Action | Hecho |
| 5 | Journeys con evidencia, informe de métricas con coste estimado, tripwires y skill `tuning-wave` | Hecho |
| 6 | Contrato de ticket opcional (ticket-studio), métrica `ticket_quality` | Hecho |
| 1.0 | MVP: GitHub Issues y Notion probados en real; con ticket-studio, del kickoff al PR mergeado con evidencia | Hecho |
| 1.1 | Eficiencia operativa: `preflight.py` en un paso, caché de baseline por SHA base y carril Fast-Track (`size: S` + `risk: ninguno`) | Hecho |
| 1.2 | Adaptador Jira Zero-Admin, soporte Dual-Runtime (`Claude Code` + `Google Antigravity agy`), `repo_map.py`, `resolve-epic` con paralelismo intra-repo por archivos disjuntos y `--export-sanitized` | Hecho |
| 1.3 | Cada ticket en una sesión nueva: control de contexto inicial en el preflight y tripwire `orchestrator_ctx_start_k_max` | Hecho |
| 1.4 | Agente `coder` propio, vigilante de contexto (`context_guard.py`) y métricas del bucle del coder | Hecho |
| 1.5 | Chequeos de aceptación ejecutables antes del PR y modelo del orquestador recomendado por carril | Hecho |
| 1.6 | Permiso de merge en `setup-project`, aviso del trabajo en segundo plano y esperas medidas sin ausencias (`human_stops`) | Hecho |

### Límites conocidos

Todas las corridas reales registradas usan GitHub Issues y el perfil `reduced`. Falta probar en real:

- **Jira:** el adaptador existe desde la 1.2, pero no hay corridas con `tracker.type: "jira"`. Notion se probó en la 1.0.
- **Perfil `full`:** descrito y con su tabla de ruteo, sin corridas.
- **`resolve-epic` y los coders en paralelo:** sin corridas registradas.
- **Google Antigravity `agy`:** los hooks y el ruteo lo contemplan, sin corridas registradas.
- **Entorno desplegado:** las pruebas en vivo se han hecho contra el entorno local (`dev_url` vacío); el gate de deploy no se ha ejercitado.
- **Review bot, criterios `e2e` con navegador y journeys:** sin probar a fondo (un solo repo tiene un journey).
- **Proyecto desde cero:** el ticket 0 de un repo sin código se resolvió una vez (kickoff-demo#2, Next.js); falta repetirlo con otro stack.

## Cómo cambiar el playbook

Cambiar cómo trabajan los agentes es editar Markdown: rama, PR, review y **bump de versión** en `plugin.json`, `.claude-plugin/plugin.json` y `.claude-plugin/marketplace.json`. La CI rechaza un PR sin bump o con las versiones desalineadas. Anota el cambio en [CHANGELOG.md](CHANGELOG.md).
