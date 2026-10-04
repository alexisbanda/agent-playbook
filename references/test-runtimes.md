# Entornos de tests

Cómo deducir `environment.test_command` y `environment.worktree_test_command`. Los dos se ejecutan **desde la raíz del clon principal**. En `worktree_test_command`, `{worktree}` se sustituye por la ruta absoluta del worktree.

El problema que resuelve `worktree_test_command`: si los tests corren en un contenedor que monta el clon principal, correrlos "dentro del worktree" con el mismo comando prueba en realidad el código del clon principal y da un falso verde.

## Detección

Comprueba en este orden y quédate con el primero que encaje:

| Señal en el repo | Entorno |
| --- | --- |
| `vendor/bin/sail` y un servicio `laravel.test` en `compose.yaml` o `docker-compose.yml` | Laravel Sail |
| `compose.yaml` / `docker-compose.yml` con un servicio de la app que monta `.` y la suite necesita servicios del compose (base de datos, cache) | Docker Compose |
| Ninguna de las anteriores | Local |

Si el `phpunit.xml`, `.env.testing` o equivalente apunta a un host que solo existe dentro de la red del compose (por ejemplo `DB_HOST=mysql`), es Sail o Docker Compose aunque el comando local parezca funcionar.

## Laravel Sail

| Campo | Valor |
| --- | --- |
| `test_command` | `./vendor/bin/sail test` |
| `worktree_test_command` | `WWWUSER=$(id -u) WWWGROUP=$(id -g) docker compose run --rm --no-deps -v {worktree}:/var/www/html -v $PWD/vendor:/var/www/html/vendor -v $PWD/.env:/var/www/html/.env laravel.test php artisan test` |

- Los contenedores tienen que estar arriba (`./vendor/bin/sail up -d`); `--no-deps` reutiliza la base de datos que ya corre.
- `WWWUSER` y `WWWGROUP` hacen falta porque el entrypoint de Sail cambia a ese usuario; sin ellos falla con `unable to find user`.
- `vendor/` y `.env` no están versionados: se montan desde el clon principal. Si el ticket cambia dependencias (`composer.json`), hay que instalar `vendor/` en el worktree y quitar ese montaje.
- La base de datos de tests es compartida: no corras dos suites a la vez.

## Docker Compose genérico

| Campo | Valor |
| --- | --- |
| `test_command` | `docker compose run --rm <servicio> <comando de tests>` |
| `worktree_test_command` | `docker compose run --rm --no-deps -v {worktree}:<ruta de la app en el contenedor> <servicio> <comando de tests>` |

Lee el servicio, la ruta de montaje y el comando del propio `compose.yaml` y del `Makefile` o los scripts del proyecto. Monta además desde el clon principal lo que no esté versionado y la suite necesite (dependencias, `.env`).

## Local

| Campo | Valor |
| --- | --- |
| `test_command` | El script de tests del proyecto: `composer test`, `npm test`, `pytest`, `make test`… |
| `worktree_test_command` | Vacío. El motor ejecuta `test_command` con el worktree como directorio de trabajo |

Si el worktree necesita dependencias instaladas (`node_modules`, `vendor`, un entorno virtual), el motor las instala o enlaza al crear el worktree (ver `engine.md`, paso 1).

## Cómo comprobar que `worktree_test_command` prueba el worktree

En `setup-project` no hay worktree todavía: verifica la sintaxis ejecutándolo con `{worktree}` igual a la ruta del clon principal. En la primera corrida, el motor confirma que prueba el worktree (ver `engine.md`, paso 2).
