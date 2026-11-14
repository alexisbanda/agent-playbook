# Preflight

Se ejecuta antes de cualquier otra cosa. Cada control falla con un mensaje concreto de qué falta y cómo arreglarlo. No sigas con un control en rojo.

## Ejecución en un solo paso (`scripts/preflight.py`)

Ejecuta todos los controles de golpe y abre `.agent-playbook/active-run` si no hay fallos:

```bash
python3 <plugin>/scripts/preflight.py --session-model <id del modelo de la sesión> --open-run <ticket> [--override-model "<motivo>"]
```

El script devuelve un JSON con `ok` (`true` si ningún control dio `fail`), la lista `checks`, metadatos detectados (`profile`, `tracker_type`, `base_branch`, `origin_sha`, `gh_env_prefix`) y el bloque `markdown` listo para pegar en `RUN_STATE.md`. Si `checks` incluye avisos (`warn`) que requieren decisión del usuario (cambios sin commitear en el clon principal, commits locales sin push en la rama base, un `active-run` de otro ticket o una sesión con demasiado contexto), pregúntale antes de seguir. Los avisos del permiso de merge (control 8), del segundo reviewer (control 9) y de los lectores Gemini (control 10) no requieren decisión: menciónalos y sigue.

A continuación se detalla qué comprueba cada control:

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

`preflight.py` compara la versión instalada en `<plugin>/.claude-plugin/plugin.json` con la última publicada en GitHub y guarda el resultado en `.agent-playbook/cache/version-check.json` durante 24 horas para no repetir llamadas de red en el mismo día.

Si `installed` es menor que `latest`, avisa: el usuario debe actualizar el plugin (`/plugin` → Marketplaces → actualizar, y luego `/reload-plugins`). No bloquea, salvo que el usuario quiera actualizar primero. Si la consulta remota falla, dilo y sigue.

## 3. Configuración del repo

- `.agent-playbook.json` o `.claude/agent-playbook.json` existe. Si no, ejecuta el skill `setup-project` y vuelve aquí.
- Es válida contra `<plugin>/config/agent-playbook.schema.json` (con `jsonschema` si está instalado; si no, revisa `version`, `profile` y `tracker.type`).
- `tracker.type` es `github`, `notion` o `jira`. Para `linear`, detente: no hay adaptador todavía.

## 4. Herramientas y permisos

- `gh auth status` en verde, con el scope `repo`. Si falla por un token de entorno, `preflight.py` reintenta sin `GITHUB_TOKEN`/`GH_TOKEN` y devuelve `gh_env_prefix: "env -u GITHUB_TOKEN -u GH_TOKEN"` (ver [Problemas conocidos](#problemas-conocidos)).
- `git remote get-url origin` apunta a GitHub.
- Si el tracker es `notion`, el conector de Notion responde (por ejemplo, una búsqueda de la base de datos configurada). Si no está autorizado, detente y pide al usuario que lo autorice en los conectores de claude.ai.
- Si el tracker es `jira`, el conector de Atlassian responde y llega al proyecto. `preflight.py` no puede comprobarlo (es un conector MCP), así que lo haces tú:
  1. `getAccessibleAtlassianResources`. Si falla o no está autorizado, detente y pide al usuario que autorice el conector de Atlassian en los conectores de claude.ai.
  2. Elige el sitio: el de `tracker.jira.cloud_id` o el de `tracker.jira.site_url` si están configurados; si no, el único accesible. Si hay varios y la configuración no dice cuál, pregunta. Si el configurado no aparece entre los accesibles, detente: la cuenta autorizada no tiene acceso a ese sitio.
  3. `getVisibleJiraProjects` sobre ese sitio: `tracker.jira.project_key` tiene que aparecer. Si no, detente y dilo (clave mal escrita o sin permiso en el proyecto).
  4. Anota el `cloudId` en `RUN_STATE.md` y úsalo en todas las llamadas del adaptador (`references/trackers/jira.md`).

## 5. Estado del clon principal

- `git fetch origin` sin errores.
- `git status --porcelain` en el clon principal:
  - vacío: OK;
  - solo `.claude/agent-playbook.json`, `.agent-playbook.json` y `.gitignore` (lo que deja `setup-project`): AVISO, sigue, y recuerda al usuario que conviene versionarlos;
  - cualquier otro cambio: pregunta. No los muevas ni los descartes por tu cuenta.
- **Rama base al día con el remoto.** `git log --oneline origin/<base>..<base>` y `git log --oneline <base>..origin/<base>`, con `<base>` la rama por defecto:
  - sin salida: OK;
  - commits locales sin push: AVISO. Enuméralos y explica que el worktree parte de `origin/<base>`, así que **no estarán en el PR**. Pregunta si hacer push antes o seguir sin ellos;
  - el local va por detrás: OK (el worktree parte de `origin`), pero menciónalo.

## 6. Hooks

- Si existe `.agent-playbook/hook-errors.log` con entradas recientes, AVISO: algún hook falló (los hooks no bloquean la sesión cuando fallan, así que una regla podría no estar aplicándose). Muestra la última entrada.
- Si existe `.agent-playbook/active-run` de otro ticket, pregunta: puede ser una corrida que no se cerró.

## 7. Contexto de la sesión

Cada ticket se resuelve en una sesión nueva. El orquestador relee todo su contexto en cada llamada, así que una sesión que ya resolvió otro ticket paga por él una y otra vez (en castkit, 8 corridas encadenadas pasaron de 168k a 733k tokens de contexto y de 1,9 a 12 USD por corrida).

`preflight.py` busca el transcript de la sesión en `.agent-playbook/events.jsonl` y compara su contexto actual con el tripwire `orchestrator_ctx_start_k_max` (150k):

- por debajo: OK;
- por encima: AVISO y **no abre `active-run`**, porque la corrida pertenece a la sesión que la abre y `/clear` empieza otra. Propón al usuario `/clear` (o una sesión nueva) y repetir allí el preflight; todo lo necesario para seguir está en el tracker, `RUN_STATE.md` y el repositorio. Si decide seguir en esta sesión, repite con `--keep-session` y anótalo en `RUN_STATE.md`.

## 8. Permiso de merge

`preflight.py` busca en `.claude/settings.json`, `.claude/settings.local.json` y `~/.claude/settings.json` una regla `permissions.allow` para `gh pr merge`. Sin ella, el modo automático de Claude Code deniega el merge aunque el usuario haya dado el OK, y cada PR cuesta una parada más: el usuario lo mergea a mano y vuelve a decirlo (en castkit y recuerdos, 23 de 32 PRs).

- con regla: OK;
- sin regla: AVISO que **no requiere decisión**. No te detengas por él; menciónalo al presentar el plan y sugiere `setup-project` para añadir `Bash(gh pr merge * --match-head-commit *)`.

La regla no debilita el control: el OK explícito del usuario y `merge_gate.py` siguen siendo obligatorios, y el gate de seguridad bloquea un `gh pr merge` sin `--match-head-commit` o lanzado desde un subagente.

## 9. Segundo reviewer (solo si `second_reviewer.enabled`)

Si `second_reviewer.enabled` no es `true` en la configuración del repo, este control se omite y no aparece en la tabla. Si está activado, `preflight.py` comprueba si `agy` está en el `PATH`:

- con `agy` disponible: OK, indicando el modelo configurado (`second_reviewer.model`);
- sin `agy` en el `PATH`: AVISO (`second_reviewer.enabled pero agy no está en el PATH: la corrida seguirá sin segundo reviewer`). Nunca da `FALLO` ni requiere decisión: menciónalo y sigue.

## 10. Lectores Gemini (solo si `gemini_readers.enabled`)

Si `gemini_readers.enabled` no es `true`, este control se omite. Si está activado, `preflight.py` comprueba si `agy` está en el `PATH`:

- con `agy` disponible: OK, indicando el modelo y esfuerzo configurados (`gemini_readers.model`, `gemini_readers.effort`);
- sin `agy` en el `PATH`: AVISO (`gemini_readers.enabled pero agy no está en el PATH: se caerá a lectores Claude haiku`). Nunca da `FALLO` ni requiere decisión: menciónalo y sigue.

## Problemas conocidos

| Síntoma | Causa | Qué hacer |
| --- | --- | --- |
| `gh auth status` dice que el token es inválido, o `gh` responde 401, aunque el usuario hizo `gh auth login` | Hay una variable `GITHUB_TOKEN` (o `GH_TOKEN`) exportada en el entorno, que `gh` usa antes que las credenciales guardadas | Comprueba `env -u GITHUB_TOKEN -u GH_TOKEN gh auth status`. Si así está en verde, escribe ese prefijo **literal** delante de cada comando `gh` de la corrida (`env -u GITHUB_TOKEN -u GH_TOKEN gh pr merge …`) y anótalo en `RUN_STATE.md`. No lo guardes en una variable (`GH=...; $GH pr ...`): los hooks reconocen los comandos por su texto. Sugiere al usuario quitar la variable de su perfil del shell. No imprimas el valor del token |
| El modo automático de Claude Code deniega `gh pr merge` («merge sin review») aunque el usuario dio OK | El clasificador del modo automático no ve la aprobación del gate ni la del usuario | No lo esquives (ni con otra herramienta ni reformulando el comando). Dale al usuario el comando exacto que imprimió `merge_gate.py`, con el prefijo `env -u …` si la corrida lo usa, para que lo ejecute él, o sugiere una regla de permisos para `gh pr merge`. Anótalo en `RUN_STATE.md`. `close_run.py` cuenta igualmente ese merge |

## Resultado

Escribe en `RUN_STATE.md` (sección Preflight) el bloque `markdown` devuelto por `preflight.py` (una línea por control con OK, AVISO o FALLO).
