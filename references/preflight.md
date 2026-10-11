# Preflight

Se ejecuta antes de cualquier otra cosa. Cada control falla con un mensaje concreto de qué falta y cómo arreglarlo. No sigas con un control en rojo.

## 1. Modelo de la sesión

Comprueba el modelo con el que corre la sesión (lo indica tu propio contexto de sistema):

```bash
python3 <plugin>/scripts/route.py --session-model <id del modelo de la sesión>
```

| Resultado | Qué hacer |
| --- | --- |
| `allow` | OK |
| `block` (por ejemplo `haiku`) | **Detente.** Pide al usuario que cambie el modelo de la sesión |
| `missing_pins` no vacío | AVISO, no bloquea: los alias no están fijados a una versión exacta. Indica las variables que faltan (ver `<plugin>/routing/ROUTING.md`) |

En el perfil `full`, la clase `orchestrate` pide `fable`: si la sesión usa otro modelo, avisa.

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

- `gh auth status` en verde, con el scope `repo`. Si falla por un token de entorno, ver [Problemas conocidos](#problemas-conocidos).
- `git remote get-url origin` apunta a GitHub.
- Si el tracker es `notion`, el conector de Notion responde (por ejemplo, una búsqueda de la base de datos configurada). Si no está autorizado, detente y pide al usuario que lo autorice en los conectores de claude.ai.

## 5. Estado del clon principal

- `git fetch origin` sin errores.
- `git status --porcelain` en el clon principal:
  - vacío: OK;
  - solo `.claude/agent-playbook.json` y `.gitignore` (lo que deja `setup-project`): AVISO, sigue, y recuerda al usuario que conviene versionarlos;
  - cualquier otro cambio: pregunta. No los muevas ni los descartes por tu cuenta.
- **Rama base al día con el remoto.** `git log --oneline origin/<base>..<base>` y `git log --oneline <base>..origin/<base>`, con `<base>` la rama por defecto:
  - sin salida: OK;
  - commits locales sin push: AVISO. Enuméralos y explica que el worktree parte de `origin/<base>`, así que **no estarán en el PR**. Pregunta si hacer push antes o seguir sin ellos;
  - el local va por detrás: OK (el worktree parte de `origin`), pero menciónalo.

## 6. Hooks

- Si existe `.agent-playbook/hook-errors.log` con entradas recientes, AVISO: algún hook falló (los hooks no bloquean la sesión cuando fallan, así que una regla podría no estar aplicándose). Muestra la última entrada.
- Si existe `.agent-playbook/active-run` de otro ticket, pregunta: puede ser una corrida que no se cerró.

## Problemas conocidos

| Síntoma | Causa | Qué hacer |
| --- | --- | --- |
| `gh auth status` dice que el token es inválido, o `gh` responde 401, aunque el usuario hizo `gh auth login` | Hay una variable `GITHUB_TOKEN` (o `GH_TOKEN`) exportada en el entorno, que `gh` usa antes que las credenciales guardadas | Comprueba `env -u GITHUB_TOKEN -u GH_TOKEN gh auth status`. Si así está en verde, escribe ese prefijo **literal** delante de cada comando `gh` de la corrida (`env -u GITHUB_TOKEN -u GH_TOKEN gh pr merge …`) y anótalo en `RUN_STATE.md`. No lo guardes en una variable (`GH=...; $GH pr ...`): los hooks reconocen los comandos por su texto. Sugiere al usuario quitar la variable de su perfil del shell. No imprimas el valor del token |
| El modo automático de Claude Code deniega `gh pr merge` («merge sin review») aunque el usuario dio OK | El clasificador del modo automático no ve la aprobación del gate ni la del usuario | No lo esquives (ni con otra herramienta ni reformulando el comando). Dale al usuario el comando exacto que imprimió `merge_gate.py`, con el prefijo `env -u …` si la corrida lo usa, para que lo ejecute él, o sugiere una regla de permisos para `gh pr merge`. Anótalo en `RUN_STATE.md`. `close_run.py` cuenta igualmente ese merge |

## Resultado

Escribe en `RUN_STATE.md` (sección Preflight) una línea por control con OK, AVISO o FALLO.
