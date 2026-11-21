# Privacidad y datos

## Resumen

agent-playbook **no envía datos a su autor**. No tiene servidores, analítica remota ni telemetría externa. Todo lo que mide se queda en el repositorio del usuario.

## Qué se guarda y dónde

| Dato | Dónde | Quién lo escribe |
| --- | --- | --- |
| Eventos de los hooks (inicio y fin de sesión, lanzamiento de subagentes, PRs abiertos, worktrees) | `<repo>/.agent-playbook/events.jsonl` | `hooks/telemetry.py` |
| Métricas por corrida | `<repo>/.agent-playbook/metrics.jsonl` | `scripts/close_run.py` |
| Estado de cada corrida, evidencia, logs de journeys y de los lectores y reviewers Gemini | `<repo>/.agent-playbook/runs/` y archivos relacionados | skills y scripts |
| Mapa de arquitectura | `<repo>/.agent-playbook/repo-map.md` | `scripts/repo_map.py` |

La telemetría **no guarda el texto de los prompts ni de los comandos**: solo hechos (por ejemplo, la longitud de un prompt o que se abrió un PR) y rutas locales a los transcripts. El directorio `.agent-playbook/` está en `.gitignore`, por lo que no se sube al repositorio salvo que el usuario lo decida.

`scripts/metrics_report.py --export-sanitized` genera una exportación sin datos identificables, por si el usuario decide compartir métricas. Compartirlas es siempre una acción manual del usuario.

## Qué sale hacia terceros

Los datos solo salen hacia los servicios que el propio usuario usa y configura: Anthropic (Claude Code), Google (si activa `agy`, `second_reviewer` o `gemini_readers`), GitHub, Notion o Jira. Ese tratamiento se rige por las políticas de privacidad de cada proveedor. El detalle está en [THIRD_PARTY.md](THIRD_PARTY.md).

## Responsable

El usuario es el responsable de los datos de sus repositorios y de decidir qué funciones activa. Consultas: ver la cláusula 12.7 de [LICENSE](LICENSE).
