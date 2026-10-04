# Preflight

Se ejecuta antes de cualquier otra cosa. Cada control falla con un mensaje concreto de qué falta y cómo arreglarlo. No sigas con un control en rojo.

## 1. Modelo de la sesión

Comprueba el modelo con el que corre la sesión (lo indica tu propio contexto de sistema).

| Modelo de la sesión | Resultado |
| --- | --- |
| Familia `sonnet`, `opus` o `fable` | OK |
| Cualquier otro (por ejemplo `haiku`) | **Detente.** Pide al usuario que cambie el modelo de la sesión |

Si el usuario pasó `--override-model "<motivo>"`, continúa y anota el motivo en `RUN_STATE.md` (sección Overrides).

## 2. Versión del playbook

```bash
installed=$(python3 -c "import json;print(json.load(open('<plugin>/.claude-plugin/plugin.json'))['version'])")
latest=$(gh api repos/alexisbanda/agent-playbook/contents/.claude-plugin/plugin.json --jq .content | base64 -d | python3 -c "import json,sys;print(json.load(sys.stdin)['version'])")
echo "installed=$installed latest=$latest"
```

Si `installed` es menor que `latest`, avisa: el usuario debe actualizar el plugin (`/plugin` → Marketplaces → actualizar, y luego `/reload-plugins`). No bloquea, salvo que el usuario quiera actualizar primero. Si la consulta remota falla, dilo y sigue.

## 3. Configuración del repo

- `.claude/agent-playbook.json` existe. Si no, ejecuta el skill `setup-project` y vuelve aquí.
- Es válida contra `<plugin>/config/agent-playbook.schema.json` (con `jsonschema` si está instalado; si no, revisa `version`, `profile` y `tracker.type` a mano).
- `tracker.type` es `github` o `notion`. Para `jira` o `linear`, detente: no hay adaptador todavía.

## 4. Herramientas y permisos

- `gh auth status` en verde, con el scope `repo`.
- `git remote get-url origin` apunta a GitHub.
- Si el tracker es `notion`, el conector de Notion responde (por ejemplo, una búsqueda de la base de datos configurada). Si no está autorizado, detente y pide al usuario que lo autorice en los conectores de claude.ai.

## 5. Estado del clon principal

- `git status --porcelain` vacío en el clon principal. Si hay cambios, pregunta: no los muevas ni los descartes por tu cuenta.
- `git fetch origin` sin errores.

## Resultado

Escribe en `RUN_STATE.md` (sección Preflight) una línea por control con OK, AVISO o FALLO.
