"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";

import { getEvent, getFolderPhotos } from "@/lib/api";
import type { EventDetail, Photo } from "@/lib/types";
import FindMyPhotos from "@/components/FindMyPhotos";
import FolderTabs from "@/components/FolderTabs";
import MasonryGallery from "@/components/MasonryGallery";

// How many photos to fetch per page/batch (infinite scroll).
const PAGE_SIZE = 30;

// Guest-facing event gallery. Mobile-first, folder tabs + masonry + selfie search.
// In Next.js 15+, route `params` is a Promise and must be unwrapped with React.use().
export default function EventPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination state.
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Refs drive pagination so overlapping/StrictMode-duplicated calls can't race.
  // `offsetRef` is the source of truth for the next fetch offset; `loadingRef`
  // is a synchronous in-flight guard (state updates are async and can double-fire).
  const offsetRef = useRef(0);
  const loadingRef = useRef(false);
  const hasMoreRef = useRef(true);

  // Merge new photos, dropping any whose id we already have. This makes the
  // gallery resilient to duplicate/overlapping fetches (no photo shown twice).
  const mergePhotos = useCallback((prev: Photo[], batch: Photo[]): Photo[] => {
    const seen = new Set(prev.map((p) => p.id));
    const additions = batch.filter((p) => !seen.has(p.id));
    return additions.length ? [...prev, ...additions] : prev;
  }, []);

  // Load the event once and select the first folder.
  useEffect(() => {
    getEvent(slug)
      .then((data) => {
        setEvent(data);
        if (data.folders.length > 0) setActiveFolder(data.folders[0].id);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [slug]);

  // Reset and load the first page whenever the active folder changes.
  useEffect(() => {
    if (!activeFolder) return;
    let cancelled = false;

    // Reset pagination for the new folder.
    offsetRef.current = 0;
    hasMoreRef.current = true;
    loadingRef.current = true;
    setPhotos([]);
    setHasMore(true);

    getFolderPhotos(slug, activeFolder, PAGE_SIZE, 0)
      .then((batch) => {
        if (cancelled) return;
        offsetRef.current = batch.length;
        hasMoreRef.current = batch.length === PAGE_SIZE;
        setHasMore(hasMoreRef.current);
        setPhotos((prev) => mergePhotos(prev, batch));
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        loadingRef.current = false;
      });

    // If the folder changes (or StrictMode re-runs), ignore the stale response.
    return () => {
      cancelled = true;
    };
  }, [slug, activeFolder, mergePhotos]);

  // Fetch the next page and append it (deduplicated).
  const loadMore = useCallback(() => {
    if (!activeFolder || loadingRef.current || !hasMoreRef.current) return;
    loadingRef.current = true;
    setLoadingMore(true);
    getFolderPhotos(slug, activeFolder, PAGE_SIZE, offsetRef.current)
      .then((batch) => {
        offsetRef.current += batch.length;
        hasMoreRef.current = batch.length === PAGE_SIZE;
        setHasMore(hasMoreRef.current);
        setPhotos((prev) => mergePhotos(prev, batch));
      })
      .catch((err) => setError(err.message))
      .finally(() => {
        loadingRef.current = false;
        setLoadingMore(false);
      });
  }, [slug, activeFolder, mergePhotos]);

  // Trigger loadMore when the sentinel scrolls into view.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore]);

  if (loading) {
    return <p className="py-24 text-center text-neutral-500">Loading…</p>;
  }
  if (error || !event) {
    return (
      <p className="py-24 text-center text-red-500">
        {error ?? "Event not found."}
      </p>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-6xl pb-28">
      <header className="sticky top-0 z-30 border-b bg-white/90 px-4 py-4 backdrop-blur">
        <h1 className="text-2xl font-bold tracking-tight">{event.title}</h1>
        {event.event_date && (
          <p className="text-sm text-neutral-500">{event.event_date}</p>
        )}
        <FolderTabs
          folders={event.folders}
          activeId={activeFolder}
          onSelect={setActiveFolder}
        />
      </header>

      <div className="px-4 py-4">
        <MasonryGallery photos={photos} />

        {/* Infinite-scroll sentinel + loading indicator. */}
        <div ref={sentinelRef} className="h-10" />
        {loadingMore && (
          <p className="py-4 text-center text-sm text-neutral-400">
            Loading more…
          </p>
        )}
      </div>

      <FindMyPhotos slug={slug} />
    </main>
  );
}
