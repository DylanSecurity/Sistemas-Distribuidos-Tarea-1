# Sistemas-Distribuidos
# Grupo 1
# Tarea 1: Plataforma distribuida del fútbol Chileno

**Asignatura:** Sistemas Distribuidos (2026-2)
**Profesor:** Nicolás Hidalgo
**Ayudantes:** Benjamín Aceituno y Isidora Gonzales
**Estudiantes:** Carlos Valenzuela y Dylan Moraga (4to año, Ingeniería Civil en Informática)

---

## Descripción del Proyecto

Este proyecto implementa una plataforma distribuida capaz de manejar y responder a consultas sobre el fútbol chileno . El sistema está diseñado para soportar alta concurrencia mediante la implementación de un sistema de caché distribuido utilizando **Redis** y una API desarrollada en **Python (FastAPI)**. 

Se simula un entorno de alta demanda  testeando distintas políticas de reemplazo de caché (LRU, LFU, FIFO) y distribuciones de tráfico (Uniforme y Zipf).

---

## Estructura del Proyecto

Propuesta de estructura para la solución:

```text
tarea_1_sistemas_distribuidos/
│
├── app/                        # Modulos principales del sistema
│   ├── main.py                 # API Gateway (FastAPI) y gestion de Cache (Redis)
│   ├── scraper.py              # Servicio de extraccion de datos (Soccerway)
│   └── traffic_generator.py    # Generador de trafico (Distribuciones Uniforme y Zipf)
│
├── data/                       # Almacenamiento local temporal
│   └── liga_chile.json         # Datos precargados en memoria al iniciar el sistema
│
├── informe/                    # Documentacion y análisis
│   └── informe_entrega1.pdf    # Informe tecnico con análisis de metricas y rendimiento
│
├── docker-compose.yml          # Orquestacion de los servicios (App, Redis, Métricas)
├── Dockerfile                  # Construccion de la imagen para la aplicacion Python
├── requirements.txt            # Dependencias del proyecto (FastAPI, Redis, httpx, etc.)
└── README.md                  
