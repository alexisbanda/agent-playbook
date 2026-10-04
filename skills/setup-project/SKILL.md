---
name: setup-project
description: Configura el agent-playbook en el repositorio actual. Crea .claude/agent-playbook.json (gestor de tickets, perfil, modo de hooks, review bot, entorno), prepara las etiquetas del tracker y excluye del control de versiones la carpeta de estado de las corridas. Úsalo la primera vez que el playbook se usa en un repo, o para cambiar su configuración.
---

# setup-project

Deja un repositorio listo para trabajar con el playbook. No toca código de la aplicación.

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Archivo de configuración | `.claude/agent-playbook.json` |
| Esquema | `${CLAUDE_SKILL_DIR}/../../config/agent-playbook.schema.json` |
| Plantilla | `${CLAUDE_SKILL_DIR}/../../config/agent-playbook.example.json` |
| Carpeta de estado (no versionada) | `.agent-playbook/` |

## Pasos

1. **Comprobar el repositorio.** Debe ser un repo git con remoto `origin` en GitHub y `gh auth status` en verde. Si `gh` falla por un `GITHUB_TOKEN` del entorno, aplica la solución de "Problemas conocidos" en `<plugin>/references/preflight.md`. Si no, detente y explica qué falta.
2. **Leer la configuración actual.** Si `.claude/agent-playbook.json` existe, muéstrala y pregunta qué cambiar. Si no, parte de la plantilla.
3. **Preguntar solo lo que no se puede deducir**, en una sola tanda:
   - Gestor de tickets: `github` o `notion`. `jira` y `linear` están reservados: si los piden, explica que aún no hay adaptador (ver `docs/TRACKERS.md` del plugin) y ofrece `github` mientras tanto.
   - Si es `notion`: la URL de la base de datos de tickets y los nombres de la propiedad de estado y sus valores.
   - Perfil: `reduced` (por defecto) o `full`.
   - Review bot (Claude Code Action): activado o no. Por defecto, desactivado.
   - Entorno: URL de dev y comando de verificación de deploy, si existen. En un proyecto nuevo pueden quedar vacíos.
4. **Deducir el resto.** `tracker.github.repo` sale de `origin`.
5. **Comando de tests: deducir, ejecutar y solo entonces guardar.** Lee `<plugin>/references/test-runtimes.md` (con `<plugin>` = `${CLAUDE_SKILL_DIR}/../..`). Detecta dónde corren los tests (local, Laravel Sail, Docker Compose), propone `environment.test_command` y `environment.worktree_test_command` según esa referencia, y **ejecuta `test_command`** en el clon principal.
   - Si termina y el resultado tiene sentido (los tests corren, aunque alguno falle por motivos del código), guárdalo y anota el resumen (pasan/fallan) para el usuario.
   - Si falla por el entorno (driver o base de datos no disponible, contenedor apagado, dependencia sin instalar), **no lo guardes**: explica qué falta (por ejemplo, `./vendor/bin/sail up -d`) y pregunta si arrancarlo o dejar el campo vacío.
   - Un comando que no se pudo ejecutar se guarda solo si el usuario lo pide, y se dice en el resumen.
6. **Escribir la configuración** en `.claude/agent-playbook.json` y validarla contra el esquema:
   ```bash
   python3 -c "import json,jsonschema,sys; jsonschema.validate(json.load(open('.claude/agent-playbook.json')), json.load(open(sys.argv[1])))" "${CLAUDE_SKILL_DIR}/../../config/agent-playbook.schema.json"
   ```
   Si `jsonschema` no está instalado, revisa a mano los campos obligatorios (`version`, `profile`, `tracker.type`) y dilo en el resumen.
7. **Excluir el estado de las corridas.** Añade `.agent-playbook/` al `.gitignore` del repo si no está.
8. **Preparar el tracker.**
   - `github`: crea la etiqueta de "en curso" si no existe (`gh label create <in_progress_label> --color FBCA04 --force`).
   - `notion`: comprueba con el conector de Notion que la base de datos existe y tiene la propiedad de estado. Si el conector no está autorizado, detente y pide al usuario que lo autorice.
9. **Review bot.** Si está activado, indica que el workflow se instala con el skill del motor (fase 4 del roadmap) y que el repo necesita el secreto `ANTHROPIC_API_KEY`, que configura el usuario. Nunca pidas ni escribas el valor del secreto.
10. **Resumen y commit.** Muestra la configuración final, el resultado del comando de tests y los archivos tocados (`.claude/agent-playbook.json`, `.gitignore`). Propón versionarlos en un commit propio (`chore: configurar agent-playbook`) y hazlo **solo con el OK del usuario**. Si prefiere no hacerlo, avisa de que el preflight de `resolve-issue` los verá como cambios pendientes del setup y no bloqueará por ellos.
