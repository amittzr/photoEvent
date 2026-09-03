# photoEvent

Event photo sharing with AI-powered facial recognition. Admins create events, organize photos into folders, and bulk-upload high-resolution images. Guests open a unique event link, browse a masonry gallery, and use **Find My Photos 🤳** to locate themselves with a selfie.

## Architecture

- **Backend**: FastAPI (Python 3.10+), Clean Architecture (Routers → Services → Repositories → Models).
- **Database**: PostgreSQL 16 + `pgvector` (HNSW cosine index for face-embedding search).
- **ORM/Migrations**: SQLModel + Alembic.
- **Storage**: Google Drive API (originals + optimized thumbnails, public read).
- **Face engine**: InsightFace `buffalo_l` (512-d) by default; `face_recognition` (128-d) fallback.
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS, mobile-first.

See `.kiro/requirements.md` and `.kiro/design.md` for the full spec, API contract, and ERD.

## Privacy

Guest selfies are processed in memory only. Neither the selfie image nor its embedding is written to disk, Google Drive, or the database.

## Quick start

### 1. Backend + database (Docker)

```bash
cp backend/.env.example backend/.env      # then edit secrets + Google Drive config
# Place your Drive service-account JSON at backend/google-credentials.json
# Share the root Drive folder with the service account's email (Editor)
docker compose up --build
```

This starts PostgreSQL (with pgvector), runs Alembic migrations, and serves the API at `http://localhost:8000` (docs at `/docs`).

### 2. Frontend

```bash
cd frontend
cp .env.local.example .env.local          # set NEXT_PUBLIC_API_BASE_URL
npm install
npm run dev                               # http://localhost:3000
```

## Configuration highlights (`backend/.env`)

| Key | Purpose |
|-----|---------|
| `DATABASE_URL` | Postgres connection (psycopg driver) |
| `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Single-admin auth |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `GOOGLE_APPLICATION_CREDENTIALS` | Google Drive storage |
| `FACE_ENGINE`, `FACE_EMBEDDING_DIM` | `insightface` (512) or `face_recognition` (128) |
| `FACE_MATCH_THRESHOLD` | Cosine-distance cutoff for matches (lower = stricter) |

> If you switch `FACE_ENGINE` to `face_recognition`, set `FACE_EMBEDDING_DIM=128` **before** running migrations (the vector column dimension is fixed at migration time).

## Key API endpoints

| Method | Path | Access |
|--------|------|--------|
| POST | `/api/auth/login` | public |
| GET/POST | `/api/admin/events` | admin |
| POST | `/api/admin/events/{id}/folders` | admin |
| POST | `/api/admin/folders/{id}/photos` | admin (bulk upload) |
| GET | `/api/e/{slug}` | public |
| GET | `/api/e/{slug}/folders/{folder_id}/photos` | public |
| POST | `/api/e/{slug}/search` | public (selfie, in-memory) |
| GET | `/api/photos/{id}/download` | public |
