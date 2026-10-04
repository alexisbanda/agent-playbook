# Changelog

## 0.6.1

- El marketplace lista también [ticket-studio](https://github.com/alexisbanda/ticket-studio), el plugin hermano para que el PM escriba tickets listos para agentes. Sin cambios en el comportamiento de agent-playbook.

## 0.6.0

- **Journeys de regresión** con evidencia: `scripts/run_journeys.py` corre los `journeys` de la configuración, guarda los logs por ticket e imprime la tabla para el comentario de evidencia. `setup-project` propone candidatos.
- **Informe de métricas** (`scripts/metrics_report.py`): tabla por corrida con coste estimado (tarifas en `metrics/prices.json`) y evaluación de 8 tripwires (`metrics/tripwires.json`) sobre las últimas 10 corridas.
- **Skill `tuning-wave`**: lee las métricas de uno o varios repos, mira detrás de cada tripwire que salta y propone de 1 a 3 cambios atados a una métrica, que con OK lleva a un PR en este repositorio.
- Cada línea de métricas registra `playbook_version`, para comparar antes y después de un cambio en los manuales.
- `docs/METRICS.md`, con la tabla de impacto medido de la guía. Tests: 87.

## 0.5.0

- **Gate de merge** (`scripts/merge_gate.py`): comprueba las 4 condiciones (veredicto fresco y anclado, checks en verde, mergeable, espaciado de deploys), imprime el comando de merge con `--match-head-commit` y distingue "todavía no" (1) de "no se puede sin un cambio" (2). Con `--watch` hace de vigilante en segundo plano.
- **Review bot opcional** (`templates/workflows/claude-review.yml`, Claude Code Action `@v1`): revisa los PRs que no están en borrador contra el ticket y sus criterios; su veredicto es el check `claude-review`, ligado al commit. Se monta y desmonta con `review_bot.enabled` y `setup-project`. `docs/REVIEW_BOT.md`.
- Motor: review concurrente con el bot en `standard`, en serie en `critical`; `promoted_at` en UTC; vigilante en lugar de esperar.
- Config: `review_bot.check_name`. Tests del gate de merge (74 en total).

## 0.4.1

Correcciones de la segunda corrida real (pokemon-visiotech#3):

- **Gate de seguridad**: reconoce `gh` y `git` detrás de una variable (`$GH pr merge`), de `env -u …` o con `git -C <dir> push` (comprobando la rama de ese directorio). Antes, un `$GH pr merge` se saltaba las reglas de merge y promoción.
- **Corridas por sesión**: el marcador `active-run` guarda `$CLAUDE_CODE_SESSION_ID`. Otra sesión en el mismo repo ya no contamina las métricas ni pasa por el gate de modelos de la corrida.
- **Telemetría precisa**: los comandos solo cuentan en posición de comando (no si aparecen en un `grep` o un heredoc); `pr_opened` exige la URL del PR en la salida.
- `subagent_done` pasa a `subagent_launched` (marca el lanzamiento; los subagentes corren en segundo plano). `close_run.py` acepta los dos nombres.
- El preflight y `resolve-issue` piden escribir `gh` y `git` literales, sin variables.
- Tests: 57, incluidos los casos de la corrida. Los comandos reales de esa corrida, repasados con los patrones nuevos, dan exactamente 1 worktree, 1 PR abierto, promovido y mergeado.

## 0.4.0

- Hooks (`hooks/hooks.json`), inactivos en repos sin `.claude/agent-playbook.json`:
  - **Gate de modelos** (`PreToolUse` sobre `Agent`/`Task`): aplica `routing.json` durante una corrida; inyecta el modelo que falta, avisa o bloquea según `hooks.mode`, registra los overrides.
  - **Gate de seguridad** (`PreToolUse` sobre `Bash`): push a la rama base, push forzado, merges y promociones desde subagentes, merges sin `--match-head-commit`, `rm -rf` fuera del repo y patrones de producción configurables. En `warn` pide confirmación; en `block` deniega.
  - **Telemetría**: hechos de cada evento en `.agent-playbook/events.jsonl`, sin guardar prompts ni comandos. Aviso al iniciar sesión si los alias de modelo no están fijados.
- `scripts/close_run.py`: al cerrar la corrida, cruza eventos y transcripts y añade una línea validada a `metrics.jsonl` (tiempos, espera al humano, subagentes, PRs, gates, tokens por modelo).
- Corridas con marcador `.agent-playbook/active-run`: lo abre `resolve-issue` tras el preflight y lo quita `close_run.py`.
- Config: `hooks.production_patterns`. Esquema de métricas en `config/metrics.schema.json`.
- `docs/HOOKS.md`. Tests de los hooks en `tests/test_hooks.py` (fallan si un hook registra un error interno).

## 0.3.0

- Ruteo de modelos: `routing/routing.json` (fuente de verdad) con cuatro niveles (`haiku`, `sonnet`, `opus`, `fable`) y las tablas de los perfiles `reduced` y `full`, su esquema y `routing/ROUTING.md`.
- `scripts/route.py`: decide para cada lanzamiento de subagente si inyecta, permite o bloquea el modelo, comprueba el modelo de la sesión y avisa de los alias sin fijar. Lo usará el gate de modelos de la fase 3.
- Reglas: encabezado `ROLE · CLASS` obligatorio, `OVERRIDE: <motivo>` registrado, `fable` nunca escribe código (no se puede saltar), clases de alto riesgo solo en `opus` en ambos perfiles.
- `resolve-issue`, el motor y las plantillas usan la tabla en lugar de modelos fijos. El coder de clase `critical` pasa a `opus`; el reviewer usa la clase `review`.
- CI: valida `routing.json` contra su esquema y corre los tests de `tests/`.

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
