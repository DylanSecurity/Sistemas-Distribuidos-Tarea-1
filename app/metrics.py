"""Registro de metricas reproducibles en Redis."""

from __future__ import annotations

import time
from typing import Any

import redis.asyncio as redis

PREFIX = "metricas"
MAX_SAMPLES = 2_000
WINDOW_SECONDS = 60
THROUGHPUT_KEY = f"{PREFIX}:throughput_timestamps"


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = (len(ordered) - 1) * percentile / 100
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    if lower == upper:
        return round(ordered[lower], 2)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 2)


async def registrar_consulta(
    client: redis.Redis,
    *,
    cache_hit: bool | None,
    latencia_ms: float,
    scraping_ms: float = 0.0,
    error: bool = False,
) -> None:
    """Guarda una muestra de cada consulta sin crecer sin limite."""
    try:
        pipeline = client.pipeline(transaction=False)
        pipeline.incr(f"{PREFIX}:solicitudes")
        if cache_hit is True:
            pipeline.incr(f"{PREFIX}:hits")
        elif cache_hit is False:
            pipeline.incr(f"{PREFIX}:misses")
        if error:
            pipeline.incr(f"{PREFIX}:errores")
        pipeline.lpush(f"{PREFIX}:latencias_ms", round(latencia_ms, 4))
        pipeline.ltrim(f"{PREFIX}:latencias_ms", 0, MAX_SAMPLES - 1)
        now = time.time()
        # Guardamos solo la ventana de throughput, sin depender de un limite fijo.
        pipeline.zadd(THROUGHPUT_KEY, {str(time.time_ns()): now})
        pipeline.zremrangebyscore(THROUGHPUT_KEY, 0, now - WINDOW_SECONDS)
        if scraping_ms:
            pipeline.incrbyfloat(f"{PREFIX}:scraping_total_ms", scraping_ms)
            pipeline.lpush(f"{PREFIX}:scraping_ms", round(scraping_ms, 4))
            pipeline.ltrim(f"{PREFIX}:scraping_ms", 0, MAX_SAMPLES - 1)
        await pipeline.execute()
    except redis.RedisError:
        # La API sigue funcionando aunque Redis se caiga un rato.
        return


async def obtener_metricas(client: redis.Redis) -> dict[str, Any]:
    """Entrega las metricas de la app y los datos que entrega Redis."""
    pipeline = client.pipeline(transaction=False)
    pipeline.get(f"{PREFIX}:solicitudes")
    pipeline.get(f"{PREFIX}:hits")
    pipeline.get(f"{PREFIX}:misses")
    pipeline.get(f"{PREFIX}:errores")
    pipeline.get(f"{PREFIX}:scraping_total_ms")
    pipeline.lrange(f"{PREFIX}:latencias_ms", 0, MAX_SAMPLES - 1)
    pipeline.lrange(f"{PREFIX}:scraping_ms", 0, MAX_SAMPLES - 1)
    now = time.time()
    pipeline.zrangebyscore(THROUGHPUT_KEY, now - WINDOW_SECONDS, "+inf", withscores=True)
    (
        requests,
        hits,
        misses,
        errors,
        scraping_total,
        latency_raw,
        scraper_raw,
        timestamp_raw,
    ) = await pipeline.execute()
    redis_stats = await client.info("stats")

    requests = int(requests or 0)
    hits, misses, errors = int(hits or 0), int(misses or 0), int(errors or 0)
    latencies = [float(value) for value in latency_raw]
    scraper_latencies = [float(value) for value in scraper_raw]
    recent_timestamps = [float(score) for _, score in timestamp_raw]
    if len(recent_timestamps) >= 2:
        observed_seconds = max(0.001, max(recent_timestamps) - min(recent_timestamps))
        throughput = len(recent_timestamps) / observed_seconds
    else:
        observed_seconds = 0.0
        throughput = 0.0
    cache_requests = hits + misses
    evicted = int(redis_stats.get("evicted_keys", 0))
    expired = int(redis_stats.get("expired_keys", 0))

    return {
        "solicitudes_totales": requests,
        "hits": hits,
        "misses": misses,
        "hit_rate_pct": round((hits / cache_requests) * 100, 2) if cache_requests else 0.0,
        "cache_efficiency_pct": round((hits / cache_requests) * 100, 2) if cache_requests else 0.0,
        "error_rate_pct": round((errors / requests) * 100, 2) if requests else 0.0,
        "throughput_rps_ventana_reciente": round(throughput, 3),
        "ventana_observada_segundos": round(observed_seconds, 3),
        "latencia_ms": {
            "muestras": len(latencies),
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        },
        "scraping_ms": {
            "muestras": len(scraper_latencies),
            "promedio": round(float(scraping_total or 0) / len(scraper_latencies), 2)
            if scraper_latencies
            else 0.0,
            "p50": _percentile(scraper_latencies, 50),
            "p95": _percentile(scraper_latencies, 95),
        },
        "redis": {
            "evicted_keys": evicted,
            "expired_keys": expired,
            "eviction_rate_pct": round((evicted / requests) * 100, 2) if requests else 0.0,
        },
    }
