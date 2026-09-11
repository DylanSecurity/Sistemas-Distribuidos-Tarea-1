import time
import json
import redis
from fastapi import FastAPI
from app.scraper import (
    obtener_q1_proximos_partidos,
    obtener_q2_ultimos_partidos,
    obtener_q3_historial,
    obtener_q4_periodo,
    obtener_q5_tabla_posiciones
)
from app.metrics import registrar_hit, registrar_miss, registrar_latencia

app = FastAPI(title="Plataforma de Futbol Chileno - All you can Cache", version="1.0")

import os
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, db=0, decode_responses=True)

TTL_SEGUNDOS = 60
@app.get("/q1/{equipo}")
async def q1_proximos_partidos(equipo: str):
    start_time = time.time()
    cache_key = f"q1:{equipo.lower()}"
    cached_data = r.get(cache_key)
    
    if cached_data:
        registrar_hit()
        latencia = (time.time() - start_time) * 1000
        registrar_latencia(latencia)
        return {"origen": "CACHE (Hit)", "datos": json.loads(cached_data)}
    
    datos = await obtener_q1_proximos_partidos(equipo)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    
    registrar_miss()
    latencia = (time.time() - start_time) * 1000
    registrar_latencia(latencia)
    return {"origen": "SCRAPER (Miss)", "datos": datos}

@app.get("/q2/{equipo}")
async def q2_ultimos_partidos(equipo: str):
    start_time = time.time()
    cache_key = f"q2:{equipo.lower()}"
    cached_data = r.get(cache_key)
    
    if cached_data:
        registrar_hit()
        latencia = (time.time() - start_time) * 1000
        registrar_latencia(latencia)
        return {"origen": "CACHE (Hit)", "datos": json.loads(cached_data)}
    
    datos = await obtener_q2_ultimos_partidos(equipo)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    
    registrar_miss()
    latencia = (time.time() - start_time) * 1000
    registrar_latencia(latencia)
    return {"origen": "SCRAPER (Miss)", "datos": datos}

@app.get("/q3/{equipo1}/{equipo2}")
async def q3_historial_enfrentamientos(equipo1: str, equipo2: str):
    start_time = time.time()
    
    equipos = sorted([equipo1.lower(), equipo2.lower()])
    cache_key = f"q3:{equipos[0]}:vs:{equipos[1]}"
    
    cached_data = r.get(cache_key)
    if cached_data:
        registrar_hit()
        latencia = (time.time() - start_time) * 1000
        registrar_latencia(latencia)
        return {"origen": "CACHE (Hit)", "datos": json.loads(cached_data)}
    
    datos = await obtener_q3_historial(equipo1, equipo2)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    
    registrar_miss()
    latencia = (time.time() - start_time) * 1000
    registrar_latencia(latencia)
    return {"origen": "SCRAPER (Miss)", "datos": datos}

@app.get("/q4/{fecha_inicio}/{fecha_fin}")
async def q4_partidos_periodo(fecha_inicio: str, fecha_fin: str):
    start_time = time.time()
    cache_key = f"q4:{fecha_inicio}:{fecha_fin}"
    cached_data = r.get(cache_key)
    
    if cached_data:
        registrar_hit()
        latencia = (time.time() - start_time) * 1000
        registrar_latencia(latencia)
        return {"origen": "CACHE (Hit)", "datos": json.loads(cached_data)}
    
    datos = await obtener_q4_periodo(fecha_inicio, fecha_fin)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    
    registrar_miss()
    latencia = (time.time() - start_time) * 1000
    registrar_latencia(latencia)
    return {"origen": "SCRAPER (Miss)", "datos": datos}

@app.get("/q5")
async def q5_tabla_posiciones():
    start_time = time.time()
    cache_key = "q5:tabla_posiciones"
    cached_data = r.get(cache_key)
    
    if cached_data:
        registrar_hit()
        latencia = (time.time() - start_time) * 1000
        registrar_latencia(latencia)
        return {"origen": "CACHE (Hit)", "datos": json.loads(cached_data)}
    
    datos = await obtener_q5_tabla_posiciones()
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    
    registrar_miss()
    latencia = (time.time() - start_time) * 1000
    registrar_latencia(latencia)
    return {"origen": "SCRAPER (Miss)", "datos": datos}
