"use client";

import { useRef, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";

import type { EventDetail } from "@/lib/types";

interface ShareEventModalProps {
  event: EventDetail;
  onClose: () => void;
}

// High-res multiplier for the downloadable/print QR (on-screen QR stays small).
const QR_DOWNLOAD_SIZE = 1024;

// Share modal: guest URL with copy-to-clipboard, a QR code, a high-res PNG
// download, and a printable card preview.
export default function ShareEventModal({ event, onClose }: ShareEventModalProps) {
  const [copied, setCopied] = useState(false);
  // Hidden high-res canvas used only to export a crisp PNG for printing.
  const hiddenQrRef = useRef<HTMLDivElement>(null);

  // Build the absolute public guest URL from the current browser origin.
  const guestUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/e/${event.slug}`
      : `/e/${event.slug}`;

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(guestUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for browsers without the async clipboard API.
      const ta = document.createElement("textarea");
      ta.value = guestUrl;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function downloadQr() {
    // Grab the hidden high-res canvas and save it as a PNG.
    const canvas = hiddenQrRef.current?.querySelector("canvas");
    if (!canvas) return;
    const url = canvas.toDataURL("image/png");
    const a = document.createElement("a");
    a.href = url;
    a.download = `${event.slug}-qr.png`;
    a.click();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Share Event</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-neutral-500 hover:bg-neutral-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Guest URL + copy button. */}
        <label className="text-sm font-medium text-neutral-700">
          Guest link
        </label>
        <div className="mb-4 mt-1 flex gap-2">
          <input
            readOnly
            value={guestUrl}
            className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm"
            onFocus={(e) => e.target.select()}
          />
          <button
            type="button"
            onClick={copyLink}
            className="whitespace-nowrap rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark"
          >
            {copied ? "Copied ✓" : "Copy Link"}
          </button>
        </div>

        {/* Printable card preview with the on-screen QR. */}
        <div className="rounded-xl border border-neutral-200 p-5 text-center">
          <p className="text-lg font-bold">{event.title}</p>
          {event.event_date && (
            <p className="mb-3 text-sm text-neutral-500">{event.event_date}</p>
          )}
          <div className="flex justify-center">
            <QRCodeCanvas
              value={guestUrl}
              size={200}
              level="M"
              includeMargin
            />
          </div>
          <p className="mt-3 text-sm text-neutral-600">
            Scan to view &amp; find your photos
          </p>
        </div>

        <button
          type="button"
          onClick={downloadQr}
          className="mt-4 w-full rounded-lg bg-brand px-4 py-2.5 font-medium text-white transition hover:bg-brand-dark"
        >
          Download QR Code (high-res PNG)
        </button>

        {/* Off-screen high-res QR used only for the PNG export. */}
        <div ref={hiddenQrRef} className="pointer-events-none absolute -left-[9999px]">
          <QRCodeCanvas
            value={guestUrl}
            size={QR_DOWNLOAD_SIZE}
            level="H"
            includeMargin
          />
        </div>
      </div>
    </div>
  );
}
