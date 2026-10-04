# Changelog

## 0.2.1

Correcciones de la primera corrida real (pokemon-visiotech#1):

- `setup-project` detecta el entorno de tests (local, Laravel Sail, Docker Compose), **ejecuta** el comando antes de guardarlo y propone `worktree_test_command`. Nueva referencia `test-runtimes.md`.
- Nuevo campo `environment.worktree_test_command` con `{worktree}`: los tests de un worktree ya no prueban por error el clon principal cuando el contenedor solo monta este. El motor se detiene si los tests corren en contenedor y el campo falta.
- `setup-project` propone commitear la configuración (con OK); el preflight ya no trata esos archivos como clon sucio.
- El preflight detecta commits locales sin push en la rama base y avisa de que no estarán en el PR.
- Problema conocido documentado: `GITHUB_TOKEN` del entorno que pisa la sesión de `gh`.
- Aprobar el plan autoriza explícitamente los commits, el push de la rama del ticket y el PR en borrador de esa corrida, también cuando hay una regla general de pedir OK antes de commit o push. El merge sigue necesitando OK.

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
