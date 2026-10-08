version: '3.9'

services:
  ai-stl-factory:
    build: .
    container_name: ai-stl-factory
    ports:
      - "5000:5000"
    env_file:
      - .env
    volumes:
      - .:/app
      - ./credentials:/app/credentials
      - ./logs:/app/logs
      - ./generated:/app/generated
    restart: unless-stopped
