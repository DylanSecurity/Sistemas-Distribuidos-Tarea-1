"""Busca datos publicos de Soccerway para la Liga de Primera de Chile.

Soccerway carga los partidos desde feeds de la liga. Este modulo los usa y los
deja en memoria mientras la app corre, sin una base de datos local.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

import httpx

try:
    from playwright.async_api import async_playwright
except ImportError:  # La imagen Docker incluye Playwright; esto mejora el error local.
    async_playwright = None


BASE_URL = "https://cl.soccerway.com"
CURRENT_SEASON = int(os.getenv("SOCCERWAY_CURRENT_SEASON", datetime.now().year))
HISTORY_SEASONS = int(os.getenv("SOCCERWAY_HISTORY_SEASONS", "2"))
REQUEST_TIMEOUT = float(os.getenv("SCRAPER_TIMEOUT_SECONDS", "20"))
USER_AGENT = "Mozilla/5.0 (compatible; SistemasDistribuidos/1.0)"

# Separadores que usa el feed de Soccerway.
FIELD_SEPARATOR = "\N{NOT SIGN}"
KEY_VALUE_SEPARATOR = "\N{DIVISION SIGN}"

_memory_cache: dict[tuple[int, str], list[dict[str, Any]]] = {}

TEAM_ALIASES = {
    "universidad-de-chile": "u-de-chile",
    "universidad-catolica": "u-catolica",
    "universidad-catolica-de-chile": "u-catolica",
    "deportes-concepcion": "dep-concepcion",
    "universidad-de-concepcion": "u-de-concepcion",
    "union-espanola": "u-espanola",
    "union-la-calera": "u-la-calera",
}


class ScraperError(RuntimeError):
    """Error que permite responder sin botar la API."""


def normalizar_equipo(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return TEAM_ALIASES.get(normalized, normalized)


def _season_path(year: int) -> str:
    suffix = "" if year == CURRENT_SEASON else f"-{year}"
    return f"/chile/liga-de-primera{suffix}"


def _page_url(year: int, view: str) -> str:
    return f"{BASE_URL}{_season_path(year)}/{view}/"


async def fetch_html(url: str) -> str:
    """Baja una pagina de Soccerway con un limite de espera."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-CL,es;q=0.9"},
            timeout=REQUEST_TIMEOUT,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        raise ScraperError(f"Soccerway no respondió correctamente: {exc}") from exc


def _extract_feed(html: str, feed_name: str) -> str:
    pattern = rf"cjs\.initialFeeds\[[\"']{re.escape(feed_name)}[\"']\]\s*=\s*\{{\s*data:\s*`(.*?)`"
    match = re.search(pattern, html, re.DOTALL)
    if not match or not match.group(1):
        raise ScraperError(f"Soccerway no entregó el feed '{feed_name}'.")
    return match.group(1)


def _parse_events(payload: str, source_url: str) -> list[dict[str, Any]]:
    """Pasa el feed compacto de Soccerway a partidos simples."""
    events: list[dict[str, Any]] = []
    field_pattern = rf"{FIELD_SEPARATOR}([A-Z]{{2,3}}){KEY_VALUE_SEPARATOR}"

    for chunk in payload.split("~AA")[1:]:
        pieces = re.split(field_pattern, chunk)
        fields: dict[str, list[str]] = {}
        for key, value in zip(pieces[1::2], pieces[2::2]):
            fields.setdefault(key, []).append(value)

        timestamp = fields.get("AD", [""])[0]
        home = fields.get("AE", [""])[0]
        away = fields.get("AF", [""])[0]
        if not (timestamp.isdigit() and home and away):
            continue

        events.append(
            {
                "id": pieces[0].lstrip(KEY_VALUE_SEPARATOR),
                "timestamp": int(timestamp),
                "local": home,
                "visitante": away,
                "local_slug": fields.get("WU", [normalizar_equipo(home)])[0],
                "visitante_slug": fields.get("WV", [normalizar_equipo(away)])[0],
                "goles_local": fields.get("AG", [None])[0],
                "goles_visitante": fields.get("AH", [None])[0],
                "ronda": fields.get("ER", [""])[0],
                "fuente_origen": source_url,
            }
        )
    return events


async def _load_events(
    year: int,
    feed_name: str,
    *,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    cache_key = (year, feed_name)
    if cache_key in _memory_cache and not refresh:
        return _memory_cache[cache_key]

    view = "partidos" if feed_name == "fixtures" else "resultados"
    source_url = _page_url(year, view)
    payload = _extract_feed(await fetch_html(source_url), feed_name)
    events = _parse_events(payload, source_url)
    if not events:
        raise ScraperError(f"El feed '{feed_name}' de Soccerway no contenía partidos.")

    _memory_cache[cache_key] = events
    return events


async def precargar_datos() -> dict[str, int]:
    """Carga los datos mas usados sin impedir que la API inicie."""
    requested = [
        (CURRENT_SEASON, "fixtures"),
        (CURRENT_SEASON, "results"),
        (CURRENT_SEASON - 1, "results"),
    ]
    results = await asyncio.gather(
        *(_load_events(year, feed) for year, feed in requested),
        return_exceptions=True,
    )
    return {
        f"{year}:{feed}": len(result) if isinstance(result, list) else 0
        for (year, feed), result in zip(requested, results)
    }


def _is_requested_team(event: dict[str, Any], team: str) -> bool:
    target = normalizar_equipo(team)
    candidates = {
        normalizar_equipo(event["local"]),
        normalizar_equipo(event["visitante"]),
        normalizar_equipo(event["local_slug"]),
        normalizar_equipo(event["visitante_slug"]),
    }
    return target in candidates


def _format_match(event: dict[str, Any], include_result: bool = False) -> dict[str, Any]:
    scheduled = datetime.fromtimestamp(event["timestamp"], timezone.utc)
    result = None
    if include_result and event["goles_local"] is not None and event["goles_visitante"] is not None:
        result = f"{event['goles_local']}-{event['goles_visitante']}"

    match: dict[str, Any] = {
        "fecha": scheduled.date().isoformat(),
        "hora": scheduled.strftime("%H:%M"),
        "zona_horaria": "UTC",
        "local": event["local"],
        "visitante": event["visitante"],
        "ronda": event["ronda"],
        "fuente_origen": event["fuente_origen"],
    }
    if include_result:
        match["resultado"] = result or "Pendiente"
    return match


async def obtener_q1_proximos_partidos(equipo: str) -> dict[str, Any]:
    now = time.time()
    # El cache de Redis vencio: renovamos la fuente antes de responder.
    events = await _load_events(CURRENT_SEASON, "fixtures", refresh=True)
    matches = [
        _format_match(event)
        for event in events
        if event["timestamp"] >= now and _is_requested_team(event, equipo)
    ]
    matches.sort(key=lambda item: (item["fecha"], item["hora"]))
    return {"consulta": "Q1", "equipo": equipo, "partidos": matches}


async def obtener_q2_ultimos_partidos(equipo: str) -> dict[str, Any]:
    now = time.time()
    matches: list[dict[str, Any]] = []
    years = range(CURRENT_SEASON, CURRENT_SEASON - HISTORY_SEASONS - 1, -1)
    result_sets = await asyncio.gather(
        *(_load_events(year, "results", refresh=True) for year in years)
    )
    for events in result_sets:
        matches.extend(
            _format_match(event, include_result=True)
            for event in events
            if event["timestamp"] <= now and _is_requested_team(event, equipo)
        )

    matches.sort(key=lambda item: (item["fecha"], item["hora"]), reverse=True)
    return {"consulta": "Q2", "equipo": equipo, "resultados": matches[:10]}


async def obtener_q3_historial(equipo1: str, equipo2: str) -> dict[str, Any]:
    now = time.time()
    target1, target2 = normalizar_equipo(equipo1), normalizar_equipo(equipo2)
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    years = range(CURRENT_SEASON, CURRENT_SEASON - HISTORY_SEASONS - 1, -1)
    result_sets = await asyncio.gather(
        *(_load_events(year, "results", refresh=True) for year in years)
    )
    for events in result_sets:
        for event in events:
            teams = {
                normalizar_equipo(event["local"]),
                normalizar_equipo(event["visitante"]),
                normalizar_equipo(event["local_slug"]),
                normalizar_equipo(event["visitante_slug"]),
            }
            if event["timestamp"] <= now and target1 in teams and target2 in teams and event["id"] not in seen:
                seen.add(event["id"])
                matches.append(_format_match(event, include_result=True))

    matches.sort(key=lambda item: (item["fecha"], item["hora"]), reverse=True)
    return {
        "consulta": "Q3",
        "enfrentamiento": f"{equipo1} vs {equipo2}",
        "partidos_encontrados": len(matches),
        "detalle": matches,
    }


async def obtener_q4_periodo(fecha_inicio: str, fecha_fin: str) -> dict[str, Any]:
    start, end = date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin)
    if start > end:
        raise ValueError("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
    if end.year - start.year > 2:
        raise ValueError("El período máximo permitido es de tres años.")

    now = time.time()
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    requests = [(year, "results") for year in range(start.year, end.year + 1)]
    # Soccerway no publica fixtures para temporadas que ya terminaron.
    if start.year <= CURRENT_SEASON <= end.year:
        requests.append((CURRENT_SEASON, "fixtures"))
    event_sets = await asyncio.gather(
        *(_load_events(year, feed_name, refresh=True) for year, feed_name in requests)
    )
    for events in event_sets:
        for event in events:
            event_date = datetime.fromtimestamp(event["timestamp"], timezone.utc).date()
            if start <= event_date <= end and event["id"] not in seen:
                seen.add(event["id"])
                matches.append(_format_match(event, include_result=event["timestamp"] <= now))

    matches.sort(key=lambda item: (item["fecha"], item["hora"]))
    return {
        "consulta": "Q4",
        "periodo": {"inicio": fecha_inicio, "fin": fecha_fin},
        "partidos": matches,
    }


async def obtener_q5_tabla_posiciones() -> dict[str, Any]:
    """Carga la tabla que Soccerway arma con JavaScript.

    La descarga HTML no trae las filas, por eso usamos Playwright aqui. La imagen
    Docker del proyecto ya trae Chromium y Playwright para esta consulta.
    """
    if async_playwright is None:
        raise ScraperError("Playwright no está instalado; ejecute la aplicación con Docker Compose.")

    url = _page_url(CURRENT_SEASON, "tabla-de-posiciones")
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(REQUEST_TIMEOUT * 1000))
                rows = page.locator(".ui-table__row")
                await rows.first.wait_for(timeout=int(REQUEST_TIMEOUT * 1000))
                posiciones = await rows.evaluate_all(
                    """rows => rows.map(row => {
                        const values = Array.from(row.querySelectorAll('.table__cell--value'))
                            .map(cell => cell.textContent.trim());
                        const [favor = '0', contra = '0'] = (values[4] || '0:0').split(':');
                        return {
                            posicion: Number((row.querySelector('.tableCellRank')?.textContent || '0').replace(/\\D/g, '')),
                            equipo: row.querySelector('.tableCellParticipant__name')?.textContent.trim() || '',
                            partidos_jugados: Number(values[0] || 0),
                            ganados: Number(values[1] || 0),
                            empatados: Number(values[2] || 0),
                            perdidos: Number(values[3] || 0),
                            goles_favor: Number(favor),
                            goles_contra: Number(contra),
                            diferencia_goles: Number(values[5] || 0),
                            puntos: Number(values[6] || 0),
                            forma: Array.from(row.querySelectorAll('.tableCellFormIcon span'))
                                .map(item => item.textContent.trim())
                                .filter(Boolean)
                        };
                    }).filter(row => row.equipo)"""
                )
            finally:
                await browser.close()
    except Exception as exc:
        raise ScraperError(f"No fue posible obtener la tabla de posiciones: {exc}") from exc

    if not posiciones:
        raise ScraperError("Soccerway devolvió una tabla de posiciones vacía.")
    return {
        "consulta": "Q5",
        "liga": "Liga de Primera de Chile",
        "posiciones": posiciones,
        "fuente_origen": url,
    }
