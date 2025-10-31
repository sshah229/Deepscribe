# DeepScribe Clinical Trials Finder

Full‑stack demo that:

- Extracts structured patient data from a transcript using Gemini (optional) or a safe heuristic fallback.
- Queries ClinicalTrials.gov for matching studies.
- Displays top matches in a simple React UI.

## Architecture

- Backend: Python Flask + httpx. Optional Gemini integration via `google-generativeai`.
- Frontend: React + Vite.

## Prerequisites

- Python 3.10+
- Node.js 18+

## Quick Start (Local)

1. Backend
   - Create env and install deps
     - Windows PowerShell:
       ```powershell
       python -m venv .venv
       .venv\\Scripts\\Activate.ps1
       pip install -r server/requirements.txt
       copy server/.env.example server/.env
       ```
   - Set `GOOGLE_API_KEY` in `server/.env` if you want Gemini extraction. If omitted, a regex heuristic is used.
   - Run the server
     ```powershell
     python server/app.py
     ```
   - Health check: http://localhost:8000/api/health

2. Frontend
   - Install deps and run dev server
     ```powershell
     npm --prefix client install
     npm --prefix client run dev
     ```
   - Open http://localhost:5173
   - Vite proxy sends `/api/*` to the Flask server at `http://localhost:8000`.

## Usage

- Click "Use sample transcript" to preload a realistic conversation.
- Click "Extract data" to see parsed age/sex/diagnosis/keywords/locations.
- Click "Find trials" to fetch top matches. Cards link to ClinicalTrials.gov pages.

## Deployment

- Backend: Deploy to Render/Fly/Heroku or similar. Set env `PORT` and `GOOGLE_API_KEY`.
- Frontend: Deploy to Vercel/Netlify. Configure `VITE_API_BASE` or use a reverse proxy. For simplicity, you can serve the React build from a static host and point it to your backend URL by replacing fetch base path `/api` with your backend origin.

## Assumptions

- Transcript may omit some fields; the app uses best-effort extraction and does permissive filtering.
- Age/sex eligibility is filtered client-side based on ClinicalTrials.gov fields.
- Ranking is by API order + local filters; you could extend with LLM ranking.

## Extend Ideas

- LLM-based ranking and reasoning for inclusion/exclusion.
- Save favorites and export/share.
- Chat about a specific trial.
- Geospatial filtering by distance.
