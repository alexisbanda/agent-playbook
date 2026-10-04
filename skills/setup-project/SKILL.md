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

1. **Comprobar el repositorio.** Debe ser un repo git con remoto `origin` en GitHub y `gh auth status` en verde. Si no, detente y explica qué falta.
2. **Leer la configuración actual.** Si `.claude/agent-playbook.json` existe, muéstrala y pregunta qué cambiar. Si no, parte de la plantilla.
3. **Preguntar solo lo que no se puede deducir**, en una sola tanda:
   - Gestor de tickets: `github` o `notion`. `jira` y `linear` están reservados: si los piden, explica que aún no hay adaptador (ver `docs/TRACKERS.md` del plugin) y ofrece `github` mientras tanto.
   - Si es `notion`: la URL de la base de datos de tickets y los nombres de la propiedad de estado y sus valores.
   - Perfil: `reduced` (por defecto) o `full`.
   - Review bot (Claude Code Action): activado o no. Por defecto, desactivado.
   - Entorno: URL de dev, comando de tests y comando de verificación de deploy, si existen. En un proyecto nuevo pueden quedar vacíos.
4. **Deducir el resto.** `tracker.github.repo` sale de `origin`. `environment.test_command` se propone a partir de los manifiestos del proyecto (`package.json`, `composer.json`, `pyproject.toml`, `Makefile`…), y se confirma con el usuario.
5. **Escribir la configuración** en `.claude/agent-playbook.json` y validarla contra el esquema:
   ```bash
   python3 -c "import json,jsonschema,sys; jsonschema.validate(json.load(open('.claude/agent-playbook.json')), json.load(open(sys.argv[1])))" "${CLAUDE_SKILL_DIR}/../../config/agent-playbook.schema.json"
   ```
   Si `jsonschema` no está instalado, revisa a mano los campos obligatorios (`version`, `profile`, `tracker.type`) y dilo en el resumen.
6. **Excluir el estado de las corridas.** Añade `.agent-playbook/` al `.gitignore` del repo si no está.
7. **Preparar el tracker.**
   - `github`: crea la etiqueta de "en curso" si no existe (`gh label create <in_progress_label> --color FBCA04 --force`).
   - `notion`: comprueba con el conector de Notion que la base de datos existe y tiene la propiedad de estado. Si el conector no está autorizado, detente y pide al usuario que lo autorice.
8. **Review bot.** Si está activado, indica que el workflow se instala con el skill del motor (fase 4 del roadmap) y que el repo necesita el secreto `ANTHROPIC_API_KEY`, que configura el usuario. Nunca pidas ni escribas el valor del secreto.
9. **Resumen.** Muestra la configuración final y los archivos tocados. No hagas commit: deja que el usuario decida.
