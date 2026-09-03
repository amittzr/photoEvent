import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "photoEvent",
  description: "Event photo sharing with AI facial recognition.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
