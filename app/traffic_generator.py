"""Generador reproducible de trafico uniforme y Zipf para la API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any

import httpx
import numpy as np


DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")
EQUIPOS = [
    "colo-colo",
    "universidad-de-chile",
    "universidad-catolica",
    "coquimbo",
    "deportes-concepcion",
    "universidad-de-concepcion",
    "palestino",
    "everton",
    "limache",
    "audax",
    "nublense",
    "cobresal",
    "huachipato",
    "la-serena",
    "o-higgins",
    "union-la-calera",
]
VALID_QUERIES = {"q1", "q2", "q3", "q4", "q5"}


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = (len(ordered) - 1) * percentile / 100
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 2)


def _sample_team_index(
    generator: np.random.Generator,
    distribution: str,
    zipf_alpha: float,
) -> int:
    if distribution == "uniform":
        return int(generator.integers(0, len(EQUIPOS)))
    while True:
        index = int(generator.zipf(zipf_alpha)) - 1
        if index < len(EQUIPOS):
            return index


def generar_endpoint(
    request_number: int,
    generator: np.random.Generator,
    distribution: str,
    zipf_alpha: float,
    queries: list[str],
) -> str:
    """Arma una consulta usando la distribucion elegida para las claves de cache."""
    query = queries[(request_number - 1) % len(queries)]
    first_index = _sample_team_index(generator, distribution, zipf_alpha)
    second_index = _sample_team_index(generator, distribution, zipf_alpha)
    if first_index == second_index:
        second_index = (second_index + 1) % len(EQUIPOS)
    first, second = EQUIPOS[first_index], EQUIPOS[second_index]

    if query == "q1":
        return f"/q1/{first}"
    if query == "q2":
        return f"/q2/{first}"
    if query == "q3":
        return f"/q3/{first}/{second}"
    if query == "q4":
        month = ((request_number - 1) % 12) + 1
        return f"/q4/2026-{month:02d}-01/2026-{month:02d}-28"
    return "/q5"


async def _snapshot_metrics(client: httpx.AsyncClient, api_url: str) -> dict[str, Any]:
    try:
        response = await client.get(f"{api_url}/metrics")
        return response.json() if response.is_success else {}
    except (httpx.HTTPError, ValueError):
        return {}


async def ejecutar_prueba(
    *,
    distribution: str = "zipf",
    total_requests: int = 500,
    zipf_alpha: float = 1.5,
    arrival_rate: float = 100.0,
    queries: list[str] | None = None,
    seed: int = 42,
    api_url: str = DEFAULT_API_URL,
    verbose: bool = False,
) -> dict[str, Any]:
    """Corre una prueba y entrega numeros listos para el informe."""
    if total_requests <= 0:
        raise ValueError("El número de solicitudes debe ser mayor que cero.")
    if distribution not in {"uniform", "zipf"}:
        raise ValueError("La distribución debe ser 'uniform' o 'zipf'.")
    if distribution == "zipf" and zipf_alpha <= 1:
        raise ValueError("El parámetro alpha de Zipf debe ser mayor que 1.")
    if arrival_rate < 0:
        raise ValueError("La tasa de arribo no puede ser negativa.")

    selected_queries = queries or ["q1", "q2", "q3"]
    invalid_queries = set(selected_queries) - VALID_QUERIES
    if invalid_queries:
        raise ValueError(f"Consultas no válidas: {', '.join(sorted(invalid_queries))}")

    api_url = api_url.rstrip("/")
    generator = np.random.default_rng(seed)
    latencies: list[float] = []
    hits = misses = successes = errors = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        metrics_before = await _snapshot_metrics(client, api_url)
        started_at = time.perf_counter()
        next_arrival = started_at

        for request_number in range(1, total_requests + 1):
            endpoint = generar_endpoint(
                request_number,
                generator,
                distribution,
                zipf_alpha,
                selected_queries,
            )
            request_started = time.perf_counter()
            try:
                response = await client.get(f"{api_url}{endpoint}")
                latency_ms = (time.perf_counter() - request_started) * 1000
                latencies.append(latency_ms)
                if response.is_success:
                    successes += 1
                    origin = response.json().get("origen", "")
                    if "Hit" in origin:
                        hits += 1
                    elif "Miss" in origin:
                        misses += 1
                    if verbose:
                        print(f"[{request_number:04d}] {endpoint:<42} {latency_ms:>8.2f} ms | {origin}")
                else:
                    errors += 1
                    if verbose:
                        print(f"[{request_number:04d}] {endpoint:<42} HTTP {response.status_code}")
            except httpx.HTTPError as exc:
                errors += 1
                if verbose:
                    print(f"[{request_number:04d}] {endpoint:<42} ERROR {exc}")

            if arrival_rate:
                next_arrival += 1 / arrival_rate
                await asyncio.sleep(max(0, next_arrival - time.perf_counter()))

        elapsed_seconds = time.perf_counter() - started_at
        metrics_after = await _snapshot_metrics(client, api_url)

    redis_before = metrics_before.get("redis", {})
    redis_after = metrics_after.get("redis", {})
    evicted = max(0, int(redis_after.get("evicted_keys", 0)) - int(redis_before.get("evicted_keys", 0)))
    expired = max(0, int(redis_after.get("expired_keys", 0)) - int(redis_before.get("expired_keys", 0)))
    cache_requests = hits + misses

    return {
        "distribucion": distribution,
        "seed": seed,
        "zipf_alpha": zipf_alpha if distribution == "zipf" else None,
        "tasa_arribo_objetivo_rps": arrival_rate,
        "consultas": selected_queries,
        "solicitudes_totales": total_requests,
        "exitos": successes,
        "errores": errors,
        "error_rate_pct": round((errors / total_requests) * 100, 2),
        "hits": hits,
        "misses": misses,
        "hit_rate_pct": round((hits / cache_requests) * 100, 2) if cache_requests else 0.0,
        "cache_efficiency_pct": round((hits / cache_requests) * 100, 2) if cache_requests else 0.0,
        "throughput_rps": round(total_requests / elapsed_seconds, 2) if elapsed_seconds else 0.0,
        "latencia_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "promedio": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        },
        "evicted_keys": evicted,
        "expired_keys": expired,
        "eviction_rate_pct": round((evicted / total_requests) * 100, 2),
    }


def _parse_queries(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba reproducible de caché para Sistemas Distribuidos.")
    parser.add_argument("--distribution", choices=("uniform", "zipf"), default="zipf")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--arrival-rate", type=float, default=100.0, help="Solicitudes por segundo; 0 ejecuta sin pausa.")
    parser.add_argument("--zipf-alpha", type=float, default=1.5)
    parser.add_argument("--queries", default="q1,q2,q3", help="Lista separada por comas: q1,q2,q3,q4,q5.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(
        ejecutar_prueba(
            distribution=args.distribution,
            total_requests=args.requests,
            arrival_rate=args.arrival_rate,
            zipf_alpha=args.zipf_alpha,
            queries=_parse_queries(args.queries),
            seed=args.seed,
            api_url=args.api_url,
            verbose=args.verbose,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
