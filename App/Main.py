import json
import os
import time
from app.metrics import registrar_hit, registrar_latencia, registrar_miss
from app.scraper import (
    obtener_q1_proximos_partidos,
    obtener_q2_ultimos_partidos,
    obtener_q3_historial,
    obtener_q4_periodo,
    obtener_q5_tabla_posiciones,
)
from fastapi import FastAPI, HTTPException
import redis

app = FastAPI(
    title="Plataforma de Futbol Chileno - All you can Cache", version="1.0"
)

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True,
)

TTL_SEGUNDOS = int(os.getenv("TTL_SEGUNDOS", 300))


@app.get("/q1/{equipo}")
async def q1_proximos_partidos(equipo: str):
  start_time = time.perf_counter()
  equipo_norm = equipo.strip().lower()
  cache_key = f"q1:{equipo_norm}"

  try:
    cached_data = r.get(cache_key)
    if cached_data:
      latencia = (time.perf_counter() - start_time) * 1000
      registrar_hit()
      registrar_latencia(latencia)
      return {
          "origen": "CACHE (Hit)",
          "tiempo_ms": round(latencia, 2),
          "datos": json.loads(cached_data),
      }
  except redis.RedisError:
    pass

  try:
    datos = await obtener_q1_proximos_partidos(equipo_norm)
    if not datos:
      raise HTTPException(
          status_code=404, detail="No se encontraron datos para el equipo"
      )

    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    latencia = (time.perf_counter() - start_time) * 1000
    registrar_miss()
    registrar_latencia(latencia)
    return {
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latencia, 2),
        "datos": datos,
    }
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(
        status_code=503, detail=f"Error al obtener datos del scraper: {str(e)}"
    )


@app.get("/q2/{equipo}")
async def q2_ultimos_partidos(equipo: str):
  start_time = time.perf_counter()
  equipo_norm = equipo.strip().lower()
  cache_key = f"q2:{equipo_norm}"

  try:
    cached_data = r.get(cache_key)
    if cached_data:
      latencia = (time.perf_counter() - start_time) * 1000
      registrar_hit()
      registrar_latencia(latencia)
      return {
          "origen": "CACHE (Hit)",
          "tiempo_ms": round(latencia, 2),
          "datos": json.loads(cached_data),
      }
  except redis.RedisError:
    pass

  try:
    datos = await obtener_q2_ultimos_partidos(equipo_norm)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    latencia = (time.perf_counter() - start_time) * 1000
    registrar_miss()
    registrar_latencia(latencia)
    return {
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latencia, 2),
        "datos": datos,
    }
  except Exception as e:
    raise HTTPException(
        status_code=503, detail=f"Error en el scraper: {str(e)}"
    )


@app.get("/q3/{equipo1}/{equipo2}")
async def q3_historial_enfrentamientos(equipo1: str, equipo2: str):
  start_time = time.perf_counter()
  equipos = sorted([equipo1.strip().lower(), equipo2.strip().lower()])
  cache_key = f"q3:{equipos[0]}:vs:{equipos[1]}"

  try:
    cached_data = r.get(cache_key)
    if cached_data:
      latencia = (time.perf_counter() - start_time) * 1000
      registrar_hit()
      registrar_latencia(latencia)
      return {
          "origen": "CACHE (Hit)",
          "tiempo_ms": round(latencia, 2),
          "datos": json.loads(cached_data),
      }
  except redis.RedisError:
    pass

  try:
    datos = await obtener_q3_historial(equipos[0], equipos[1])
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    latencia = (time.perf_counter() - start_time) * 1000
    registrar_miss()
    registrar_latencia(latencia)
    return {
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latencia, 2),
        "datos": datos,
    }
  except Exception as e:
    raise HTTPException(
        status_code=503, detail=f"Error en el scraper: {str(e)}"
    )


@app.get("/q4/{fecha_inicio}/{fecha_fin}")
async def q4_partidos_periodo(fecha_inicio: str, fecha_fin: str):
  start_time = time.perf_counter()
  cache_key = f"q4:{fecha_inicio.strip()}:{fecha_fin.strip()}"

  try:
    cached_data = r.get(cache_key)
    if cached_data:
      latencia = (time.perf_counter() - start_time) * 1000
      registrar_hit()
      registrar_latencia(latencia)
      return {
          "origen": "CACHE (Hit)",
          "tiempo_ms": round(latencia, 2),
          "datos": json.loads(cached_data),
      }
  except redis.RedisError:
    pass

  try:
    datos = await obtener_q4_periodo(fecha_inicio, fecha_fin)
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    latencia = (time.perf_counter() - start_time) * 1000
    registrar_miss()
    registrar_latencia(latencia)
    return {
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latencia, 2),
        "datos": datos,
    }
  except Exception as e:
    raise HTTPException(
        status_code=503, detail=f"Error en el scraper: {str(e)}"
    )


@app.get("/q5")
async def q5_tabla_posiciones():
  start_time = time.perf_counter()
  cache_key = "q5:tabla_posiciones"

  try:
    cached_data = r.get(cache_key)
    if cached_data:
      latencia = (time.perf_counter() - start_time) * 1000
      registrar_hit()
      registrar_latencia(latencia)
      return {
          "origen": "CACHE (Hit)",
          "tiempo_ms": round(latencia, 2),
          "datos": json.loads(cached_data),
      }
  except redis.RedisError:
    pass

  try:
    datos = await obtener_q5_tabla_posiciones()
    r.setex(cache_key, TTL_SEGUNDOS, json.dumps(datos))
    latencia = (time.perf_counter() - start_time) * 1000
    registrar_miss()
    registrar_latencia(latencia)
    return {
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latencia, 2),
        "datos": datos,
    }
  except Exception as e:
    raise HTTPException(
        status_code=503, detail=f"Error en el scraper: {str(e)}"
    )
  
