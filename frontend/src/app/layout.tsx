import type { Metadata } from "next";
import { InstrumentProvider } from "@/contexts/InstrumentContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scalping Arise",
  description:
    "Multi-Timeframe, Multi-Strategy Scalping Signal Intelligence System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <InstrumentProvider>{children}</InstrumentProvider>
      </body>
    </html>
  );
}
