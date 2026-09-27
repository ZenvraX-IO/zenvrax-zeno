# Zeno, el asistente. Clona el Dockerfile de Xrise, que lleva meses en produccion.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY catalogo ./catalogo
COPY servicio ./servicio
COPY web ./web
COPY lector.py zeno.py ver_catalogo.py ./
# Los tests viajan en la imagen a proposito: si no se pueden ejecutar donde corre el codigo, no se
# ejecutan nunca. Son puros y pesan nada.
COPY tests ./tests
EXPOSE 8804
CMD ["uvicorn", "servicio.api:app", "--host", "0.0.0.0", "--port", "8804"]
