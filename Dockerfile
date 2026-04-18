FROM python:3.12-slim
 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
 
WORKDIR /app
 
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
COPY . .

# EXPOSE es documentación — no abre el puerto realmente. El puerto real lo define ports: en el docker-compose.yml. No es obligatorio pero es buena práctica.
EXPOSE 5555
 
CMD ["python", "main.py"]