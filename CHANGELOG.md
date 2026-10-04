# Changelog

## 0.2.0

- Skill `resolve-issue`: orquestador con preflight, lectores, plan con aprobación, construcción en worktree, review, merge con checklist y cierre con evidencia.
- Referencias compartidas: `preflight`, `engine` (perfil reducido), `closure` y adaptadores de tracker para GitHub Issues y Notion (este último sin probar contra una base real).
- Plantillas: `RUN_STATE`, `HANDBACK`, `CODER_BRIEF`, `REVIEW_BRIEF`, `PR_BODY`, `EVIDENCE`.
- `setup-project` resuelve rutas con `${CLAUDE_SKILL_DIR}`.

## 0.1.0

- Esqueleto del plugin y marketplace privado en el mismo repositorio.
- Configuración por repositorio (`.claude/agent-playbook.json`) con esquema JSON: perfil, gestor de tickets, modo de hooks, review bot, entorno y journeys.
- Skill `setup-project`.
- Documentación de escalado y de gestores de tickets.
- CI: validación estricta de manifiestos y skills, validación del esquema y control de bump de versión.
