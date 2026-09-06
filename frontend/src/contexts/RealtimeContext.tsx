/**
 * Scalping Arise — Realtime Context
 *
 * Provides a WebSocket connection to the backend event bus.
 * Emits decision updates, emergency events, and system status
 * in real-time. Auto-reconnects on disconnect.
 */

'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

export type RealtimeEvent = {
  type: string;
  timestamp?: string;
  [key: string]: unknown;
};

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

interface RealtimeContextValue {
  connectionState: ConnectionState;
  lastEvent: RealtimeEvent | null;
  events: RealtimeEvent[];
  subscribe: (callback: (event: RealtimeEvent) => void) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

const MAX_EVENTS = 200;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const [events, setEvents] = useState<RealtimeEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Set<(event: RealtimeEvent) => void>>(new Set());
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('connecting');

    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const wsUrl = baseUrl.replace(/^http/, 'ws') + '/api/v1/ws';

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionState('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data: RealtimeEvent = JSON.parse(event.data);
          setLastEvent(data);
          setEvents((prev) => [data, ...prev].slice(0, MAX_EVENTS));

          // Notify subscribers
          listenersRef.current.forEach((cb) => {
            try { cb(data); } catch { /* subscriber error */ }
          });
        } catch { /* parse error */ }
      };

      ws.onclose = () => {
        setConnectionState('disconnected');
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        setConnectionState('error');
      };
    } catch {
      setConnectionState('error');
      scheduleReconnect();
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) return;

    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, reconnectAttemptsRef.current),
      RECONNECT_MAX_MS
    );
    reconnectAttemptsRef.current += 1;

    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, delay);
  }, [connect]);

  const subscribe = useCallback((callback: (event: RealtimeEvent) => void) => {
    listenersRef.current.add(callback);
    return () => {
      listenersRef.current.delete(callback);
    };
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return (
    <RealtimeContext.Provider value={{ connectionState, lastEvent, events, subscribe }}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime(): RealtimeContextValue {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error('useRealtime must be used within RealtimeProvider');
  return ctx;
}
