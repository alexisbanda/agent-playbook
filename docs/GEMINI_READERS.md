# Lectores Gemini

Exploración de código en solo lectura con Gemini a través del CLI `agy` de Antigravity (`scripts/gemini_reader.py`). Sustituye a los subagentes lectores de Claude (`haiku`) en la fase «Medir el terreno» de `resolve-issue` y `resolve-epic` sin gastar tokens de Claude ni engordar el contexto de subagentes. Si una llamada falla, el orquestador cae automáticamente a un lector Claude (`haiku`) para ese ámbito y lo anota en LÍMITES.

## Activarlo

1. Instala `agy` e inicia sesión en Antigravity con tu cuenta.
2. En la configuración del repo:
   ```json
   "gemini_readers": { "enabled": true }
   ```
   `/agent-playbook:setup-project` lo pregunta si encuentra `agy` en el PATH.

| Campo | Por defecto | Qué es |
| --- | --- | --- |
| `enabled` | `false` | Activa los lectores Gemini |
| `model` | `gemini-3.8-flash` | Modelo de `agy` (lista: `agy models`) |
| `effort` | `low` | Nivel de esfuerzo (`low`, `medium`, `high`) |
| `timeout_seconds` | `180` | Tiempo máximo de cada lector |

## Cómo funciona

El orquestador lanza de 1 a 3 llamadas en paralelo (una por pregunta o ámbito):

```bash
python3 <plugin>/scripts/gemini_reader.py <ticket> --question "<ámbito o pregunta>"
```

- Escribe el encargo en `.agent-playbook/runs/<ticket>/gemini-reader-<n>-input.md`.
- Invoca `agy` desde la raíz del repo con `--mode plan`, `--sandbox`, salida JSON con esquema (`summary`, `files`, `risks`, `tests`) y permisos por llamada en `--settings` (`allow` y `deny`), quitando `GEMINI_API_KEY` y `GOOGLE_API_KEY` del entorno:
  - **Lista permitida (`allow`):** `cat`, `ls`, `grep`, `head`, `tail`, `wc`, `git log`, `git show`, `git diff`, `git ls-files`, además de la herramienta nativa de lectura de archivos (`read_file`, sin permisos de terminal).
  - **Lista denegada (`deny`):** intérpretes, gestores de paquetes, shells, red y escritura (`node`, `npx`, `npm`, `pnpm`, `yarn`, `bun`, `deno`, `python`, `python3`, `pip`, `pip3`, `uv`, `ruby`, `perl`, `php`, `go`, `cargo`, `rustc`, `java`, `javac`, `make`, `sh`, `bash`, `zsh`, `curl`, `wget`, `rm`, `mv`, `cp`, `tee`, `touch`, `mkdir`, `sed`, `find`, `gh`, `docker`). Producen **denegación suave**: el modelo recibe el error de herramienta y el turno continúa sin abortar.
  - **Comandos no listados:** cualquier comando que no está ni en `allow` ni en `deny` aborta el turno en modo sin interfaz (`auto-denied` en stderr o `denied_actions` sin `structured_output` en stdout). En ese caso el script lee el último `run_command` del transcript de `agy`, guarda los últimos 4000 caracteres del stderr en `.agent-playbook/runs/<ticket>/gemini-reader-<n>-stderr.log`, hace un **único reintento** avisando en el prompt de que no repita ese comando y registra la lista `denied` en `gemini-readers.jsonl`.
- Normaliza las rutas, marca si algún archivo no existe en el repo, añade una línea a `gemini-readers.jsonl` e imprime una tabla compacta para el orquestador (con una línea `Reintento tras denegar: <cmd>` si se recuperó tras un comando denegado).
- Si sale con código 1 (`missing`, `timeout`, `denied`, `invalid` o `error`), el script indica lanzar un lector Claude (`ROLE: reader · CLASS: reader`, `haiku`) para ese ámbito y anotarlo en LÍMITES.

## Cómo formular las preguntas

Formula cada pregunta como **«dónde está / qué dice»**, no como **«comprueba si funciona»**: los lectores Gemini trabajan en solo lectura y sin ejecutar intérpretes ni código. Si un criterio o duda requiere ejecutar algo («¿pasa X?», «¿existe Y en la versión Z?»), el lector solo puede buscar pistas en código, lockfiles o documentación y apuntar en `risks` lo que quede pendiente de verificar; la comprobación ejecutable va al plan como chequeo del coder.

## Métricas

`close_run.py` añade a la línea de métricas el campo `gemini_readers` (ver [METRICS.md](METRICS.md)): llamadas (`calls`), llamadas degradadas (`degraded`), lecturas recuperadas tras reintento por denegación (`recovered`, opcional), tokens de Gemini (`tokens`) y segundos (`seconds`), o `null` si no hubo.
