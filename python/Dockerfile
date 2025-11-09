# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install python-docx et requests
RUN pip install --no-cache-dir python-docx requests

# Copier le contenu de tocomplete dans /app (sans bind mount)
COPY ./tocomplete /app/

# Copier les scripts Python
COPY ./python /app/python

WORKDIR /app/python

# Utiliser shell form pour exécuter les deux scripts séquentiellement
CMD ["sh", "-c", "python3 JsonFormater.py && python3 send_to_ai.py"]