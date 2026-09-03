# Requirements — Event Photo Sharing with Facial Recognition

## 1. User Roles

| Role  | Access | Auth |
|-------|--------|------|
| Admin | Full management of events, folders, uploads | JWT (single admin account) |
| Guest | Read-only per-event access via unique URL, selfie search, downloads | None (public event slug) |

## 2. Functional Requirements

### 2.1 Authentication & Authorization
- **FR-1**: Single admin logs in with username + password, receives a JWT access token.
- **FR-2**: All `/api/admin/*` routes require a valid JWT bearer token.
- **FR-3**: Guests access events through public slug URLs (`/e/{slug}`) with no registration.
- **FR-4**: Admin credentials are seeded from environment variables; password stored as a bcrypt hash.

### 2.2 Event & Folder Management (Admin)
- **FR-5**: Admin can create an event with `title`, `slug` (unique, URL-safe), and `event_date`.
- **FR-6**: Admin can update and delete events.
- **FR-7**: Admin can create sub-folders/categories within an event (e.g., "הפרשת חלה", "חינה", "חתונה", "מסיבה"). Folder names support Unicode (Hebrew).
- **FR-8**: Admin can bulk-upload high-resolution images assigned to a specific folder.

### 2.3 Facial Recognition
- **FR-9**: On upload, extract face embeddings (512-d InsightFace, or 128-d face_recognition fallback) for every detected face, asynchronously.
- **FR-10**: Store embeddings in PostgreSQL using `pgvector`, linked to the source photo.
- **FR-11**: Guest uploads a selfie (file upload or live camera capture); the system extracts its embedding and runs a vector similarity search scoped to the current event.
- **FR-12**: Return matching photos ranked by similarity within seconds.
- **FR-13 (Privacy)**: Guest selfie image and its embedding MUST NOT be persisted to disk or cloud; both are discarded immediately after processing.

### 2.4 Storage & Processing
- **FR-14**: Store original high-resolution images in Google Drive (via the Google Drive API), under a configurable root folder, with one sub-folder per event.
- **FR-15**: Generate optimized thumbnails (~200–300KB) locally before upload, then store them in Google Drive alongside the originals (reduces bandwidth and avoids rate limits).
- **FR-15a**: Uploaded originals and thumbnails are granted public read access (`anyone`/`reader`) so the web client can render them directly.
- **FR-16**: Face vector extraction runs as a background task, not blocking the upload response.
- **FR-17**: Track processing status per photo (`pending`, `processing`, `done`, `failed`).

### 2.5 Guest UI
- **FR-18**: Mobile-first, minimal, clean UI.
- **FR-19**: Folder tabs to filter photos by category.
- **FR-20**: Masonry grid with lazy loading and an image lightbox.
- **FR-21**: Prominent "Find My Photos 🤳" action.
- **FR-22**: Direct download button for full-resolution originals.

## 3. Non-Functional Requirements
- **NFR-1**: Selfie search returns in < 3s for events with up to ~50k faces (pgvector IVFFlat/HNSW index).
- **NFR-2**: Clean Architecture with strict separation (Routers, Services, Repositories, Schemas, Models).
- **NFR-3**: All code comments in English.
- **NFR-4**: Containerized local dev via docker-compose (Postgres + pgvector).
- **NFR-5**: Secrets (JWT secret, Google Drive service-account credentials, admin password) provided via environment variables.
- **NFR-6**: CORS configured for the frontend origin.

## 4. Out of Scope (v1)
- Multi-admin / role hierarchy.
- Payment / e-commerce.
- Video processing.
