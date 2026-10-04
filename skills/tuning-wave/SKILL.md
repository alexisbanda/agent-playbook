---
name: tuning-wave
description: Revisión periódica del playbook a partir de las métricas de las corridas. Resume .agent-playbook/metrics.jsonl de uno o varios repos, compara con los tripwires y propone de 1 a 3 cambios a los manuales, cada uno atado a la métrica que debe mover, para llevarlos a un PR en agent-playbook. Úsalo cuando el usuario pida la tuning wave, revisar las métricas del playbook o mejorar el proceso con datos.
argument-hint: "[rutas a metrics.jsonl de otros repos]"
---

# tuning-wave

Cierra el ciclo de mejora continua: las corridas dejan métricas medidas por los hooks, esta revisión las convierte en cambios a los manuales, y la siguiente versión del plugin los lleva a todos.

## Parámetros

| Parámetro | Valor |
| --- | --- |
| Raíz del plugin (`<plugin>`) | `${CLAUDE_SKILL_DIR}/../..` |
| Informe | `python3 <plugin>/scripts/metrics_report.py [archivos...]` |
| Umbrales | `<plugin>/metrics/tripwires.json` |
| Precios para el coste estimado | `<plugin>/metrics/prices.json` |
| Cambios propuestos | Máximo 3 por ola |

## Pasos

1. **Reunir las métricas.** Por defecto, `.agent-playbook/metrics.jsonl` del repo actual. Añade las rutas que pase el usuario (otros repos que usen el playbook). Si hay menos de 3 corridas en total, dilo y detente: con tan pocos datos cualquier conclusión es ruido.
2. **Generar el informe** con `metrics_report.py` y muéstralo tal cual. Distingue las corridas por `playbook_version`: las líneas sin versión (0.4.x o anterior) pueden tener métricas infladas por fallos de telemetría ya corregidos. Menciónalo y no bases un cambio solo en ellas.
3. **Mirar detrás de cada tripwire que salta**, y solo de esos. Fuentes, de más a menos fiable:
   - `.agent-playbook/events.jsonl`: decisiones de los gates, overrides, esperas;
   - `.agent-playbook/runs/<ticket>/RUN_STATE.md`: plan, agentes, punto de retoma;
   - los comentarios de evidencia en los tickets, en especial las secciones LÍMITES;
   - el skill o la referencia que gobierna esa fase.

   Busca la causa en el proceso (un paso ambiguo, una regla que falta, un umbral mal puesto), no en una corrida concreta.
4. **Proponer de 1 a 3 cambios.** Para cada uno:

   | Campo | Contenido |
   | --- | --- |
   | Problema | Qué muestran las métricas, con los números |
   | Cambio | Archivo del playbook y qué cambia (skill, referencia, hook, tabla de ruteo, tripwire) |
   | Métrica que debe mover | Cuál y en qué dirección |
   | Cómo saber si funcionó | Qué mirar en la siguiente ola |

   Prefiere cambiar texto antes que código, y hooks solo cuando una regla se esté saltando. Si un umbral está mal calibrado, el cambio puede ser el propio tripwire. Si ningún tripwire salta, dilo: "sin cambios" es un resultado válido.
5. **Esperar la aprobación** del usuario sobre qué cambios aplicar.
6. **Aplicarlos** en el repositorio del playbook (`alexisbanda/agent-playbook`): rama `tuning/<fecha>`, cambios aprobados, entrada en `CHANGELOG.md` que cite las métricas, bump de versión, tests en verde. El PR incluye la tabla del paso 4. Commit, push y PR con OK del usuario.
7. **Resumen final:** tripwires que saltaron, cambios propuestos y aplicados, enlace al PR y qué mirar en la próxima ola.

## Frecuencia

Semanal, o cada 10 corridas, lo que llegue antes. Se puede programar con el skill `schedule`.
