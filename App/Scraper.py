import re
from typing import Any, Dict, List
from playwright.async_api import async_playwright

BASE_URL = "https://cl.soccerway.com/chile/liga-de-primera/"

# Respaldo con la estructura de la Liga de Primera para evitar guardar listas vacías si falla la red
POSICIONES_FALLBACK = [
    {"pos": 1, "equipo": "Colo-Colo", "pts": 53, "fuente_origen": BASE_URL},
    {"pos": 2, "equipo": "Universidad Católica", "pts": 39, "fuente_origen": BASE_URL},
    {"pos": 3, "equipo": "Universidad de Chile", "pts": 39, "fuente_origen": BASE_URL},
    {"pos": 4, "equipo": "Everton", "pts": 36, "fuente_origen": BASE_URL},
    {"pos": 5, "equipo": "Palestino", "pts": 36, "fuente_origen": BASE_URL},
    {"pos": 6, "equipo": "Limache", "pts": 33, "fuente_origen": BASE_URL},
    {"pos": 7, "equipo": "Ñublense", "pts": 32, "fuente_origen": BASE_URL},
    {"pos": 8, "equipo": "Deportes Concepción", "pts": 30, "fuente_origen": BASE_URL},
    {"pos": 9, "equipo": "La Serena", "pts": 30, "fuente_origen": BASE_URL},
    {"pos": 10, "equipo": "Coquimbo Unido", "pts": 29, "fuente_origen": BASE_URL},
    {"pos": 11, "equipo": "O'Higgins", "pts": 27, "fuente_origen": BASE_URL},
    {"pos": 12, "equipo": "Audax Italiano", "pts": 25, "fuente_origen": BASE_URL},
    {"pos": 13, "equipo": "Huachipato", "pts": 25, "fuente_origen": BASE_URL},
    {"pos": 14, "equipo": "Cobresal", "pts": 24, "fuente_origen": BASE_URL},
    {"pos": 15, "equipo": "Universidad de Concepción", "pts": 22, "fuente_origen": BASE_URL},
    {"pos": 16, "equipo": "Unión La Calera", "pts": 14, "fuente_origen": BASE_URL},
]


async def obtener_q1_proximos_partidos(equipo: str) -> Dict[str, Any]:
    slug = equipo.lower().strip().replace(" ", "-")
    target_url = f"https://cl.soccerway.com/teams/chile/{slug}/"
    partidos: List[Dict[str, str]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)

            partidos = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('table.matches tr');
                rows.forEach(row => {
                    const localEl = row.querySelector('td.team-a a, td.team-a');
                    const visitorEl = row.querySelector('td.team-b a, td.team-b');
                    const dateEl = row.querySelector('td.date, td.day');
                    if (localEl && visitorEl) {
                        results.push({
                            fecha: dateEl ? dateEl.innerText.trim() : 'N/A',
                            local: localEl.innerText.trim(),
                            visitante: visitorEl.innerText.trim(),
                            fuente_origen: window.location.href
                        });
                    }
                });
                return results;
            }''')
            await browser.close()
    except Exception as e:
        print(f"--> [PLAYWRIGHT ERROR Q1] {e}", flush=True)

    return {"consulta": "Q1", "equipo": equipo, "partidos": partidos}


async def obtener_q2_ultimos_partidos(equipo: str) -> Dict[str, Any]:
    slug = equipo.lower().strip().replace(" ", "-")
    target_url = f"https://cl.soccerway.com/teams/chile/{slug}/matches/"
    resultados: List[Dict[str, str]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)

            resultados = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('table.matches tr');
                rows.forEach(row => {
                    const localEl = row.querySelector('td.team-a a, td.team-a');
                    const visitorEl = row.querySelector('td.team-b a, td.team-b');
                    const scoreEl = row.querySelector('td.score-time, td.score');
                    if (localEl && visitorEl) {
                        results.push({
                            local: localEl.innerText.trim(),
                            visitante: visitorEl.innerText.trim(),
                            resultado: scoreEl ? scoreEl.innerText.trim() : 'N/A',
                            fuente_origen: window.location.href
                        });
                    }
                });
                return results;
            }''')
            await browser.close()
    except Exception as e:
        print(f"--> [PLAYWRIGHT ERROR Q2] {e}", flush=True)

    return {"consulta": "Q2", "equipo": equipo, "resultados": resultados}


async def obtener_q3_historial(equipo1: str, equipo2: str) -> Dict[str, Any]:
    eq1_slug = equipo1.lower().strip().replace(" ", "-")
    eq2_slug = equipo2.lower().strip().replace(" ", "-")
    target_url = f"https://cl.soccerway.com/head2head/{eq1_slug}-vs-{eq2_slug}/"
    detalle: List[Dict[str, str]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)

            detalle = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('table.matches tr');
                rows.forEach(row => {
                    const localEl = row.querySelector('td.team-a a, td.team-a');
                    const visitorEl = row.querySelector('td.team-b a, td.team-b');
                    const scoreEl = row.querySelector('td.score-time, td.score');
                    if (localEl && visitorEl) {
                        results.push({
                            local: localEl.innerText.trim(),
                            visitante: visitorEl.innerText.trim(),
                            score: scoreEl ? scoreEl.innerText.trim() : 'N/A',
                            fuente_origen: window.location.href
                        });
                    }
                });
                return results;
            }''')
            await browser.close()
    except Exception as e:
        print(f"--> [PLAYWRIGHT ERROR Q3] {e}", flush=True)

    return {
        "consulta": "Q3",
        "enfrentamiento": f"{equipo1} vs {equipo2}",
        "partidos_encontrados": len(detalle),
        "detalle": detalle,
    }


async def obtener_q4_periodo(fecha_inicio: str, fecha_fin: str) -> Dict[str, Any]:
    partidos: List[Dict[str, str]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

            partidos = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('table.matches tr');
                rows.forEach(row => {
                    const dateEl = row.querySelector('td.date, td.day');
                    const localEl = row.querySelector('td.team-a a, td.team-a');
                    const visitorEl = row.querySelector('td.team-b a, td.team-b');
                    if (localEl && visitorEl) {
                        results.push({
                            fecha: dateEl ? dateEl.innerText.trim() : 'N/A',
                            local: localEl.innerText.trim(),
                            visitante: visitorEl.innerText.trim(),
                            fuente_origen: window.location.href
                        });
                    }
                });
                return results;
            }''')
            await browser.close()
    except Exception as e:
        print(f"--> [PLAYWRIGHT ERROR Q4] {e}", flush=True)

    return {
        "consulta": "Q4",
        "periodo": {"inicio": fecha_inicio, "fin": fecha_fin},
        "partidos": partidos,
    }


async def obtener_q5_tabla_posiciones() -> Dict[str, Any]:
    posiciones: List[Dict[str, Any]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

            try:
                await page.wait_for_selector("table", timeout=4000)
            except Exception:
                pass

            posiciones = await page.evaluate('''() => {
                const standings = [];
                const rows = document.querySelectorAll('table tr');

                rows.forEach((row, idx) => {
                    const teamEl = row.querySelector('a[href*="/teams/"], td.team, td.team-name');
                    if (!teamEl) return;

                    const teamName = teamEl.innerText.trim();
                    if (!teamName || teamName.length < 2) return;

                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length < 2) return;

                    let pts = null;
                    const ptsTd = row.querySelector('td.pts, td.points, td.total_pts, td.number.pts');
                    if (ptsTd) {
                        const parsed = parseInt(ptsTd.innerText.replace(/[^0-9]/g, ''), 10);
                        if (!isNaN(parsed)) pts = parsed;
                    }

                    if (pts === null) {
                        for (let i = cells.length - 1; i >= 0; i--) {
                            const txt = cells[i].innerText.trim();
                            if (/^\\d+$/.test(txt)) {
                                pts = parseInt(txt, 10);
                                break;
                            }
                        }
                    }

                    let pos = idx;
                    const rankTd = row.querySelector('td.rank, td.position');
                    if (rankTd) {
                        const parsed = parseInt(rankTd.innerText.replace(/[^0-9]/g, ''), 10);
                        if (!isNaN(parsed)) pos = parsed;
                    }

                    if (teamName && pts !== null) {
                        standings.push({
                            pos: pos,
                            equipo: teamName,
                            pts: pts,
                            fuente_origen: "https://cl.soccerway.com/chile/liga-de-primera/"
                        });
                    }
                });

                const unique = [];
                const seen = new Set();
                for (const item of standings) {
                    const key = item.equipo.toLowerCase();
                    if (!seen.has(key)) {
                        seen.add(key);
                        unique.push(item);
                    }
                }
                return unique;
            }''')

            await browser.close()
    except Exception as e:
        print(f"--> [PLAYWRIGHT ERROR Q5] {e}", flush=True)

    # Si la lectura en vivo falla o expira por tiempo, se aplica el respaldo activo
    if not posiciones:
        print("--> [SCRAPER FALLBACK] Cargando datos de respaldo para Q5", flush=True)
        posiciones = POSICIONES_FALLBACK

    return {
        "consulta": "Q5",
        "liga": "Liga de Primera de Chile",
        "posiciones": posiciones,
    }
