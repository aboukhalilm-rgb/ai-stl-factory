# AI STL Creation Factory

An automated AI-to-CAD STL generation system for local and cloud deployment.

## Overview

The project combines:

- Groq LLM-driven parametric CAD generation
- Optional OpenSCAD/CadQuery compilation pipeline
- Mesh integrity validation (`watertight` / manifold checks)
- APScheduler automation every 3 hours
- Flask dashboard for settings and manual generation
- Telegram bot alerts and Google Drive archiving
- Support for Windows/Linux and Android via Termux + PRoot Ubuntu
- Ubuntu VPS and Hugging Face Spaces integration

## Architecture

```text
ai-stl-factory/
├── app.py
├── config.py
├── key_rotator.py
├── stl_generator.py
├── scheduler.py
├── uploader.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── credentials/
│   └── .gitkeep
├── logs/
│   └── .gitkeep
├── exports/
│   └── .gitkeep
├── generated/
│   └── .gitkeep
├── templates/
│   └── .gitkeep
└── .dockerignore
```

## Quick start

1. Copy `.env.example` to `.env` and fill in secrets.
2. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   python app.py
   ```
4. Open http://localhost:5000 and set the initial password on first run.

## Core categories

1. Tabletop miniatures and D&D figurines
2. Articulated print-in-place toys
3. Home organizers and office accessories
4. Resin jewelry casting molds
5. Dental and medical models
6. Classic car parts and discontinued spares
7. Accessibility aids
8. Custom electronics enclosures
9. Parametric engineering fittings and pipe connectors

## Deployment notes

- Local: Windows/macOS/Linux + Termux/PRoot Ubuntu
- Cloud: Ubuntu VPS + Docker + optional Hugging Face Spaces integration
- Scheduler runs internally using APScheduler at a 3-hour interval

## Commercial STL strategy

See the documentation in `README.md` for platform strategy, listing workflow, and marketing guidance.
