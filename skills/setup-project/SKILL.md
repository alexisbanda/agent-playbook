---
name: setup-project
description: Configura el agent-playbook en el repositorio actual. Crea .agent-playbook.json (o .claude/agent-playbook.json) con gestor de tickets, perfil, modo de hooks, review bot y entorno, prepara las etiquetas del tracker y excluye del control de versiones la carpeta de estado de las corridas. Úsalo la primera vez que el playbook se usa en un repo, o para cambiar su configuración.
---

# setup-project

Deja un repositorio listo para trabajar con el playbook. No toca código de la aplicación.

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Archivo de configuración | `.agent-playbook.json` (neutral multi-runtime) o `.claude/agent-playbook.json` |
| Esquema | `${CLAUDE_SKILL_DIR}/../../config/agent-playbook.schema.json` |
| Plantilla | `${CLAUDE_SKILL_DIR}/../../config/agent-playbook.example.json` |
| Carpeta de estado (no versionada) | `.agent-playbook/` |

## Pasos

1. **Comprobar el repositorio.** Debe ser un repo git con remoto `origin` en GitHub y `gh auth status` en verde. Si `gh` falla por un `GITHUB_TOKEN` del entorno, aplica la solución de "Problemas conocidos" en `<plugin>/references/preflight.md`. Si no, detente y explica qué falta.
2. **Leer la configuración actual.** Si `.agent-playbook.json` o `.claude/agent-playbook.json` existe, muéstrala y pregunta qué cambiar. Si no, parte de la plantilla.
3. **Preguntar solo lo que no se puede deducir**, en una sola tanda:
   - Gestor de tickets: `github`, `notion` o `jira`. `linear` está reservado: si lo piden, explica que aún no hay adaptador (ver `docs/TRACKERS.md` del plugin) y ofrece `github` mientras tanto.
   - Si es `notion`: la URL de la base de datos de tickets y los nombres de la propiedad de estado y sus valores.
   - Si es `jira`: la clave del proyecto (`project_key`, por ejemplo `PROJ`), el `site_url` o `cloud_id` de Atlassian y los nombres de estado (`in_progress`, `done`).
   - Perfil: `reduced` (por defecto) o `full`.
   - Review bot (Claude Code Action): activado o no. Por defecto, desactivado.
   - Modo de los hooks: `warn` (por defecto: el gate de modelos avisa y el de seguridad pide confirmación), `block` u `off`. Ver `docs/HOOKS.md` del plugin.
   - Patrones de escritura en producción (`hooks.production_patterns`), si el proyecto tiene comandos que tocan producción (por ejemplo `--env=production`). Puede quedar vacío.
   - Entorno: URL de dev y comando de verificación de deploy, si existen. En un proyecto nuevo pueden quedar vacíos.
   - Journeys de regresión: 2 o 3 recorridos de usuario que protegen el producto, cada uno con un comando que sale con 0 si pasa (un test e2e, un script de `curl`, un comando del proyecto). Propón candidatos a partir de lo que veas en el repo. Pueden quedar vacíos.
4. **Deducir el resto.** `tracker.github.repo` sale de `origin`.
5. **Comando de tests: deducir, ejecutar y solo entonces guardar.** Lee `<plugin>/references/test-runtimes.md` (con `<plugin>` = `${CLAUDE_SKILL_DIR}/../..`). Detecta dónde corren los tests (local, Laravel Sail, Docker Compose), propone `environment.test_command` y `environment.worktree_test_command` según esa referencia, y **ejecuta `test_command`** en el clon principal.
   - Si termina y el resultado tiene sentido (los tests corren, aunque alguno falle por motivos del código), guárdalo y anota el resumen (pasan/fallan) para el usuario.
   - Si falla por el entorno (driver o base de datos no disponible, contenedor apagado, dependencia sin instalar), **no lo guardes**: explica qué falta (por ejemplo, `./vendor/bin/sail up -d`) y pregunta si arrancarlo o dejar el campo vacío.
   - Un comando que no se pudo ejecutar se guarda solo si el usuario lo pide, y se dice en el resumen.
   - **Repo sin código** (sin `package.json`, `composer.json`, `pyproject.toml` ni equivalente; típico antes del ticket 0): no hay nada que ejecutar. Si `docs/product/TECH.md` ya fija el stack, propone el comando que el ticket 0 va a crear (por ejemplo `npm test`), guárdalo solo con OK del usuario y di en el resumen que no se pudo ejecutar; el baseline de la primera corrida saldrá sin tests y lo anota. Si el stack no está decidido, déjalo vacío.
   - **Versión del runtime:** comprueba la que pide el proyecto contra la instalada (sección «Versión del runtime» de `test-runtimes.md`). Si no coincide, dilo; no instales nada aquí.
6. **Escribir la configuración** en `.claude/agent-playbook.json` (o `.agent-playbook.json` si el proyecto prefiere la ruta neutral) y validarla contra el esquema:
   ```bash
   python3 -c "import json,jsonschema,sys; jsonschema.validate(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))" .claude/agent-playbook.json "${CLAUDE_SKILL_DIR}/../../config/agent-playbook.schema.json"
   ```
   Si `jsonschema` no está instalado, revisa a mano los campos obligatorios (`version`, `profile`, `tracker.type`) y dilo en el resumen.
7. **Excluir el estado de las corridas y generar el mapa de arquitectura.** Añade `.agent-playbook/` al `.gitignore` del repo si no está, y ejecuta `python3 <plugin>/scripts/repo_map.py` para dejar generado `.agent-playbook/repo-map.md`.
8. **Preparar el tracker.**
   - `github`: crea la etiqueta de "en curso" si no existe (`gh label create <in_progress_label> --color FBCA04 --force`).
   - `notion`: comprueba con el conector de Notion que la base de datos existe y tiene la propiedad de estado. Si el conector no está autorizado, detente y pide al usuario que lo autorice.
   - `jira`: comprueba con el conector de Atlassian (`getVisibleAtlassianResources` / `searchJiraIssuesUsingJql`) que el `project_key` existe y es accesible. Si no está autorizado, detente y pide al usuario que lo autorice.
9. **Review bot** (detalle en `<plugin>/docs/REVIEW_BOT.md`).
   - **Activado:** copia `<plugin>/templates/workflows/claude-review.yml` a `.github/workflows/claude-review.yml` (si ya existe y difiere, muestra el diff y pregunta). Comprueba si existe el secreto con `gh secret list` (solo lista nombres). Si falta `ANTHROPIC_API_KEY`, pide al usuario que lo cree él (`gh secret set ANTHROPIC_API_KEY`). Nunca pidas, leas ni escribas el valor del secreto.
   - **Desactivado** y el workflow existe: propón borrarlo para desmontar el bot.
   - El workflow es un archivo del repo: entra en el commit del paso siguiente, y solo corre una vez esté en la rama base.
10. **Permiso de merge.** Sin una regla de permisos para `gh pr merge`, el modo automático de Claude Code deniega el merge aunque el usuario lo haya aprobado, y el usuario acaba mergeando a mano cada PR (una parada más por ticket). Propón añadir a `permissions.allow` de `.claude/settings.local.json` (personal y no versionado; si lo creas, comprueba que está en `.gitignore`):
    - `Bash(gh pr merge * --match-head-commit *)`;
    - y, si la corrida necesita el prefijo de "Problemas conocidos", también `Bash(env -u GITHUB_TOKEN -u GH_TOKEN gh pr merge * --match-head-commit *)`.

    Explica qué sigue protegiendo el merge: el OK explícito del usuario en el chat, `merge_gate.py` y el gate de seguridad, que bloquea el merge sin `--match-head-commit` o desde un subagente. Añádela **solo con su OK**. Si el usuario prefiere ponerla en `~/.claude/settings.json` para todos sus repos, también vale.
11. **Resumen y commit.** Muestra la configuración final, el resultado del comando de tests, si quedó la regla de merge, y los archivos tocados (`.claude/agent-playbook.json` o `.agent-playbook.json`, `.gitignore` y, si aplica, el workflow del review bot). Propón versionarlos en un commit propio (`chore: configurar agent-playbook`) y hazlo **solo con el OK del usuario**. Si prefiere no hacerlo, avisa de que el preflight de `resolve-issue` los verá como cambios pendientes del setup y no bloqueará por ellos.
