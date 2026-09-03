"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { searchBySelfie } from "@/lib/api";
import type { PhotoMatch } from "@/lib/types";
import MasonryGallery from "./MasonryGallery";

interface FindMyPhotosProps {
  slug: string;
}

// "idle" -> choose method; "camera" -> live webcam preview; then search states.
type Status = "idle" | "camera" | "searching" | "done" | "error";

// Floating action + modal for selfie-based photo search.
// The selfie is sent to the backend for a one-off search and never stored.
export default function FindMyPhotos({ slug }: FindMyPhotosProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [matches, setMatches] = useState<PhotoMatch[]>([]);
  const [message, setMessage] = useState<string>("");

  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Stop the webcam and release the device. Safe to call multiple times.
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  async function runSearch(file: File | Blob) {
    setStatus("searching");
    setMessage("");
    try {
      // Wrap a Blob (from the canvas snapshot) into a File for the form upload.
      const selfie =
        file instanceof File
          ? file
          : new File([file], "selfie.jpg", { type: "image/jpeg" });
      const res = await searchBySelfie(slug, selfie);
      setMatches(res.matches);
      if (res.faces_detected_in_selfie === 0) {
        setMessage("No face detected in your photo. Try a clearer selfie.");
      } else if (res.matches.length === 0) {
        setMessage("No matching photos found for this event.");
      }
      setStatus("done");
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Search failed.");
    }
  }

  // Request the webcam and show the live preview. Works on desktop and mobile.
  async function startCamera() {
    setMessage("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setMessage(
        "Live camera isn't available in this browser. Please upload a photo instead.",
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      setStatus("camera");
    } catch {
      setMessage(
        "Couldn't access the camera. Check permissions, or upload a photo instead.",
      );
    }
  }

  // Attach the stream to the <video> element once it is rendered.
  useEffect(() => {
    if (status === "camera" && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {
        /* Autoplay can be interrupted; ignore. */
      });
    }
  }, [status]);

  // Capture the current video frame to a JPEG blob and run the search.
  function capturePhoto() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    stopCamera();
    canvas.toBlob(
      (blob) => {
        if (blob) runSearch(blob);
      },
      "image/jpeg",
      0.92,
    );
  }

  function reset() {
    stopCamera();
    setStatus("idle");
    setMatches([]);
    setMessage("");
    if (inputRef.current) inputRef.current.value = "";
  }

  function close() {
    stopCamera();
    setOpen(false);
    reset();
  }

  // Ensure the camera is released if the component unmounts while streaming.
  useEffect(() => stopCamera, [stopCamera]);

  return (
    <>
      {/* Prominent floating action button. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 rounded-full bg-brand px-6 py-3.5 font-semibold text-white shadow-lg transition hover:bg-brand-dark"
      >
        Find My Photos 🤳
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white">
          <header className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-lg font-semibold">Find My Photos</h2>
            <button
              type="button"
              onClick={close}
              className="rounded-full p-2 text-neutral-500 hover:bg-neutral-100"
              aria-label="Close"
            >
              ✕
            </button>
          </header>

          <div className="flex-1 overflow-y-auto p-4">
            {status === "idle" && (
              <div className="mx-auto flex max-w-sm flex-col items-center gap-4 py-12 text-center">
                <p className="text-neutral-600">
                  Take a selfie with your camera or upload a photo. We match it
                  against this event&apos;s photos and never store your selfie.
                </p>

                <button
                  type="button"
                  onClick={startCamera}
                  className="w-full rounded-lg bg-brand px-6 py-3 font-medium text-white transition hover:bg-brand-dark"
                >
                  Take a photo 📷
                </button>

                <div className="flex w-full items-center gap-3 text-xs text-neutral-400">
                  <span className="h-px flex-1 bg-neutral-200" />
                  or
                  <span className="h-px flex-1 bg-neutral-200" />
                </div>

                <input
                  ref={inputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) runSearch(file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="w-full rounded-lg border border-neutral-300 px-6 py-3 font-medium text-neutral-700 transition hover:bg-neutral-50"
                >
                  Upload a photo
                </button>

                {message && (
                  <p className="text-sm text-red-500">{message}</p>
                )}
              </div>
            )}

            {status === "camera" && (
              <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-4">
                <div className="w-full overflow-hidden rounded-xl bg-black">
                  {/* Mirror the preview so it feels natural, like a mirror. */}
                  <video
                    ref={videoRef}
                    playsInline
                    muted
                    className="w-full -scale-x-100"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={capturePhoto}
                    className="rounded-lg bg-brand px-6 py-3 font-medium text-white transition hover:bg-brand-dark"
                  >
                    Capture &amp; search
                  </button>
                  <button
                    type="button"
                    onClick={reset}
                    className="rounded-lg border border-neutral-300 px-6 py-3 font-medium text-neutral-700 transition hover:bg-neutral-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {status === "searching" && (
              <p className="py-16 text-center text-neutral-500">
                Searching for your photos…
              </p>
            )}

            {(status === "done" || status === "error") && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-neutral-600">
                    {status === "done" && matches.length > 0
                      ? `Found ${matches.length} photo(s)`
                      : message}
                  </p>
                  <button
                    type="button"
                    onClick={reset}
                    className="text-sm font-medium text-brand hover:underline"
                  >
                    Try another selfie
                  </button>
                </div>
                {matches.length > 0 && (
                  <MasonryGallery photos={matches.map((m) => m.photo)} />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
