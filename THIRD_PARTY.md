# Servicios y herramientas de terceros

agent-playbook no incluye ni redistribuye código de terceros. Para funcionar se apoya en herramientas y servicios externos que el usuario instala, contrata y paga por su cuenta. El uso de cada uno se rige por sus propios términos y políticas, que el usuario acepta directamente con cada proveedor. Ver la cláusula 7 de [LICENSE](LICENSE).

| Servicio o herramienta | Para qué lo usa agent-playbook | Obligatorio | Qué datos salen hacia el proveedor |
| --- | --- | --- | --- |
| Claude Code (Anthropic) | Runtime del plugin: skills, agentes, hooks y modelos Claude | Sí, o `agy` como runtime | Lo que Claude Code envía normalmente: prompts, código leído y salidas de herramientas |
| Google Antigravity `agy` y modelos Gemini (Google) | Runtime alternativo, segundo reviewer (`second_reviewer`) y lectores de código (`gemini_readers`) | No, desactivado por defecto | Diff del ticket, ticket, cuerpo del PR y archivos que los lectores lean del repositorio |
| GitHub y CLI `gh` | Issues, ramas, pull requests, review bot (Claude Code Action) | Sí con `tracker.type: "github"`; para PRs siempre | Commits, PRs, comentarios y evidencia del cierre |
| Notion | Tracker de tickets | Solo con `tracker.type: "notion"` | Comentarios y cambios de estado en los tickets |
| Jira (Atlassian) | Tracker de tickets | Solo con `tracker.type: "jira"` | Comentarios y cambios de estado en los tickets |
| Python 3, Git, Node.js | Ejecutar scripts, hooks, worktrees y la CI | Sí | Ninguno |

## Responsabilidades del usuario

- Tener cuenta y licencia vigentes en cada servicio que active.
- Pagar el consumo de API, tokens y planes de cada proveedor. Las cifras de coste de [docs/METRICS.md](docs/METRICS.md) son estimaciones a partir de `metrics/prices.json` y no son una factura ni un compromiso de precio.
- Comprobar que enviar su código a esos proveedores es compatible con sus obligaciones de confidencialidad y con las políticas de su organización, en especial al activar las funciones de Gemini, que envían código a Google.
- Cumplir las políticas de uso aceptable de cada proveedor.

## Cambios de los proveedores

Los proveedores pueden cambiar sus modelos, precios, APIs o términos sin aviso. El titular de agent-playbook no controla esos cambios ni responde por ellos. Puede adaptar el plugin en versiones posteriores, pero no está obligado a hacerlo.
