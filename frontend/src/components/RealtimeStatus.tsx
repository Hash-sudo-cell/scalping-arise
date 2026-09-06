/**
 * Scalping Arise — Realtime Status Indicator
 *
 * Shows WebSocket connection state and last event count.
 * Placed in the header for visibility.
 */

'use client';

import { useRealtime } from "@/contexts/RealtimeContext";

const statusColors: Record<string, string> = {
  connected: "#22c55e",
  connecting: "#f59e0b",
  disconnected: "#6b7280",
  error: "#ef4444",
};

const statusLabels: Record<string, string> = {
  connected: "LIVE",
  connecting: "CONNECTING",
  disconnected: "OFFLINE",
  error: "ERROR",
};

export default function RealtimeStatus() {
  const { connectionState, events } = useRealtime();

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: statusColors[connectionState] || "#6b7280",
          display: "inline-block",
        }}
      />
      <span style={{ color: statusColors[connectionState], fontWeight: 600 }}>
        {statusLabels[connectionState]}
      </span>
      {events.length > 0 && (
        <span style={{ color: "#9ca3af" }}>
          {events.length} events
        </span>
      )}

      <style jsx>{`
        div {
          padding: 4px 12px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
      `}</style>
    </div>
  );
}
