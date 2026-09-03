// Typed API client for the photoEvent backend.
import type {
  EventBase,
  EventDetail,
  Folder,
  Photo,
  SearchResponse,
  UploadJob,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Prefix a relative backend path (e.g. an image proxy URL) with the API base.
// Absolute URLs are returned unchanged.
export function assetUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

const TOKEN_KEY = "photoevent_admin_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // Ignore non-JSON error bodies.
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Auth ---
export async function login(username: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  setToken(data.access_token);
  return data.access_token;
}

// --- Admin ---
export const adminListEvents = () =>
  request<EventBase[]>("/api/admin/events", {}, true);

export const adminCreateEvent = (payload: {
  title: string;
  slug: string;
  event_date: string | null;
  drive_folder_id?: string | null;
}) =>
  request<EventBase>(
    "/api/admin/events",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    true,
  );

// Trigger ingestion of an existing Google Drive folder's photos. Returns a job.
export const adminSyncDrive = (
  eventId: string,
  driveFolderId?: string,
) =>
  request<UploadJob>(
    `/api/admin/events/${eventId}/sync`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        driveFolderId ? { drive_folder_id: driveFolderId } : {},
      ),
    },
    true,
  );

export const adminCreateFolder = (eventId: string, name: string, position = 0) =>
  request<Folder>(
    `/api/admin/events/${eventId}/folders`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, position }),
    },
    true,
  );

export const adminRenameFolder = (folderId: string, name: string) =>
  request<Folder>(
    `/api/admin/folders/${folderId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
    true,
  );

export const adminDeleteFolder = (folderId: string, cascade = true) =>
  request<void>(
    `/api/admin/folders/${folderId}?cascade=${cascade}`,
    { method: "DELETE" },
    true,
  );

export async function adminUploadPhotos(
  folderId: string,
  files: FileList | File[],
): Promise<{ uploaded: Photo[] }> {
  const form = new FormData();
  Array.from(files).forEach((f) => form.append("files", f));
  return request<{ uploaded: Photo[] }>(
    `/api/admin/folders/${folderId}/photos`,
    { method: "POST", body: form },
    true,
  );
}

// --- Guest ---
export const getEvent = (slug: string) =>
  request<EventDetail>(`/api/e/${slug}`);

export const getFolderPhotos = (
  slug: string,
  folderId: string,
  limit = 60,
  offset = 0,
) =>
  request<Photo[]>(
    `/api/e/${slug}/folders/${folderId}/photos?limit=${limit}&offset=${offset}`,
  );

export async function searchBySelfie(
  slug: string,
  selfie: File,
): Promise<SearchResponse> {
  const form = new FormData();
  form.append("selfie", selfie);
  return request<SearchResponse>(`/api/e/${slug}/search`, {
    method: "POST",
    body: form,
  });
}

export const downloadUrl = (photoId: string) =>
  `${API_BASE}/api/public/photos/${photoId}/download`;

// Upload a ZIP of images for background processing. Returns the created job.
export async function adminUploadZip(
  eventId: string,
  zip: File,
  folderId?: string,
): Promise<UploadJob> {
  const form = new FormData();
  form.append("file", zip);
  const qs = folderId ? `?folder_id=${folderId}` : "";
  return request<UploadJob>(
    `/api/admin/events/${eventId}/upload-zip${qs}`,
    { method: "POST", body: form },
    true,
  );
}

// Poll a bulk-upload job's status/progress.
export const adminGetJob = (jobId: string) =>
  request<UploadJob>(`/api/admin/jobs/${jobId}`, {}, true);

// Process a ZIP already in Google Drive — no HTTP upload, no timeout.
export const adminUploadZipFromDrive = (eventId: string, driveFileId: string) =>
  request<UploadJob>(
    `/api/admin/events/${eventId}/upload-zip-from-drive?drive_file_id=${encodeURIComponent(driveFileId)}`,
    { method: "POST" },
    true,
  );
