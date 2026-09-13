"""API de la Tarea 1 con cache-aside, Redis y Soccerway."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
import redis.asyncio as redis

from app.metrics import obtener_metricas, registrar_consulta
from app.scraper import (
    ScraperError,
    normalizar_equipo,
    obtener_q1_proximos_partidos,
    obtener_q2_ultimos_partidos,
    obtener_q3_historial,
    obtener_q4_periodo,
    obtener_q5_tabla_posiciones,
    precargar_datos,
)


r: redis.Redis | None = None

TTL_BY_QUERY = {
    "q1": int(os.getenv("CACHE_TTL_Q1", "300")),
    "q2": int(os.getenv("CACHE_TTL_Q2", "3600")),
    "q3": int(os.getenv("CACHE_TTL_Q3", "3600")),
    "q4": int(os.getenv("CACHE_TTL_Q4", "1800")),
    "q5": int(os.getenv("CACHE_TTL_Q5", "180")),
}
EXPERIMENT_POLICIES = {"allkeys-lru", "allkeys-lfu"}
MEMORY_LIMIT_PATTERN = re.compile(r"^\d+(kb|mb|gb)$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Conecta Redis y deja los feeds mas usados listos en memoria."""
    global r
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=0,
        decode_responses=True,
    )
    try:
        await r.ping()
        app.state.redis_available = True
    except redis.RedisError:
        # Si Redis cae, igual intentamos responder con el scraper.
        app.state.redis_available = False

    app.state.preload = await precargar_datos()
    yield
    if r is not None:
        await r.aclose()


app = FastAPI(
    title="Plataforma de Fútbol Chileno - All you can Cache",
    version="1.1",
    description="Cache-aside con Redis, scraper de Soccerway y métricas experimentales.",
    lifespan=lifespan,
)


def _redis_client() -> redis.Redis:
    if r is None:
        raise HTTPException(status_code=503, detail="Redis todavía no está inicializado.")
    return r


async def _registrar(
    client: redis.Redis,
    cache_hit: bool | None,
    started_at: float,
    scraping_ms: float = 0.0,
    error: bool = False,
) -> float:
    latency_ms = (time.perf_counter() - started_at) * 1000
    await registrar_consulta(
        client,
        cache_hit=cache_hit,
        latencia_ms=latency_ms,
        scraping_ms=scraping_ms,
        error=error,
    )
    return latency_ms


async def _cache_aside(
    *,
    query: str,
    cache_key: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
    collection_key: str,
    not_found_message: str,
) -> dict[str, Any]:
    """Hace el flujo Redis -> scraper -> Redis y guarda las metricas."""
    client = _redis_client()
    started_at = time.perf_counter()

    try:
        cached = await client.get(cache_key)
        if cached:
            data = json.loads(cached)
            latency = await _registrar(client, True, started_at)
            return {
                "consulta": query.upper(),
                "origen": "CACHE (Hit)",
                "tiempo_ms": round(latency, 2),
                "cache_ttl_segundos": TTL_BY_QUERY[query],
                "datos": data,
            }
    except (redis.RedisError, json.JSONDecodeError):
        # Si Redis falla o trae un JSON malo, seguimos con el scraper.
        app.state.redis_available = False

    scraper_started_at = time.perf_counter()
    try:
        data = await loader()
        scraping_ms = (time.perf_counter() - scraper_started_at) * 1000
        if not data.get(collection_key):
            await _registrar(client, False, started_at, scraping_ms, error=True)
            raise HTTPException(status_code=404, detail=not_found_message)
    except HTTPException:
        raise
    except ValueError as exc:
        scraping_ms = (time.perf_counter() - scraper_started_at) * 1000
        await _registrar(client, False, started_at, scraping_ms, error=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ScraperError as exc:
        scraping_ms = (time.perf_counter() - scraper_started_at) * 1000
        await _registrar(client, False, started_at, scraping_ms, error=True)
        raise HTTPException(status_code=503, detail=f"Fuente externa no disponible: {exc}") from exc
    except Exception as exc:
        scraping_ms = (time.perf_counter() - scraper_started_at) * 1000
        await _registrar(client, False, started_at, scraping_ms, error=True)
        raise HTTPException(status_code=503, detail="Error inesperado al procesar la consulta.") from exc

    try:
        await client.set(cache_key, json.dumps(data, ensure_ascii=False), ex=TTL_BY_QUERY[query])
        app.state.redis_available = True
    except redis.RedisError:
        app.state.redis_available = False

    latency = await _registrar(client, False, started_at, scraping_ms)
    return {
        "consulta": query.upper(),
        "origen": "SCRAPER (Miss)",
        "tiempo_ms": round(latency, 2),
        "scraping_ms": round(scraping_ms, 2),
        "cache_ttl_segundos": TTL_BY_QUERY[query],
        "datos": data,
    }


@app.get("/")
async def inicio() -> dict[str, Any]:
    return {
        "servicio": app.title,
        "consultas": ["/q1/{equipo}", "/q2/{equipo}", "/q3/{equipo1}/{equipo2}", "/q4/{inicio}/{fin}", "/q5"],
        "metricas": "/metrics",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    client = _redis_client()
    try:
        await client.ping()
        redis_status = "ok"
        app.state.redis_available = True
    except redis.RedisError:
        redis_status = "unavailable"
        app.state.redis_available = False
    return {
        "api": "ok",
        "redis": redis_status,
        "preload": getattr(app.state, "preload", {}),
        "ttl_por_consulta": TTL_BY_QUERY,
    }


@app.post("/experiments/reset")
async def preparar_experimento(
    policy: str,
    maxmemory: str = "2mb",
) -> dict[str, str]:
    """Deja Redis listo para una corrida comparable."""
    policy = policy.lower().strip()
    memory_limit = maxmemory.lower().strip()
    if policy not in EXPERIMENT_POLICIES:
        raise HTTPException(status_code=400, detail="Politica no valida para el experimento.")
    if not MEMORY_LIMIT_PATTERN.fullmatch(memory_limit):
        raise HTTPException(status_code=400, detail="Use una capacidad como 2mb, 5mb o 10mb.")

    client = _redis_client()
    try:
        await client.flushdb()
        await client.config_set("maxmemory", memory_limit)
        await client.config_set("maxmemory-policy", policy)
        await client.execute_command("CONFIG", "RESETSTAT")
        app.state.redis_available = True
    except redis.RedisError as exc:
        app.state.redis_available = False
        raise HTTPException(status_code=503, detail="No se pudo preparar Redis.") from exc

    return {
        "estado": "listo",
        "politica": policy,
        "capacidad": memory_limit,
        "mensaje": "Cache y metricas reiniciadas para una nueva corrida.",
    }


@app.post("/experiments/ttl")
async def configurar_ttl_experimento(query: str, seconds: int) -> dict[str, Any]:
    """Cambia un TTL para una corrida controlada."""
    query = query.lower().strip()
    if query not in TTL_BY_QUERY:
        raise HTTPException(status_code=400, detail="Consulta no valida para TTL.")
    if not 1 <= seconds <= 86_400:
        raise HTTPException(status_code=400, detail="El TTL debe estar entre 1 y 86400 segundos.")

    previous = TTL_BY_QUERY[query]
    TTL_BY_QUERY[query] = seconds
    return {
        "estado": "listo",
        "consulta": query.upper(),
        "ttl_anterior_segundos": previous,
        "ttl_nuevo_segundos": seconds,
    }


@app.get("/metrics")
async def metricas() -> dict[str, Any]:
    try:
        return await obtener_metricas(_redis_client())
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="No se pueden leer métricas: Redis no está disponible.") from exc


@app.get("/q1/{equipo}")
async def q1_proximos_partidos(equipo: str) -> dict[str, Any]:
    equipo_norm = normalizar_equipo(equipo)
    return await _cache_aside(
        query="q1",
        cache_key=f"q1:{equipo_norm}",
        loader=lambda: obtener_q1_proximos_partidos(equipo),
        collection_key="partidos",
        not_found_message=f"No se encontraron próximos partidos para '{equipo}'.",
    )


@app.get("/q2/{equipo}")
async def q2_ultimos_partidos(equipo: str) -> dict[str, Any]:
    equipo_norm = normalizar_equipo(equipo)
    return await _cache_aside(
        query="q2",
        cache_key=f"q2:{equipo_norm}",
        loader=lambda: obtener_q2_ultimos_partidos(equipo),
        collection_key="resultados",
        not_found_message=f"No se encontraron últimos partidos para '{equipo}'.",
    )


@app.get("/q3/{equipo1}/{equipo2}")
async def q3_historial_enfrentamientos(equipo1: str, equipo2: str) -> dict[str, Any]:
    first, second = sorted((normalizar_equipo(equipo1), normalizar_equipo(equipo2)))
    return await _cache_aside(
        query="q3",
        cache_key=f"q3:{first}:vs:{second}",
        loader=lambda: obtener_q3_historial(equipo1, equipo2),
        collection_key="detalle",
        not_found_message=f"No se encontraron enfrentamientos entre '{equipo1}' y '{equipo2}'.",
    )


@app.get("/q4/{fecha_inicio}/{fecha_fin}")
async def q4_partidos_periodo(fecha_inicio: str, fecha_fin: str) -> dict[str, Any]:
    return await _cache_aside(
        query="q4",
        cache_key=f"q4:{fecha_inicio}:{fecha_fin}",
        loader=lambda: obtener_q4_periodo(fecha_inicio, fecha_fin),
        collection_key="partidos",
        not_found_message="No se encontraron partidos en el período indicado.",
    )


@app.get("/q5")
async def q5_tabla_posiciones() -> dict[str, Any]:
    return await _cache_aside(
        query="q5",
        cache_key="q5:tabla-posiciones",
        loader=obtener_q5_tabla_posiciones,
        collection_key="posiciones",
        not_found_message="Soccerway no entregó una tabla de posiciones.",
    )
