// Shared API types mirroring the backend schemas.

export type PhotoStatus = "pending" | "processing" | "done" | "failed";

export interface Photo {
  id: string;
  folder_id: string;
  event_id: string;
  original_url: string;
  thumb_url: string;
  width: number | null;
  height: number | null;
  status: PhotoStatus;
  created_at: string;
}

export interface Folder {
  id: string;
  event_id: string;
  name: string;
  position: number;
  created_at: string;
  photo_count: number;
}

export interface EventBase {
  id: string;
  title: string;
  slug: string;
  event_date: string | null;
  created_at: string;
}

export interface EventDetail extends EventBase {
  folders: Folder[];
}

export interface PhotoMatch {
  photo: Photo;
  similarity: number;
}

export type JobStatus = "pending" | "processing" | "done" | "failed";

export interface UploadJob {
  id: string;
  event_id: string;
  folder_id: string;
  status: JobStatus;
  total: number;
  processed: number;
  failed: number;
  message: string | null;
  created_at: string;
  updated_at: string;
}

export interface SearchResponse {
  matches: PhotoMatch[];
  faces_detected_in_selfie: number;
}
