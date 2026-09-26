import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SwingDesk | Ergonomic desk planning",
  description:
    "Plan, compare, and request ergonomic standing desk setups for focused teams."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
