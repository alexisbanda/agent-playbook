# Métricas y mejora continua

El sistema aprende de sus propias corridas. Lo que miden los hooks alimenta cambios en los manuales, y esos cambios llegan a todos con la siguiente versión del plugin.

```
corrida → hooks registran eventos → close_run.py escribe una línea validada
        → tuning wave compara con los tripwires → 1-3 cambios a los manuales
        → PR + review + versión nueva → auto-actualización → corrida siguiente
```

## Qué se mide

Una línea por corrida en `.agent-playbook/metrics.jsonl`, escrita por `scripts/close_run.py` (esquema en [`config/metrics.schema.json`](../config/metrics.schema.json)). Detalle de los eventos en [HOOKS.md](HOOKS.md).

| Métrica | Qué revela |
| --- | --- |
| Tokens por modelo y coste estimado | Dónde está el gasto. Suele estar en el contexto que se relee (lectura de caché), no en lo que el modelo escribe. Incluye al orquestador (la sesión principal, solo dentro de la ventana de la corrida) y a cada subagente; de cada respuesta cuenta el último registro del transcript, que es el que trae los tokens de salida finales |
| Minutos totales y minutos esperando al humano | Cuánto frenan las aprobaciones |
| Subagentes por modelo | Si el ruteo se usa como se diseñó |
| PRs abiertos, promovidos y mergeados | Si el flujo llega al final. `prs_merged` incluye los PRs de la corrida que el usuario mergeó fuera de la sesión (se consultan en GitHub al cerrar); `prs_merged_outside` dice cuántos fueron |
| Contexto inicial del orquestador (`orchestrator_ctx_start_k`) | Miles de tokens que la sesión principal ya traía en su primera llamada de la corrida. Si es alto, la sesión arrastra tickets anteriores y cada llamada los relee; se arregla empezando cada ticket en una sesión nueva |
| Bucle del coder (`coder_calls_max`, `coder_ctx_peak_k`, `context_guard_warnings`) | Llamadas del coder más largo de la corrida, el mayor contexto que alcanzó un coder (en miles de tokens) y cuántas veces avisó el vigilante de contexto. El coder suele ser la mitad del coste, y crece con llamadas × contexto |
| Compactaciones | Si las corridas son demasiado largas o los agentes demasiado pesados |
| Decisiones de los gates y overrides | Qué reglas se disparan y quién las salta |
| E2E a la primera | Si el cambio llegó sano a la prueba en vivo. Es el único campo declarado por el orquestador, y está marcado así |
| Versión del playbook | Para comparar antes y después de un cambio en los manuales |
| Calidad del ticket (`ticket_quality`) | Solo con `tickets.contract: true`. Puntuación de Ticket Studio, o cumplimiento mínimo si no está instalado, y si el ticket llegó marcado como listo. Cruzada con E2E a la primera y rondas de revisión, dice si los tickets incompletos cuestan retrabajo |

El coste es una **estimación** con las tarifas de la API de [`metrics/prices.json`](../metrics/prices.json). No refleja descuentos ni un plan de suscripción.

## Informe

```bash
python3 scripts/metrics_report.py ~/Sites/<repo>/.agent-playbook/metrics.jsonl [otro/metrics.jsonl ...]
```

Muestra una tabla por corrida y el estado de cada tripwire sobre las últimas 10. Con `--json`, la misma información para procesarla.

## Tripwires

Umbrales en [`metrics/tripwires.json`](../metrics/tripwires.json). Que uno salte no es un fallo: es la señal para revisar los manuales.

| Tripwire | Umbral inicial | Salta cuando |
| --- | --- | --- |
| `e2e_first_pass_rate_min` | 0,8 | Menos del 80 % de las pruebas en vivo pasan a la primera |
| `human_wait_share_max` | 0,5 | La mediana del tiempo esperando al humano supera la mitad de la corrida |
| `compaction_runs_share_max` | 0,2 | Más del 20 % de las corridas compactan contexto |
| `cost_per_run_usd_max` | 5 USD | La mediana del coste estimado por corrida lo supera |
| `orchestrator_ctx_start_k_max` | 150 | La mediana del contexto del orquestador en su primera llamada supera 150k tokens (la sesión arrastra tickets anteriores) |
| `coder_calls_max` | 80 | La mediana de llamadas del coder más largo de cada corrida supera 80 |
| `coder_ctx_peak_k_max` | 200 | La mediana del contexto máximo de un coder supera 200k tokens |
| `overrides_per_run_max` | 1 | Más de un override de ruteo por corrida de media |
| `model_blocks_per_run_max` | 1 | El gate de modelos bloquea más de una vez por corrida de media |
| `untracked_runs_max` | 0 | Alguna corrida sin tokens medidos (telemetría rota) |

Hacen falta al menos 3 corridas para evaluarlos. Los umbrales son un punto de partida: la propia tuning wave puede proponer recalibrarlos.

## Tuning wave

`/agent-playbook:tuning-wave` (semanal o cada 10 corridas). Lee las métricas, mira detrás de cada tripwire que salta y propone de 1 a 3 cambios, cada uno atado a la métrica que debe mover. Con tu aprobación, los lleva a un PR en este repositorio.

## Impacto medido

Para completar la tabla de la guía, registra estos valores antes de adoptar el playbook y después de unas semanas de uso. Los de "después" salen del informe.

| Indicador | Antes | Después | De dónde sale |
| --- | --- | --- | --- |
| Tiempo desde ticket hasta dev probado | | | `wall_minutes` |
| PRs mergeados por semana | | | `prs_merged` agrupado por semana |
| Rondas de revisión por PR | | | Comentarios del review bot / `RUN_STATE.md` |
| Coste por PR mergeado | | | Coste estimado / `prs_merged` |
| Tickets cerrados con evidencia completa | | | Comentarios de evidencia con sección LÍMITES |
