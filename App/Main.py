from fastapi import FastAPI
import redis
import json
import time

app = FastAPI(title="API Futbol Chileno - Sistema de Cache")

#Conexion a Redis local
cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def scraper_obtener_proximos_partidos(team_id: str):
    # Simula la latencia del scraper
    time.sleep(2)
    return {
        "equipo": team_id,
        "proximo_partido": "Universidad de Chile vs Colo-Colo",
        "fecha": "2026-10-15",
        "hora": "15:00"
    }

@app.get("/")
def leer_raiz():
    return {"mensaje": "Bienvenido a la API del Futbol Chileno"}

@app.get("/q1/{team_id}")
def consulta_q1(team_id: str):
    cache_key = f"q1:team:{team_id}"

#Busca en cache
    cached_data = cache.get(cache_key)

    if cached_data:
        return {
            "origen": "CACHE (Hit)",
            "datos": json.loads(cached_data)
        }

    print(f"Cache miss para {team_id}. Consultando datos...")

#Obtiene datos nuevos
    nueva_data = scraper_obtener_proximos_partidos(team_id)

#Guarda en cache con TTL de 60 segundos
    cache.setex(name=cache_key, time=60, value=json.dumps(nueva_data))

    return {
        "origen": "SCRAPER (Miss)",
        "datos": nueva_data
    }