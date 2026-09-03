import Link from "next/link";

// Landing page with quick links.
export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-8 px-6 text-center">
      <div className="space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">photoEvent</h1>
        <p className="text-neutral-600">
          Share event photos and let guests find themselves with a selfie.
        </p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Link
          href="/admin"
          className="rounded-lg bg-brand px-6 py-3 font-medium text-white transition hover:bg-brand-dark"
        >
          Admin Portal
        </Link>
      </div>
      <p className="text-sm text-neutral-400">
        Guests: open your unique event link, e.g. <code>/e/wedding-david-sarah</code>
      </p>
    </main>
  );
}
