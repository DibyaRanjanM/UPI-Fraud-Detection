FROM python:3.11-slim
WORKDIR /app
RUN pip install httpx python-dotenv
COPY . .
CMD ["python", "-c", "print('GenAI service ready — called by api-gateway')"]