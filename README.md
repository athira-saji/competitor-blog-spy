# Competitor Blog Spy — V1

React/Vite frontend + FastAPI backend + PostgreSQL/Supabase.

## Features
- Competitor management
- Automatic RSS/Atom, sitemap and direct-page source discovery
- Continuous asynchronous monitoring
- Concurrent checks with a configurable limit
- Duplicate article prevention
- Full article metadata extraction
- Exact publication/discovery timestamps and detection delay
- Monitoring history and failed-check logs
- Dashboard with performance metrics
- Designed for 100 monitored websites

## API keys
No AI API key is required. Production only needs `DATABASE_URL` for PostgreSQL/Supabase.

## Local development

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend
Open another terminal:
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173.

## Production
Use Supabase PostgreSQL and deploy the two services in `render.yaml`. Set the backend `FRONTEND_ORIGINS` to the deployed frontend URL and `DATABASE_URL` to the Supabase PostgreSQL connection string.
