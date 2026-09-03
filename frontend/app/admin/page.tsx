"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  adminCreateEvent,
  adminCreateFolder,
  adminGetJob,
  adminListEvents,
  adminUploadPhotos,
  adminUploadZip,
  clearToken,
  getEvent,
  getToken,
} from "@/lib/api";
import type { EventBase, EventDetail, Folder, UploadJob } from "@/lib/types";

// Admin dashboard: create events, add folders, bulk-upload photos.
export default function AdminDashboard() {
  const router = useRouter();
  const [events, setEvents] = useState<EventBase[]>([]);
  const [selected, setSelected] = useState<EventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // New-event form state.
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [eventDate, setEventDate] = useState("");

  // New-folder + upload state.
  const [folderName, setFolderName] = useState("");
  const [uploadFolder, setUploadFolder] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadInfo, setUploadInfo] = useState<string>("");

  // ZIP bulk-upload state.
  const [zipUploading, setZipUploading] = useState(false);
  const [job, setJob] = useState<UploadJob | null>(null);

  // Redirect to login if there is no token.
  useEffect(() => {
    if (!getToken()) {
      router.replace("/admin/login");
      return;
    }
    refreshEvents();
  }, [router]);

  async function refreshEvents() {
    try {
      setEvents(await adminListEvents());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events.");
    }
  }

  async function openEvent(slugValue: string) {
    setSelected(await getEvent(slugValue));
  }

  async function onCreateEvent(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await adminCreateEvent({
        title,
        slug,
        event_date: eventDate || null,
      });
      setTitle("");
      setSlug("");
      setEventDate("");
      await refreshEvents();
      await openEvent(created.slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create event.");
    }
  }

  async function onCreateFolder(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    try {
      await adminCreateFolder(selected.id, folderName);
      setFolderName("");
      await openEvent(selected.slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder.");
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files || !uploadFolder) return;
    setUploading(true);
    setUploadInfo("");
    try {
      const res = await adminUploadPhotos(uploadFolder, files);
      setUploadInfo(`Uploaded ${res.uploaded.length} photo(s). Faces indexing…`);
      if (selected) await openEvent(selected.slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function onUploadZip(files: FileList | null) {
    if (!files || files.length === 0 || !selected) return;
    setZipUploading(true);
    setError(null);
    try {
      // folderId omitted -> backend files them under a default "Uploads" folder.
      const created = await adminUploadZip(selected.id, files[0]);
      setJob(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ZIP upload failed.");
    } finally {
      setZipUploading(false);
    }
  }

  // Poll the ZIP job status until it completes or fails.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const timer = setInterval(async () => {
      try {
        const updated = await adminGetJob(job.id);
        setJob(updated);
        if (updated.status === "done" && selected) {
          // Refresh folder photo counts once processing finishes.
          openEvent(selected.slug);
        }
      } catch {
        /* Transient polling error; keep trying. */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [job, selected]);

  function logout() {
    clearToken();
    router.replace("/admin/login");
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <button
          type="button"
          onClick={logout}
          className="text-sm font-medium text-neutral-500 hover:text-neutral-900"
        >
          Log out
        </button>
      </header>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="grid gap-6 md:grid-cols-[280px_1fr]">
        {/* Left: events list + create. */}
        <section className="space-y-4">
          <form
            onSubmit={onCreateEvent}
            className="space-y-2 rounded-xl bg-white p-4 shadow-sm"
          >
            <h2 className="font-semibold">New event</h2>
            <input
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              required
            />
            <input
              placeholder="slug-like-this"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              required
            />
            <input
              type="date"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
            />
            <button
              type="submit"
              className="w-full rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark"
            >
              Create event
            </button>
          </form>

          <div className="rounded-xl bg-white p-4 shadow-sm">
            <h2 className="mb-2 font-semibold">Events</h2>
            <ul className="space-y-1">
              {events.map((ev) => (
                <li key={ev.id}>
                  <button
                    type="button"
                    onClick={() => openEvent(ev.slug)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition hover:bg-neutral-100 ${
                      selected?.id === ev.id ? "bg-neutral-100 font-medium" : ""
                    }`}
                  >
                    {ev.title}
                    <span className="block text-xs text-neutral-400">
                      /e/{ev.slug}
                    </span>
                  </button>
                </li>
              ))}
              {events.length === 0 && (
                <li className="text-sm text-neutral-400">No events yet.</li>
              )}
            </ul>
          </div>
        </section>

        {/* Right: selected event detail. */}
        <section>
          {!selected ? (
            <p className="py-16 text-center text-neutral-400">
              Select or create an event.
            </p>
          ) : (
            <div className="space-y-6">
              <div className="rounded-xl bg-white p-5 shadow-sm">
                <h2 className="text-xl font-semibold">{selected.title}</h2>
                <p className="text-sm text-neutral-500">
                  Guest link: <code>/e/{selected.slug}</code>
                </p>
              </div>

              <div className="rounded-xl bg-white p-5 shadow-sm">
                <h3 className="mb-3 font-semibold">Folders</h3>
                <ul className="mb-3 flex flex-wrap gap-2">
                  {selected.folders.map((f: Folder) => (
                    <li
                      key={f.id}
                      className="rounded-full bg-neutral-100 px-3 py-1 text-sm"
                    >
                      {f.name}{" "}
                      <span className="text-neutral-400">({f.photo_count})</span>
                    </li>
                  ))}
                  {selected.folders.length === 0 && (
                    <li className="text-sm text-neutral-400">No folders yet.</li>
                  )}
                </ul>
                <form onSubmit={onCreateFolder} className="flex gap-2">
                  <input
                    placeholder="Folder name (e.g. חתונה)"
                    value={folderName}
                    onChange={(e) => setFolderName(e.target.value)}
                    className="flex-1 rounded-lg border px-3 py-2 text-sm"
                    required
                  />
                  <button
                    type="submit"
                    className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark"
                  >
                    Add
                  </button>
                </form>
              </div>

              <div className="rounded-xl bg-white p-5 shadow-sm">
                <h3 className="mb-3 font-semibold">Bulk upload</h3>
                <select
                  value={uploadFolder}
                  onChange={(e) => setUploadFolder(e.target.value)}
                  className="mb-3 w-full rounded-lg border px-3 py-2 text-sm"
                >
                  <option value="">Select a folder…</option>
                  {selected.folders.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={!uploadFolder || uploading}
                  onChange={(e) => onUpload(e.target.files)}
                  className="block w-full text-sm"
                />
                {uploading && (
                  <p className="mt-2 text-sm text-neutral-500">Uploading…</p>
                )}
                {uploadInfo && (
                  <p className="mt-2 text-sm text-green-600">{uploadInfo}</p>
                )}
              </div>

              <div className="rounded-xl bg-white p-5 shadow-sm">
                <h3 className="mb-1 font-semibold">Bulk ZIP upload</h3>
                <p className="mb-3 text-xs text-neutral-500">
                  Upload a .zip of up to 700+ photos. It&apos;s processed in the
                  background under an &quot;Uploads&quot; folder.
                </p>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  disabled={zipUploading}
                  onChange={(e) => onUploadZip(e.target.files)}
                  className="block w-full text-sm"
                />
                {zipUploading && (
                  <p className="mt-2 text-sm text-neutral-500">
                    Uploading ZIP…
                  </p>
                )}

                {job && (
                  <div className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm">
                    {job.status === "pending" && (
                      <p className="text-neutral-600">
                        Zip received, processing in background…
                      </p>
                    )}
                    {job.status === "processing" && (
                      <>
                        <p className="mb-2 text-neutral-600">
                          Processing {job.processed}/{job.total || "…"} photos
                          {job.failed > 0 && ` (${job.failed} failed)`}
                        </p>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
                          <div
                            className="h-full bg-brand transition-all"
                            style={{
                              width: `${
                                job.total
                                  ? Math.round(
                                      (job.processed / job.total) * 100,
                                    )
                                  : 5
                              }%`,
                            }}
                          />
                        </div>
                      </>
                    )}
                    {job.status === "done" && (
                      <p className="text-green-600">
                        {job.message ?? "Done."}
                      </p>
                    )}
                    {job.status === "failed" && (
                      <p className="text-red-600">
                        {job.message ?? "ZIP processing failed."}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
