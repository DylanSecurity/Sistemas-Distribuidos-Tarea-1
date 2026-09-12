import asyncio
import time
import httpx
import numpy as np
import subprocess

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
    """Obtiene los contadores globales actuales del motor Redis."""
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


def obtener_indice_zipf(num_elementos, zipf_param=1.5):
    """Muestreo por rechazo para mantener la distribución Zipf pura en un espacio finito."""
    while True:
        idx = np.random.zipf(a=zipf_param) - 1
        if idx < num_elementos:
            return idx


def generar_endpoint(
    step,
    distribucion="zipf",
    zipf_param=1.5,
    tipos_consulta=None,
):
    if tipos_consulta is None:
        tipos_consulta = ["q1", "q2", "q3"]

    q_type = tipos_consulta[step % len(tipos_consulta)]

    if distribucion == "zipf":
        idx1 = obtener_indice_zipf(len(EQUIPOS), zipf_param)
        idx2 = obtener_indice_zipf(len(EQUIPOS), zipf_param)
    else:
        idx1 = np.random.randint(0, len(EQUIPOS))
        idx2 = np.random.randint(0, len(EQUIPOS))

    if idx1 == idx2:
        idx2 = (idx1 + 1) % len(EQUIPOS)

    eq1 = EQUIPOS[idx1]
    eq2 = EQUIPOS[idx2]

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
    total_requests=500,
    zipf_param=1.5,
    tasa_arribo_delay=0.01,
    tipos_consulta=None,
    seed=42,
):
    if seed is not None:
        np.random.seed(seed)

    if tipos_consulta is None:
        tipos_consulta = ["q1", "q2", "q3"]

    latencias = []
    hits = 0
    misses = 0
    exitos = 0
    fallos = 0

    # Captura de métricas iniciales de Redis para cálculo por diferencial
    evicted_inicial, expired_inicial = obtener_metricas_redis()

    print(f"\n--- Iniciando Prueba: {distribucion.upper()} | Solicitudes: {total_requests} ---")
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

                    print(f"[{i:04d}] {endpoint:<38} | {latencia_ms:>7.2f} ms | Origen: {origen}")
                else:
                    fallos += 1
                    print(f"[{i:04d}] {endpoint:<38} | HTTP Error {res.status_code}")

            except Exception as e:
                fallos += 1
                print(f"[{i:04d}] {endpoint:<38} | Error: {e}")

            await asyncio.sleep(tasa_arribo_delay)

    total_time = time.perf_counter() - start_total
    qps = total_requests / total_time
    
    # Hit rate calculado exclusivamente sobre peticiones exitosas procesadas por la caché
    hit_rate = (hits / exitos) * 100 if exitos > 0 else 0.0

    # Cálculo diferencial de evicciones y expiraciones en Redis
    evicted_final, expired_final = obtener_metricas_redis()
    evicted_keys = evicted_final - evicted_inicial
    expired_keys = expired_final - expired_inicial
    eviction_rate = (evicted_keys / total_requests) * 100 if total_requests > 0 else 0.0

    print("\n================================================================")
    print(" RESUMEN DE MÉTRICAS DE RENDIMIENTO ")
    print("================================================================")
    print(f" Distribución Evaluada : {distribucion.upper()}")
    print(f" Consultas Evaluadas   : {tipos_consulta}")
    print(f" Solicitudes Totales   : {total_requests} (Éxito: {exitos}, Fallos: {fallos})")
    print(f" Cache Hits            : {hits}")
    print(f" Cache Misses          : {misses}")
    print(f" Hit Rate (%)          : {hit_rate:.2f}%")
    print(f" Claves Evictadas      : {evicted_keys}")
    print(f" Claves Expiradas      : {expired_keys}")
    print(f" Tasa de Evicción (%)  : {eviction_rate:.2f}%")
    print(f" Tiempo Total Prueba   : {total_time:.2f} segundos")
    print(f" Throughput (QPS/RPS)  : {qps:.2f} req/seg")
    print(f" Latencia Mínima       : {min(latencias):.2f} ms" if latencias else "N/A")
    print(f" Latencia Promedio     : {np.mean(latencias):.2f} ms" if latencias else "N/A")
    print(f" Latencia p50 (Mediana): {np.percentile(latencias, 50):.2f} ms" if latencias else "N/A")
    print(f" Latencia p95          : {np.percentile(latencias, 95):.2f} ms" if latencias else "N/A")
    print(f" Latencia Máxima       : {max(latencias):.2f} ms" if latencias else "N/A")
    print("================================================================\n")


if __name__ == "__main__":
    # Ejecución de prueba recomendada para Uniforme vs. Zipf (sin distorsión de Q5)
    asyncio.run(
        ejecutar_prueba(
            distribucion="zipf",
            total_requests=500,
            tipos_consulta=["q1", "q2", "q3"],
            tasa_arribo_delay=0.01,
        )
    )
