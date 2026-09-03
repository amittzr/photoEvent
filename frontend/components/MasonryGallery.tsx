"use client";

import { useState } from "react";

import type { Photo } from "@/lib/types";
import Lightbox from "./Lightbox";
import PhotoCard from "./PhotoCard";

interface MasonryGalleryProps {
  photos: Photo[];
}

// Responsive masonry grid with an integrated lightbox.
export default function MasonryGallery({ photos }: MasonryGalleryProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (photos.length === 0) {
    return (
      <p className="py-16 text-center text-neutral-400">No photos here yet.</p>
    );
  }

  return (
    <>
      <div className="masonry">
        {photos.map((photo, index) => (
          <PhotoCard
            key={photo.id}
            photo={photo}
            onOpen={() => setActiveIndex(index)}
          />
        ))}
      </div>

      {activeIndex !== null && (
        <Lightbox
          photos={photos}
          index={activeIndex}
          onClose={() => setActiveIndex(null)}
          onNavigate={setActiveIndex}
        />
      )}
    </>
  );
}
