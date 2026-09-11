FROM python:3.10-slim
WORKDIR /proyecto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Comando para iniciar la API y exponerla hacia afuera
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
