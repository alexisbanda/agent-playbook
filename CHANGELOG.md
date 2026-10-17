# Changelog

## 1.0.3

Lo visto al revisar el coste de kickoff-demo#2 y #5: el informe de métricas daba la mitad del coste real ($2,67 y $4,17 frente a $4,84 y $8,11).

- **Tokens de salida bien contados** (`scripts/close_run.py`): Claude Code escribe cada respuesta en varios registros con el mismo id (uno por bloque mientras se genera), y solo el último trae los `output_tokens` finales. Se contaba el primero: en #5, 16.493 tokens de salida del coder en vez de 75.681.
- **El orquestador cuenta:** si la sesión empezó antes de que los hooks del repo la vieran (no hay `session_start`), su transcript se busca junto al de sus subagentes (`<dir>/<sesión>/subagents/…` → `<dir>/<sesión>.jsonl`); además, `user_prompt` guarda la ruta del transcript. Era cerca del 40 % del coste.
- **Brief del coder, regla 9 («pocos pasos»):** cada llamada a una herramienta relee todo el contexto (el 74 % del coste del coder en #5, con 124 llamadas). Agrupar lint, typecheck y tests en una llamada; archivos nuevos de una vez; `git add` y `commit` juntos, y push y PR al final; no releer lo que ya está en el contexto.
- `docs/METRICS.md`: qué incluyen los tokens por modelo.
- 107 tests (2 nuevos).

## 1.0.2

Lo visto en la corrida de alexisbanda/kickoff-demo#2, el primer **ticket 0 de un repo sin código** resuelto de punta a punta (kickoff de ticket-studio → `TECH.md` → `resolve-issue`; Next.js 16, Postgres, Prisma 7, Vitest y CI; 28 minutos, pruebas en vivo a la primera).

- **`setup-project` en un repo sin código:** no hay comando de tests que ejecutar. Si `TECH.md` fija el stack, propone el que creará el ticket 0 y lo guarda solo con OK, diciendo que no se ejecutó; si no, lo deja vacío. Comprueba también la versión del runtime.
- **Versión del runtime** (`references/test-runtimes.md`, `engine.md` paso 1): dónde leer la que pide el proyecto, avisar si `TECH.md` nombra una fuera de soporte (la corrida pedía Node 20, sin soporte desde abril de 2026), instalar la que falta en el espacio del usuario con la aprobación del plan y usar el mismo prefijo en baseline, coder y verificación.
- **Brief del coder, regla 8:** los generadores escriben configuración de agentes (`prisma init` creó `.claude/skills/`, `.windsurf/`, `.agents/`); no se commitea nada en `.claude/`, se borra lo que creen ahí, y lo que el framework regenera en cada arranque (`AGENTS.md` de `next dev`) se commitea y se dice. Los generadores que pisan archivos del repo se ejecutan fuera del worktree.
- **README:** el límite «proyecto desde cero sin probar» pasa a «probado una vez».

## 1.0.1

- Marketplace: la ficha de ticket-studio ya no menciona Jira (ticket-studio 1.0 trabaja con GitHub Issues y Notion).

## 1.0.0

Primera versión estable (MVP), junto con ticket-studio 1.0: del documento de kickoff al PR mergeado con evidencia en el ticket, con GitHub Issues o Notion.

- **Notion probado en real**: las seis operaciones del adaptador, con notas de la primera corrida (estado como select, URLs sin `?pvs=…`, prefijo `userDefined:` solo para `url`/`id`, evidencia como comentario corto más bloque al final).
- **Identificador de Notion**: carpetas y ramas usan los **8 últimos** caracteres del id de página; los 8 primeros se repiten dentro de un workspace y hacían chocar dos tickets.
- **README**: la fase 1b (arranque) queda sustituida por el ticket 0 de ticket-studio resuelto con `resolve-issue`; roadmap al día y **límites conocidos de la 1.0**.
- Compatible con el contrato de ticket v1.1 de ticket-studio (tipo `improvement`): `ticket_check.py` ya trata cualquier tipo que no sea épica con el mismo mínimo.

## 0.7.1

Lo visto en la corrida de alexisbanda/pokemon-visiotech#6, el primer ticket de ticket-studio resuelto de punta a punta.

- **Merge bloqueado por el modo automático:** el clasificador deniega `gh pr merge` aunque el usuario haya dado OK. `references/preflight.md` (Problemas conocidos) y `references/engine.md` (paso 7) dicen qué hacer: no esquivarlo, darle al usuario el comando del gate y seguir con el cierre cuando confirme.
- **Telemetría de merges hechos a mano:** `close_run.py` consulta en GitHub los PRs abiertos en la corrida; `prs_merged` incluye los que se mergearon fuera de la sesión y el nuevo campo opcional `prs_merged_outside` dice cuántos. Sin `gh` o sin red, cuenta solo los eventos, como antes.
- **Verificación:** `engine.md`, paso 4, pide contrastar la tabla criterio → prueba del PR con los tests reales (en la corrida, el PR decía comprobar campos que ningún test comprobaba).
- 104 tests (3 nuevos).

## 0.7.0

Integración **opcional** con [ticket-studio](https://github.com/alexisbanda/ticket-studio) (su fase 3). Desactivada por defecto: sin `tickets.contract: true`, el playbook se comporta igual que en la 0.6.

- Config: `tickets.contract` (por defecto `false`) y `tickets.ready_label` (por defecto `ready`).
- `scripts/ticket_check.py`: comprueba la etiqueta de listo y el mínimo del contrato con lógica propia; si Ticket Studio está instalado, añade su puntuación. Un Ticket Studio roto o incompatible nunca rompe la corrida. Avisa, no bloquea.
- `resolve-issue`: con la opción activa, comprueba el ticket y propone resolver los sub-issues de una épica en vez de la épica; con un ticket del contrato, usa sus criterios tal cual y lleva sus preguntas abiertas al plan. Lee `docs/product/BRIEF.md` y `TECH.md` si existen, con o sin la opción.
- Adaptador de GitHub: cómo leer las dos caras, preguntas abiertas, etiquetas, padre y sub-issues.
- Métricas: `ticket_quality` en `metrics.jsonl` y columna "Calidad del ticket" en el informe.
- 101 tests (14 nuevos).

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
