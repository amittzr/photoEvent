"use client";

import { useCallback, useEffect } from "react";

import { assetUrl, downloadUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";

interface LightboxProps {
  photos: Photo[];
  index: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

// Fullscreen image viewer with keyboard navigation and a download action.
export default function Lightbox({
  photos,
  index,
  onClose,
  onNavigate,
}: LightboxProps) {
  const photo = photos[index];

  const prev = useCallback(() => {
    onNavigate((index - 1 + photos.length) % photos.length);
  }, [index, photos.length, onNavigate]);

  const next = useCallback(() => {
    onNavigate((index + 1) % photos.length);
  }, [index, photos.length, onNavigate]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, prev, next]);

  if (!photo) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        aria-label="Close"
      >
        ✕
      </button>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          prev();
        }}
        className="absolute left-4 rounded-full bg-white/10 p-3 text-white hover:bg-white/20"
        aria-label="Previous photo"
      >
        ‹
      </button>

      <div className="flex max-h-full max-w-full flex-col items-center gap-4">
        {/* Show the thumbnail for fast display; full-res is available via download. */}
        <img
          src={assetUrl(photo.thumb_url)}
          alt=""
          className="max-h-[80vh] max-w-full rounded-lg object-contain"
          onClick={(e) => e.stopPropagation()}
        />
        <a
          href={downloadUrl(photo.id)}
          onClick={(e) => e.stopPropagation()}
          className="rounded-lg bg-brand px-5 py-2.5 font-medium text-white transition hover:bg-brand-dark"
        >
          Download full resolution
        </a>
      </div>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          next();
        }}
        className="absolute right-4 rounded-full bg-white/10 p-3 text-white hover:bg-white/20"
        aria-label="Next photo"
      >
        ›
      </button>
    </div>
  );
}
