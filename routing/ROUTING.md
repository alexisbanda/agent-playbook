# Ruteo de modelos

Qué modelo hace cada trabajo. La fuente de verdad es [`routing.json`](routing.json); este documento la explica, pero si discrepan, manda el JSON. El hook de la fase 3 y `scripts/route.py` leen el JSON directamente.

## Niveles

| Nivel | Alias (Agent tool) | Modelo | Precio entrada / salida por millón de tokens |
| --- | --- | --- | --- |
| `economy` | `haiku` | Claude Haiku 4.5 | $1 / $5 |
| `standard` | `sonnet` | Claude Sonnet 5 | $2 / $10 |
| `premium` | `opus` | Claude Opus 5.5 | $4 / $20 |
| `flagship` | `fable` | Claude Fable 5.1 | $10 / $50 |

Para que cada alias apunte a la versión exacta, fija estas variables en `~/.claude/settings.json` (bloque `env`):

```json
{
  "env": {
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5-5",
    "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-fable-5-1"
  }
}
```

Si faltan, el gate de modelos avisa pero no bloquea.

## Clases por perfil

El perfil sale de `profile` en `.claude/agent-playbook.json`.

### `reduced`

| Clase | Para qué | Por defecto | Permitidos |
| --- | --- | --- | --- |
| `reader` | Leer y resumir, sin decidir | `haiku` | `haiku`, `sonnet` |
| `standard` | Un feature o fix normal, cambios mecánicos, portar pantallas | `sonnet` | `sonnet`, `opus` |
| `critical` | Dinero, contratos entre servicios, seguridad, migraciones de datos, bug de causa desconocida | `opus` | `opus` |
| `review` | Revisar el trabajo de un coder | `sonnet` | `sonnet`, `opus` |
| `orchestrate` | La sesión principal | `sonnet` | `sonnet`, `opus`, `fable` |

Las clases del perfil completo también se aceptan en el reducido y se traducen: `mechanical` y `port` → `standard`; `root-cause`, `contract`, `money` y `security` → `critical`. Así un encabezado escrito pensando en el perfil completo sigue funcionando.

### `full`

| Clase | Para qué | Por defecto | Permitidos |
| --- | --- | --- | --- |
| `reader` | Leer y resumir | `haiku` | `haiku`, `sonnet` |
| `mechanical` | Cambios sin criterio de diseño (espejos, bumps) | `sonnet` | `sonnet` |
| `port` | Portar pantallas del front | `sonnet` | `sonnet`, `opus` |
| `standard` | Un fix normal | `sonnet` | `sonnet`, `opus` |
| `root-cause` | Encontrar la causa de un bug difícil | `opus` | `opus`, `sonnet` |
| `contract` | Cambios de contrato o de forma del wire | `opus` | `opus` |
| `money` | Código que mueve dinero | `opus` | `opus` |
| `security` | Superficies de seguridad o IDOR | `opus` | `opus` |
| `critical` | Compatibilidad con el perfil reducido | `opus` | `opus` |
| `review` | Revisar el trabajo de un coder | `sonnet` | `sonnet`, `opus` |
| `orchestrate` | El jefe de obra | `fable` | `fable` |

## Reglas

1. **Encabezado obligatorio.** La primera línea de cada prompt de subagente es `ROLE: <rol> · CLASS: <clase>`. Se acepta `|` como separador. Roles habituales: `reader`, `coder`, `patriot`, `reviewer`.
2. **Modelo explícito.** El orquestador pasa `model` con el alias de la clase. Si no lo pasa, el gate inyecta el de por defecto.
3. **`fable` nunca escribe código.** Un `coder` o `patriot` con `fable` se bloquea siempre, aunque traiga `OVERRIDE`. Se reserva para pensar y coordinar.
4. **El reviewer sube a `opus`** cuando revisa trabajo de clase `critical` (o `contract`, `money`, `security`), cuando revisa el PR que resuelve el ticket en el perfil completo, o en una segunda revisión tras un desacuerdo.
5. **Excepciones con `OVERRIDE: <motivo>`** en las primeras líneas del prompt: deja pasar un modelo que la clase no permite y queda registrado en la telemetría. No salta la regla 3.
6. **Modelo de la sesión.** El resolver solo arranca en una sesión `sonnet`, `opus` o `fable`. En el perfil completo, la clase `orchestrate` pide `fable`; el preflight avisa si la sesión usa otro.

## Comprobar una decisión

```bash
python3 scripts/route.py --header "ROLE: coder · CLASS: money" --model sonnet
python3 scripts/route.py --session-model claude-opus-5-5
```

Devuelve un JSON con `decision` (`allow`, `inject` o `block`), el modelo resultante y el motivo. Sale con código 2 si bloquea.

## Cambiar la tabla

Edita `routing.json`, ajusta este documento y los tests de `tests/test_route.py`, y sube la versión del plugin. La CI valida el JSON contra `routing.schema.json` y corre los tests.
