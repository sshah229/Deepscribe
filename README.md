# DeepScribe Clinical Trials Finder

Full-stack demo that:

- Extracts structured patient data from a transcript using Gemini (primary) with a safe regex fallback.
- Queries ClinicalTrials.gov for matching studies (classic study_fields with smart fallbacks to full_studies and v2).
- Renders top matches in a modern React UI.

## Architecture

- Backend: Python Flask + httpx. Optional Gemini integration via `google-generativeai`.
- Frontend: React + Vite.

## Prerequisites

- Python 3.10+
- Node.js 18+

## Live Demo

- Client (Vercel): https://deepscribeclient.vercel.app/
- API (Vercel): https://deepscribe-tan.vercel.app/

The client calls the backend via `VITE_API_BASE`. In production this is set to the API URL above.

## Overview of Approach

- Transcript → Gemini prompt (JSON-only) extracts: `age`, `sex`, `diagnosis`, `keywords`, `locations`.
- If Gemini is unavailable or a field is missing (age), a minimal regex extractor fills gaps.
- Trial search builds a domain-aware OR query (e.g., adds synonyms for HER2/breast cancer or HFrEF) and queries ClinicalTrials.gov.
- Local filtering by age/sex; if no results pass filters, top unfiltered results are returned to avoid empty states.

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
   - Optional: create `client/.env` with `VITE_API_BASE=http://localhost:8000`.

## Usage

- Click "Use sample transcript" to preload a realistic conversation.
- Click "Extract data" to see parsed age/sex/diagnosis/keywords/locations.
- Click "Find trials" to fetch top matches. Cards link to ClinicalTrials.gov pages.

## Deployment

- Client on Vercel
  - Project root: `client`
  - Env var: `VITE_API_BASE=https://deepscribe-tan.vercel.app`
  - Build: `vite build` (default), Output: `dist`

- API on Vercel (or any Python host)
  - Ensure `server/app.py` runs with `PORT` from environment.
  - Env vars:
    - `GOOGLE_API_KEY`
    - `GEMINI_MODEL` (e.g., `gemini-2.5-flash`)
  - Test: `https://deepscribe-tan.vercel.app/api/health`

## Assumptions

- Transcript may omit some fields; the app uses best-effort extraction and does permissive filtering.
- Age/sex eligibility is filtered client-side based on ClinicalTrials.gov fields.
- Ranking is by API order + local filters; you could extend with LLM ranking.

## API Endpoints

- `POST /api/extract` → `{ extracted }`
- `POST /api/match` → `{ extracted, results }`

Example:
```bash
curl -X POST https://deepscribe-tan.vercel.app/api/match \
  -H "Content-Type: application/json" \
  -d '{"transcript":"58-year-old woman with HER2-positive invasive ductal carcinoma..."}'
```

## Extend Ideas

- LLM-based ranking and reasoning for inclusion/exclusion.
- Save favorites and export/share.
- Chat about a specific trial.
- Geospatial filtering by distance.
