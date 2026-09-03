"use client";

import { assetUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";

interface PhotoCardProps {
  photo: Photo;
  onOpen: () => void;
}

// A single lazy-loaded thumbnail card in the masonry grid.
export default function PhotoCard({ photo, onOpen }: PhotoCardProps) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="block w-full overflow-hidden rounded-lg bg-neutral-200 shadow-sm transition hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand"
      aria-label="Open photo"
    >
      {/* Native lazy loading keeps the gallery fast. */}
      <img
        src={assetUrl(photo.thumb_url)}
        alt=""
        loading="lazy"
        decoding="async"
        className="w-full object-cover"
      />
    </button>
  );
}
