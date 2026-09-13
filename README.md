# Tarea 1 - Sistemas Distribuidos

Plataforma de consultas de la Liga de Primera de Chile con patrón **cache-aside**, Redis, scraper de Soccerway y generador de tráfico reproducible. No consulta una base de datos de fútbol durante la ejecución: los feeds más usados de Soccerway se precargan en memoria al iniciar y Redis conserva las respuestas de las consultas.

## Arquitectura

`Generador de tráfico -> API FastAPI -> Redis -> scraper Soccerway -> Redis -> respuesta`

- `app/main.py`: API, TTL por tipo de consulta y flujo hit/miss.
- `app/scraper.py`: consulta feeds públicos de Soccerway; la tabla usa Playwright porque Soccerway la genera con JavaScript.
- `app/metrics.py`: registra hits, misses, latencia, tiempo de scraping, throughput, errores, evicciones y expiraciones.
- `app/traffic_generator.py`: genera tráfico uniforme o Zipf con semilla, tasa de arribo, cantidad y tipos de consulta configurables.
- `docker-compose.yml`: API y Redis desacoplados, con límite de memoria y política de reemplazo configurables.

## Ejecutar con Docker

```powershell
docker compose up --build
```

La API queda disponible en `http://localhost:8000`. Comprueba el estado con:

```powershell
curl.exe http://localhost:8000/health
```

Consultas disponibles:

```text
GET /q1/{equipo}                       Próximos partidos
GET /q2/{equipo}                       Últimos partidos
GET /q3/{equipo1}/{equipo2}            Historial entre equipos
GET /q4/{fecha_inicio}/{fecha_fin}     Partidos en un período YYYY-MM-DD
GET /q5                                Tabla de posiciones
GET /metrics                           Métricas acumuladas
```

Ejemplos:

```powershell
curl.exe http://localhost:8000/q1/colo-colo
curl.exe http://localhost:8000/q2/universidad-de-chile
curl.exe http://localhost:8000/q3/colo-colo/universidad-de-chile
curl.exe http://localhost:8000/q4/2026-08-01/2026-08-31
curl.exe http://localhost:8000/q5
curl.exe http://localhost:8000/metrics
```

## Configuración experimental

Redis parte con 2 MB y LRU. Antes de levantar el sistema puedes cambiar capacidad, política y TTL por tipo de consulta:

```powershell
$env:REDIS_MAXMEMORY = "5mb"                 # 2mb, 5mb o 10mb
$env:REDIS_MAXMEMORY_POLICY = "allkeys-lfu"  # allkeys-lru o allkeys-lfu
$env:CACHE_TTL_Q1 = "300"                    # proximos partidos: dato dinamico
$env:CACHE_TTL_Q2 = "3600"                   # historial reciente: cambia menos
$env:CACHE_TTL_Q3 = "3600"                   # enfrentamientos historicos
$env:CACHE_TTL_Q4 = "1800"                   # consultas por periodo
$env:CACHE_TTL_Q5 = "180"                    # tabla de posiciones: dato dinamico
docker compose up --build
```

Para una comparación limpia, detén el entorno, cambia una sola variable por vez y vuelve a iniciarlo. Compara al menos las capacidades 2 MB, 5 MB y 10 MB, y las políticas `allkeys-lru` y `allkeys-lfu`.

Para reiniciar solo la caché y las métricas antes de una corrida controlada, sin recrear los contenedores:

```powershell
curl.exe -X POST "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
```

Reemplaza `allkeys-lru` por `allkeys-lfu` para la otra política. Esta ruta se usa únicamente durante las pruebas y deja Redis con caché fría.

Para aislar el efecto del TTL sin reconstruir los contenedores, se puede cambiar
temporalmente el TTL de una consulta durante la corrida:

```powershell
curl.exe -X POST "http://localhost:8000/experiments/ttl?query=q2&seconds=5"
```

Después de la prueba se debe restaurar el valor normal de Q2:

```powershell
curl.exe -X POST "http://localhost:8000/experiments/ttl?query=q2&seconds=3600"
```

## Generador de tráfico

Desde otra terminal, con los contenedores arriba. Estas son las cuatro corridas
reproducibles de la comparacion inicial: 2 MB, semilla 42, 100 solicitudes,
20 rps y consultas Q1/Q2.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution uniform --requests 100 --arrival-rate 20 --queries q1,q2 --seed 42

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution zipf --zipf-alpha 1.5 --requests 100 --arrival-rate 20 --queries q1,q2 --seed 42

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lfu&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution uniform --requests 100 --arrival-rate 20 --queries q1,q2 --seed 42

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lfu&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution zipf --zipf-alpha 1.5 --requests 100 --arrival-rate 20 --queries q1,q2 --seed 42
```

El resultado se imprime como JSON para que puedas copiarlo a una tabla o gráfico del informe. Conserva la misma semilla, número de solicitudes y tasa de arribo cuando compares distribuciones. Usa `--verbose` si quieres mostrar cada petición durante el video.

## Guion de video coherente con la pauta

Usa PowerShell y ejecuta los bloques en este orden. Las corridas breves con
`--verbose` sirven para mostrar el funcionamiento; no se deben presentar como
los numeros de las tablas, que usan una carga controlada mayor.

### 1. Levantar API y Redis

```powershell
Set-Location "C:\Users\cvale\OneDrive\Desktop\Tarea 1 Sistemas Distribuidos"
docker compose up -d --build
Start-Sleep -Seconds 10
docker compose ps
docker compose logs --tail=20 api
Invoke-RestMethod -Uri "http://localhost:8000/health" | Select-Object api, redis, preload, ttl_por_consulta | Format-List
```

### 2. Consultas Q1 a Q5 con datos reales

Primero se deja Redis frio. Muestra `SCRAPER (Miss)` y la lista de datos con
`fuente_origen`, que identifica Soccerway.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"

$q1 = Invoke-RestMethod -Uri "http://localhost:8000/q1/colo-colo"
$q1 | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$q1.datos.partidos | Select-Object -First 3 fecha, hora, local, visitante, ronda, fuente_origen | Format-Table -AutoSize

$q2 = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
$q2 | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$q2.datos.resultados | Select-Object -First 3 fecha, local, visitante, resultado, ronda, fuente_origen | Format-Table -AutoSize

$q3 = Invoke-RestMethod -Uri "http://localhost:8000/q3/colo-colo/universidad-de-chile"
$q3 | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$q3.datos.detalle | Select-Object -First 5 fecha, local, visitante, resultado, fuente_origen | Format-Table -AutoSize

$q4 = Invoke-RestMethod -Uri "http://localhost:8000/q4/2026-08-01/2026-08-31"
$q4 | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$q4.datos.partidos | Select-Object -First 5 fecha, hora, local, visitante, resultado, fuente_origen | Format-Table -AutoSize

$q5 = Invoke-RestMethod -Uri "http://localhost:8000/q5"
$q5 | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$q5.datos.posiciones | Select-Object -First 5 posicion, equipo, partidos_jugados, ganados, empatados, perdidos, puntos | Format-Table -AutoSize
$q5.datos.fuente_origen
```

### 3. Mostrar cache-aside y metricas

La primera Q2 debe ser `SCRAPER (Miss)` y la segunda `CACHE (Hit)`.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
$miss = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
$hit = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
$miss | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$hit | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
Invoke-RestMethod -Uri "http://localhost:8000/metrics" | ConvertTo-Json -Depth 5
```

### 4. Trafico Uniforme y Zipf

Esta es una muestra visual corta. Para repetir la corrida documentada se usan
100 solicitudes, 20 rps, semilla 42 y sin `--verbose`.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution uniform --requests 20 --arrival-rate 5 --queries q1,q2 --seed 42 --verbose

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
docker compose exec api python -m app.traffic_generator --distribution zipf --zipf-alpha 1.5 --requests 20 --arrival-rate 5 --queries q1,q2 --seed 42 --verbose
```

### 5. Cambiar capacidad y politica de Redis

Cada cambio limpia la cache y las metricas de la nueva corrida. Muestra los tres
tamanos exigidos y comprueba la configuracion activa desde Redis.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
docker compose exec redis redis-cli CONFIG GET maxmemory
docker compose exec redis redis-cli CONFIG GET maxmemory-policy

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=5mb"
docker compose exec redis redis-cli CONFIG GET maxmemory
docker compose exec redis redis-cli CONFIG GET maxmemory-policy

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=10mb"
docker compose exec redis redis-cli CONFIG GET maxmemory
docker compose exec redis redis-cli CONFIG GET maxmemory-policy

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lfu&maxmemory=10mb"
docker compose exec redis redis-cli CONFIG GET maxmemory-policy
```

La carga de presion documentada para 10 MB uso 900 solicitudes Q4, 235 claves
distintas, LRU, Zipf con alpha 1.1, semilla 42 y 2 rps. No conviene repetirla
en vivo: toma varios minutos. Muestra sus resultados desde el informe y explica
que no hubo evicciones bajo esa carga, a diferencia de 2 MB y 5 MB.

### 6. Cambiar TTL y observar una expiracion

La primera Q2 debe ser miss, la segunda hit y la tercera miss despues de superar
el TTL de cinco segundos. Al final se restaura el TTL normal y 2 MB.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/ttl?query=q2&seconds=5"
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
$primera = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
Start-Sleep -Seconds 2
$segunda = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
Start-Sleep -Seconds 4
$tercera = Invoke-RestMethod -Uri "http://localhost:8000/q2/everton"
$primera | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$segunda | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
$tercera | Select-Object consulta, origen, tiempo_ms, scraping_ms, cache_ttl_segundos | Format-List
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/ttl?query=q2&seconds=3600"
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/experiments/reset?policy=allkeys-lru&maxmemory=2mb"
```

## Métricas para el informe

`/metrics` expone:

- hits, misses, hit rate y cache efficiency;
- latencia p50 y p95;
- promedio, p50 y p95 del tiempo de scraping;
- throughput de la ventana reciente observada (hasta 60 segundos);
- error rate;
- evicted keys, expired keys y eviction rate de Redis.

El generador entrega además el resumen de cada corrida. Para el análisis, explica por qué Zipf suele concentrar accesos en pocas claves y mejorar el hit rate, mientras que una distribución uniforme ejerce más presión sobre una caché pequeña. Relaciona cada cambio de tamaño, política o TTL con sus efectos observados en hits, latencia, expiraciones y evicciones.

## Manejo de fallos

Si Soccerway no responde, la API devuelve `503` y registra el error sin detener el servicio. Si no existe información para una consulta válida, devuelve `404`. Si Redis falla temporalmente, la API intenta responder desde el scraper en vez de interrumpir todo el flujo.
