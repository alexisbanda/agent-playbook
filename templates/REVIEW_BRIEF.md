ROLE: reviewer · CLASS: <clase>

Revisa el PR <url> del ticket <id>. No escribiste este código y **no lo tocas**: solo lo revisas.

## Contexto

- Ticket y criterios de aceptación: <texto o ruta>
- Plan aprobado: <resumen>
- HEAD a revisar: <sha>

## Qué revisar

1. ¿Cumple cada criterio de aceptación? ¿Algo del ticket se malinterpretó?
2. Corrección: casos borde, manejo de errores, concurrencia, datos nulos.
3. Seguridad: entrada no validada, IDOR, secretos, permisos.
4. Tests: ¿prueban los criterios o solo el camino feliz?
5. ¿El diff se sale del plan?

Usa `gh pr diff <pr>` y lee los archivos que haga falta.

## Veredicto

Devuelve exactamente una de estas dos líneas al principio:

- `APPROVE <sha>`
- `CHANGES_REQUESTED <sha>`

Después, si hay cambios pedidos, la lista numerada de problemas que bloquean, cada uno con archivo:línea y por qué. Las sugerencias menores van aparte, bajo "No bloquea".
