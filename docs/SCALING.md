# Cómo escalar el playbook

El playbook arranca en **perfil reducido** (`"profile": "reduced"` en `.claude/agent-playbook.json`) y está pensado para crecer sin reescribirse. Lo que escala hacia abajo son los principios; lo que escala hacia arriba es la maquinaria. Este documento dice qué cambia en cada capa y qué señal indica que conviene dar el paso.

## Reglas que no cambian con el tamaño

- Un solo escritor por rama y un worktree por tarea.
- Nadie mergea su propio trabajo, y los agentes nunca mergean.
- Ningún agente espera más de unos 5 minutos: termina su turno y deja un `HANDBACK.md`.
- El plan se aprueba antes de construir.
- Lo que no se pudo probar se declara en la sección LÍMITES.

## Capa por capa

| Capa | Perfil `reduced` (hoy) | Perfil `full` | Cómo se pasa de uno a otro |
| --- | --- | --- | --- |
| 0 · Cuentas | `gh` y Claude Code en la máquina, protección de rama en `main`, secretos fuera de los prompts | Lo mismo, más límite de gasto mensual en la API y permisos mínimos por rol | Configurar el límite de gasto antes de automatizar corridas sin supervisión |
| 1 · Manuales | Skills `setup-project` y `resolve-issue` con sus `references/` | Skills por etapa: hotfix, promoción a producción, tuning wave | Añadir un directorio en `skills/` y bump de versión. Los capítulos compartidos van en `references/` comunes |
| 2 · Ruteo | 5 clases: `reader`, `standard`, `critical`, `review`, `orchestrate`. Orquestador en `sonnet` | 10 clases: `reader`, `mechanical`, `port`, `standard`, `root-cause`, `contract`, `money`, `security`, `review`, `orchestrate` (más `critical` por compatibilidad). Orquestador en `fable` | `routing/routing.json` define las dos tablas. Cambiar `profile` a `full` activa la completa. El perfil reducido acepta las clases del completo y las traduce, y el completo acepta `critical`, así que ningún encabezado se rompe al cambiar de perfil. Ver [ROUTING.md](../routing/ROUTING.md) |
| 3 · Hooks | Gate de modelos, gate de seguridad y telemetría con métricas por corrida, en modo `warn`. Ver [HOOKS.md](HOOKS.md) | Además: validación de tickets, recordatorios de convenciones, métricas por fase | Subir `hooks.mode` a `block` cuando la telemetría muestre pocos falsos positivos. Cada hook nuevo entra primero en `warn` |
| 4 · Motor | Un coder a la vez, baseline, reviewer solo en `critical`, review bot opcional ([REVIEW_BOT.md](REVIEW_BOT.md)), merge con `merge_gate.py` (4 condiciones, vigilante con `--watch`) | Coders en paralelo (uno por repo), patriots, reviewer por coder, gate concurrente, merges por tiers con vigilante | Activar paralelismo cuando un ticket toque más de un repo. El archivo de estado `RUN_STATE.md` ya tiene la forma del motor completo |
| 5 · Cierre | Prueba en vivo con chequeos `http` y `test`, evidencia en el ticket, LÍMITES, 2 o 3 journeys | Chequeos `e2e` y `mobile`, journeys completos, extensión a producción (rollback, flags, monitoreo) | Añadir entradas a `journeys` en la configuración del repo |
| Mejora continua | `metrics.jsonl` local y revisión manual | Tuning wave periódica, tripwires, panel de métricas | Activar el skill `tuning-wave` cuando haya al menos 10 corridas registradas |

## Señales para subir de nivel

| Señal en las métricas | Paso sugerido |
| --- | --- |
| Muchos tickets tocan más de un repositorio | Motor completo: paralelismo y merges por tiers |
| Las rondas de revisión por PR superan 2 de forma habitual | Reviewer en todas las clases, no solo en `critical` |
| El gasto se concentra en lectura de contexto | Más lectores `reader` antes de los coders y sesiones más cortas |
| Los gates en `warn` casi nunca dan falsos positivos | Pasar `hooks.mode` a `block` |
| Hay código que mueve dinero, contratos entre servicios o superficies de seguridad | Perfil `full` para separar `money`, `contract` y `security` |
| Entran más personas al equipo | Acordar quién orquesta y quién prueba cada ticket; publicar el marketplace a toda la organización |

## Cambiar de gestor de tickets

El resto del playbook no sabe qué tracker se usa: habla con un adaptador. Ver [TRACKERS.md](TRACKERS.md).
