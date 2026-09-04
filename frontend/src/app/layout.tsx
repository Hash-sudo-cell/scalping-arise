import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scalping Arise",
  description:
    "XAU/USD Multi-Timeframe, Multi-Strategy Scalping Signal Intelligence System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
