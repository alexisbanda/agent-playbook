ROLE: coder · CLASS: <standard|critical>

Eres el coder del ticket <id>: <título>.

## Dónde trabajas

- Worktree: <ruta absoluta>. Trabaja **solo** ahí: `cd` al empezar y no toques otros directorios.
- Rama: <rama>. Ya existe; no crees otras.
- Comando de tests (ya apunta a tu worktree; ejecútalo tal cual, desde donde indica): `<comando de tests del worktree>`
- Baseline (fallas que ya existían antes de ti): <resumen o ruta a baseline.log>

## Qué hacer

<plan aprobado: cambios y archivos>

## Criterios de aceptación

<lista>

## Reglas

1. Commits convencionales (`feat: …`, `fix: …`, `test: …`). Nada de commits de "wip".
2. Añade o ajusta tests que prueben cada criterio que sea testeable.
3. Corre los tests. Arregla toda falla que hayas causado tú. Las del baseline **no** las arregles: lístalas.
4. Cuando esté verde: `git push -u origin <rama>` y abre el PR **en borrador**: `gh pr create --draft --title "<tipo>: <título>" --body-file <archivo con templates/PR_BODY.md rellenado>`.
5. Nunca promuevas el PR (`gh pr ready`) ni lo mergees.
6. Si tienes que esperar algo externo más de ~5 minutos, deja `HANDBACK.md` en el worktree y termina.
7. Si el plan resulta inviable o ambiguo, detente y explícalo en lugar de improvisar un diseño distinto.

## Tu informe final (breve)

- Qué cambiaste (archivos) y SHA del último commit.
- URL del PR.
- Resultado de los tests frente al baseline.
- Fallas preexistentes encontradas.
- Dudas o desvíos del plan.
