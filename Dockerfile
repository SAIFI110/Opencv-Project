# 1. Base image ab specifically Python 3.12.0 par set hai
FROM python:3.12.0-slim

# 2. Container ke andar working directory set karein
WORKDIR /app

# 3. Requirements copy karein aur install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Baqi saara project code (backend, static folder, diagrams) copy karein
COPY . .

# 5. FastAPI ka port expose karein
EXPOSE 8000

# 6. Application ko run karne ka command
CMD ["uvicorn", "chatbot_backend:app", "--host", "0.0.0.0", "--port", "8000"]