import asyncio
import time
import httpx
import numpy as np
import subprocess

# Configuracion de URL y espacio de datos
API_URL = "http://localhost:8000"
EQUIPOS = [
    "colo-colo",
    "universidad-de-chile",
    "universidad-catolica",
    "coquimbo-unido",
    "deportes-iquique",
    "palestino",
    "union-espanola",
    "everton",
    "universidad-de-concepcion",
    "audax-italiano",
    "nublense",
    "cobresal",
    "huachipato",
    "cobreloa",
    "deportes-copiapo",
    "union-la-calera",
]


def obtener_metricas_redis():
    try:
        cmd = ["docker", "exec", "tarea1sistemasdistribuidos-redis-1", "redis-cli", "info", "stats"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stats = {}
        for line in res.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                stats[k.strip()] = v.strip()
        return int(stats.get("evicted_keys", 0)), int(stats.get("expired_keys", 0))
    except Exception:
        return 0, 0


def generar_endpoint(
    step,
    distribucion="zipf",
    zipf_param=1.5,
    tipos_consulta=None,
):
  """Genera endpoints variados (Q1-Q5) según la distribución seleccionada."""
  if tipos_consulta is None:
    tipos_consulta = ["q1", "q2", "q3", "q4", "q5"]

  # Seleccion del tipo de consulta 
  q_type = tipos_consulta[step % len(tipos_consulta)]

  # Seleccion de indices segun la distribución solicitada
  if distribucion == "zipf":
    idx1 = (np.random.zipf(a=zipf_param) - 1) % len(EQUIPOS)
    idx2 = (np.random.zipf(a=zipf_param) - 1) % len(EQUIPOS)
  else:
    idx1 = np.random.randint(0, len(EQUIPOS))
    idx2 = np.random.randint(0, len(EQUIPOS))

  # Asegurar que dos equipos no sean identicos para Q3
  if idx1 == idx2:
    idx2 = (idx1 + 1) % len(EQUIPOS)

  eq1 = EQUIPOS[idx1]
  eq2 = EQUIPOS[idx2]

  # Construccion del endpoint 
  if q_type == "q1":
    return f"/q1/{eq1}"
  elif q_type == "q2":
    return f"/q2/{eq1}"
  elif q_type == "q3":
    return f"/q3/{eq1}/{eq2}"
  elif q_type == "q4":
    mes = (step % 12) + 1
    return f"/q4/2024-{mes:02d}-01/2024-{mes:02d}-28"
  elif q_type == "q5":
    return "/q5"
  else:
    return f"/q1/{eq1}"


async def ejecutar_prueba(
    distribucion="zipf",
    total_requests=150,
    zipf_param=1.5,
    tasa_arribo_delay=0.05,
    tipos_consulta=None,
    seed=42,
):
  """Ejecuta la simulacion de trafico configurable y reproducible."""
  if seed is not None:
    np.random.seed(seed)

  if tipos_consulta is None:
    tipos_consulta = ["q1", "q2", "q3", "q4", "q5"]

  latencias = []
  hits = 0
  misses = 0
  exitos = 0
  fallos = 0

  print(
      f"\n--- Ejecutando Simulación ({distribucion.upper()}) | Consultas:"
      f" {tipos_consulta} ---"
  )
  start_total = time.perf_counter()

  async with httpx.AsyncClient(timeout=15.0) as client:
    for i in range(1, total_requests + 1):
      endpoint = generar_endpoint(
          step=i,
          distribucion=distribucion,
          zipf_param=zipf_param,
          tipos_consulta=tipos_consulta,
      )

      t0 = time.perf_counter()
      try:
        res = await client.get(f"{API_URL}{endpoint}")
        t1 = time.perf_counter()
        latencia_ms = (t1 - t0) * 1000
        latencias.append(latencia_ms)

        if res.status_code == 200:
          exitos += 1
          data = res.json()
          origen = data.get("origen", "")

          if "Hit" in origen:
            hits += 1
          else:
            misses += 1

          print(
              f"[{i:03d}] {endpoint:<38} | {latencia_ms:>7.2f} ms | Origen:"
              f" {origen}"
          )
        else:
          fallos += 1
          print(f"[{i:03d}] {endpoint:<38} | HTTP Error {res.status_code}")

      except Exception as e:
        fallos += 1
        print(f"[{i:03d}] {endpoint:<38} | Error: {e}")

      await asyncio.sleep(tasa_arribo_delay)

  total_time = time.perf_counter() - start_total
  qps = total_requests / total_time
  hit_rate = (hits / total_requests) * 100 if total_requests > 0 else 0.0
  evicted_keys, expired_keys = obtener_metricas_redis()
  eviction_rate = (evicted_keys / total_requests) * 100 if total_requests > 0 else 0.0

  print("\n================================================================")
  print(" RESUMEN DE MÉTRICAS DE RENDIMIENTO (GENERADOR DE TRÁFICO)")
  print("================================================================")
  print(f" Distribución Evaluada : {distribucion.upper()}")
  print(f" Consultas Evaluadas   : {tipos_consulta}")
  print(
      f" Solicitudes Totales   : {total_requests} (Éxito: {exitos}, Fallos:"
      f" {fallos})"
  )
  print(f" Cache Hits            : {hits}")
  print(f" Cache Misses          : {misses}")
  print(f" Hit Rate (%)          : {hit_rate:.2f}%")
  print(f" Claves Evictadas (LRU): {evicted_keys}")
  print(f" Claves Expiradas (TTL): {expired_keys}")
  print(f" Tasa de Evicción (%)  : {eviction_rate:.2f}%")
  print(f" Tiempo Total Prueba   : {total_time:.2f} segundos")
  print(f" Throughput (QPS/RPS)  : {qps:.2f} req/seg")
  print(
      f" Latencia Mínima       : {min(latencias):.2f} ms"
      if latencias
      else "N/A"
  )
  print(
      f" Latencia Promedio     : {np.mean(latencias):.2f} ms"
      if latencias
      else "N/A"
  )
  print(
      f" Latencia p50 (Mediana): {np.percentile(latencias, 50):.2f} ms"
      if latencias
      else "N/A"
  )
  print(
      f" Latencia p95          : {np.percentile(latencias, 95):.2f} ms"
      if latencias
      else "N/A"
  )
  print(
      f" Latencia Máxima       : {max(latencias):.2f} ms"
      if latencias
      else "N/A"
  )
  print("================================================================\n")


if __name__ == "__main__":
  

  #Prueba de capacidad con todas las consultas Q1-Q5:
  asyncio.run(

      ejecutar_prueba(
          distribucion="zipf",
          total_requests=30000,
          tipos_consulta=["q1", "q2", "q3", "q4", "q5"],
          tasa_arribo_delay=0.03,
      )
  )
#para 1 sola consulta q1  
# asyncio.run(ejecutar_prueba(distribucion="uniforme", total_requests=100, tipos_consulta=["q1"]))
