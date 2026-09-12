import redis

# conexion a redis para metricas
import os
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, db=0, decode_responses=True)

def registrar_hit():
    # Suma 1 al contador global de aciertos en cache
    r.incr("metricas:hits")

def registrar_miss():
    # Suma 1 al contador global de fallos en cache
    r.incr("metricas:misses")

def registrar_latencia(latencia_ms: float):
    # Guarda el tiempo de respuesta 
    r.lpush("metricas:latencias", latencia_ms)
