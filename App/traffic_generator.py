import httpx
import asyncio
import random
import numpy as np
import time

# Lista de equipos de la Liga Chilena para simular consultas
EQUIPOS = [
    "colo-colo", "universidad-de-chile", "universidad-catolica", "cobreloa",
    "palestino", "union-espanola", "audax-italiano", "everton",
    "cobresal", "coquimbo-unido", "ohiggins", "huachipato",
    "deportes-iquique", "nublense", "union-la-calera", "deportes-copiapo"
]

API_BASE_URL = "http://127.0.0.1:8000"
TOTAL_REQUESTS = 100  # Cantidad de consultas a simular

async def realizar_consulta(client: httpx.AsyncClient, equipo: str, id_peticion: int):
    """Ejecuta una peticion HTTP al endpoint Q1 de la API."""
    url = f"{API_BASE_URL}/q1/{equipo}"
    try:
        response = await client.get(url, timeout=5.0)
        datos = response.json()
        print(f"[{id_peticion}] Peticion a {equipo}: {datos.get('origen')}")
    except Exception as e:
        print(f"[{id_peticion}] Error conectando con API: {e}")

async def generador_uniforme():
    """Simula trafico donde todos los equipos son consultados por igual."""
    print("\n=== INICIANDO PRUEBA: DISTRIBUCION UNIFORME ===")
    async with httpx.AsyncClient() as client:
        tareas = []
        for i in range(TOTAL_REQUESTS):
            equipo = random.choice(EQUIPOS)
            tarea = asyncio.create_task(realizar_consulta(client, equipo, i))
            tareas.append(tarea)
            # Pausa de 50ms para evitar la estampida de caché
            await asyncio.sleep(0.05) 
        
        # Ejecutar todas las consultas
        await asyncio.gather(*tareas)

async def generador_zipf():
    """Simula trafico donde pocos equipos reciben casi todas las consultas."""
    print("\n=== INICIANDO PRUEBA: DISTRIBUCION ZIPF ===")
    # numpy.random.zipf genera indices, a = 1.5 es el parametro de concentracion
    a = 1.5
    indices_zipf = np.random.zipf(a, TOTAL_REQUESTS)
    
    # Ajustamos los indices para que no superen la cantidad de equipos que tenemos
    num_equipos = len(EQUIPOS)
    indices_ajustados = [min(idx - 1, num_equipos - 1) for idx in indices_zipf]
    
    async with httpx.AsyncClient() as client:
        tareas = []
        for i, idx in enumerate(indices_ajustados):
            equipo = EQUIPOS[idx]
            tarea = asyncio.create_task(realizar_consulta(client, equipo, i))
            tareas.append(tarea)
            # Pausa de 50ms para evitar la estampida de caché
            await asyncio.sleep(0.05)
        
        await asyncio.gather(*tareas)

async def main():
    print("Iniciando Generador de Trafico...")
    start_time = time.time()
    
    # --- EXPERIMENTO 1: UNIFORME ---
    #await generador_uniforme()
    
    # --- EXPERIMENTO 2: ZIPF ---
    
    await generador_zipf()
    
    tiempo_total = time.time() - start_time
    print(f"\nGeneracion de trafico finalizada en {tiempo_total:.2f} segundos.")
    print("Revisa los contadores de Hits y Misses en Redis.")

if __name__ == "__main__":
    # Necesario en Windows para evitar un error conocido con asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
