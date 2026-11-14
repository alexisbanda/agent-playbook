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
- Invoca `agy` desde la raíz del repo con `--mode plan`, `--sandbox`, salida JSON con esquema (`summary`, `files`, `risks`, `tests`) y una lista de permisos de solo lectura por llamada (`cat`, `ls`, `grep`, `git log`, `git show`), quitando `GEMINI_API_KEY` y `GOOGLE_API_KEY` del entorno.
- Normaliza las rutas, marca si algún archivo no existe en el repo, añade una línea a `gemini-readers.jsonl` e imprime una tabla compacta para el orquestador.
- Si sale con código 1 (`missing`, `timeout`, `denied`, `invalid` o `error`), el script indica lanzar un lector Claude (`ROLE: reader · CLASS: reader`, `haiku`) para ese ámbito y anotarlo en LÍMITES.

## Métricas

`close_run.py` añade a la línea de métricas el campo `gemini_readers` (ver [METRICS.md](METRICS.md)): llamadas (`calls`), llamadas degradadas (`degraded`), tokens de Gemini (`tokens`) y segundos (`seconds`), o `null` si no hubo.
