# Design — Event Photo Sharing with Facial Recognition

## 1. System Overview

```
┌──────────────┐        ┌───────────────────────────────────────┐        ┌──────────────┐
│  Next.js UI  │  HTTP  │              FastAPI API                │        │  PostgreSQL  │
│ Admin+Guest  │ <────> │  Routers → Services → Repositories      │ <────> │  + pgvector  │
└──────────────┘        │  (Auth, Event, Storage, FaceRecognition)│        └──────────────┘
                        └───────────────┬─────────────────────────┘
                                        │
                              ┌─────────┴─────────┐
                              │  Google Drive API  │
                              │ (originals +       │
                              │  thumbnails)       │
                              └────────────────────┘
```

## 2. Backend Directory Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app factory, middleware, router registration
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── security.py          # JWT create/verify, password hashing
│   │   └── database.py          # Engine, session, get_session dependency
│   ├── deps.py                  # DI: current_admin, get Drive client, get services
│   ├── models/                  # SQLModel entities
│   │   ├── event.py
│   │   ├── folder.py
│   │   ├── photo.py
│   │   └── face.py
│   ├── schemas/                 # Pydantic DTOs
│   │   ├── auth.py
│   │   ├── event.py
│   │   ├── folder.py
│   │   ├── photo.py
│   │   └── search.py
│   ├── repositories/            # DB access
│   │   ├── event_repository.py
│   │   ├── folder_repository.py
│   │   ├── photo_repository.py
│   │   └── face_repository.py
│   ├── services/                # Business logic
│   │   ├── auth_service.py
│   │   ├── event_service.py
│   │   ├── storage_service.py       # Google Drive manager
│   │   ├── face_service.py          # embedding extraction
│   │   └── upload_service.py        # orchestrates upload + thumbnail + async face task
│   └── routers/
│       ├── auth.py
│       ├── admin_events.py
│       ├── admin_folders.py
│       ├── admin_photos.py
│       └── guest.py
├── alembic/                     # migrations
├── alembic.ini
├── requirements.txt
├── Dockerfile
└── .env.example
```

## 3. Database ERD

```
┌────────────────────┐        ┌────────────────────┐
│       events       │        │      folders       │
├────────────────────┤        ├────────────────────┤
│ id           UUID PK│1     * │ id           UUID PK│
│ title        text   │───────<│ event_id     FK     │
│ slug         text U  │        │ name         text   │
│ event_date   date   │        │ position     int    │
│ created_at   ts     │        │ created_at   ts     │
└────────────────────┘        └─────────┬──────────┘
                                         │ 1
                                         │
                                         │ *
                              ┌──────────┴─────────┐
                              │       photos       │
                              ├────────────────────┤
                              │ id            UUID PK│
                              │ folder_id     FK     │
                              │ event_id      FK     │  (denormalized for fast scoping)
                              │ original_url  text   │
                              │ thumb_url     text   │
                              │ drive_original_id text│  (Drive file ID)
                              │ drive_thumb_id    text│  (Drive file ID)
                              │ width         int    │
                              │ height        int    │
                              │ status        enum   │  pending|processing|done|failed
                              │ created_at    ts     │
                              └─────────┬──────────┘
                                        │ 1
                                        │ *
                             ┌──────────┴─────────┐
                             │       faces        │
                             ├────────────────────┤
                             │ id           UUID PK │
                             │ photo_id     FK      │
                             │ event_id     FK      │  (denormalized for scoped search)
                             │ embedding    vector  │  (dim=512 InsightFace / 128 fallback)
                             │ bbox         jsonb    │  (x,y,w,h)
                             │ det_score    float    │
                             │ created_at   ts       │
                             └────────────────────┘
```

### Indexes
- `events.slug` UNIQUE.
- `faces.embedding` — pgvector HNSW index (`vector_cosine_ops`) for ANN search.
- `faces.event_id`, `photos.event_id`, `photos.folder_id` — btree for scoping.

## 4. API Contract

### Auth
- `POST /api/auth/login` → `{username, password}` → `{access_token, token_type}`

### Admin (JWT required)
- `GET  /api/admin/events` → `[EventOut]`
- `POST /api/admin/events` → `{title, slug, event_date}` → `EventOut`
- `PATCH /api/admin/events/{event_id}` → partial → `EventOut`
- `DELETE /api/admin/events/{event_id}` → `204`
- `POST /api/admin/events/{event_id}/folders` → `{name, position?}` → `FolderOut`
- `DELETE /api/admin/folders/{folder_id}` → `204`
- `POST /api/admin/folders/{folder_id}/photos` (multipart, many files) → `{uploaded: [PhotoOut]}`

### Guest (public)
- `GET  /api/e/{slug}` → `EventDetailOut` (event + folders + photo counts)
- `GET  /api/e/{slug}/folders/{folder_id}/photos?limit&offset` → `[PhotoOut]`
- `POST /api/e/{slug}/search` (multipart selfie) → `{matches: [PhotoMatchOut]}` — selfie discarded after processing
- `GET  /api/photos/{photo_id}/download` → streams the original bytes from Google Drive (attachment)

## 5. Facial Recognition Flow

**Indexing (on upload, background):**
1. Download/keep original bytes in memory.
2. Generate thumbnail (Pillow, target ~200–300KB, longest edge ~1600px, progressive JPEG).
3. Resolve/create the event's Drive sub-folders, then upload original + thumbnail to Google Drive and grant public read access.
4. Detect faces + extract embeddings (InsightFace `buffalo_l`).
5. Insert one `faces` row per detected face with the embedding vector.
6. Update photo `status`.

**Search (guest selfie):**
1. Receive selfie in memory (UploadFile → bytes).
2. Extract the largest-face embedding.
3. `SELECT ... ORDER BY embedding <=> :query LIMIT k` scoped to `event_id`, with a cosine-distance threshold.
4. Deduplicate photos, return matches ranked by best similarity.
5. Discard selfie bytes and embedding. **Nothing persisted.**

## 6. Storage Layout (Google Drive)

All content lives under the folder identified by `GOOGLE_DRIVE_ROOT_FOLDER_ID`.
Drive is folder-ID based, so the storage manager resolves each logical path
segment to a Drive folder (creating it on demand) and caches the IDs.

```
{GOOGLE_DRIVE_ROOT_FOLDER_ID}/
  events/{event_id}/
    originals/{photo_id}.{ext}   → Drive file, public reader
    thumbs/{photo_id}.jpg        → Drive file, public reader
```

The `photos` table stores each file's Drive file ID (`drive_original_id`,
`drive_thumb_id`) plus a directly viewable URL
(`https://drive.google.com/uc?export=view&id=<id>`).

## 7. Security & Privacy
- JWT HS256, configurable expiry; bearer scheme.
- Passwords hashed with bcrypt (passlib).
- Guest selfie never touches disk/Drive; processed from an in-memory buffer.
- Photos are granted public read (`anyone`/`reader`) so the client can render them; downloads are proxied through the API as an attachment stream.
- Drive access uses a service account (Drive API enabled) with the root folder shared to it; credentials come from `GOOGLE_APPLICATION_CREDENTIALS`.
- CORS restricted to configured frontend origin.

## 8. Frontend Structure

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                 # landing
│   ├── e/[slug]/page.tsx        # guest event gallery
│   └── admin/
│       ├── login/page.tsx
│       └── page.tsx             # dashboard: events, folders, upload
├── components/
│   ├── MasonryGallery.tsx
│   ├── Lightbox.tsx
│   ├── FolderTabs.tsx
│   ├── FindMyPhotos.tsx         # selfie capture/upload modal
│   └── PhotoCard.tsx
├── lib/api.ts                   # typed API client
└── tailwind + next config
```
