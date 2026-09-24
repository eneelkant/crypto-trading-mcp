import { useEffect, useRef, useState } from "react";
import type { DashboardEvent } from "../api/client";

export function useEventStream(onEvent?: (event: DashboardEvent) => void) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<DashboardEvent[]>([]);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        timer = window.setTimeout(connect, 1500);
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === "event" && data.event) {
            const event = data.event as DashboardEvent;
            setEvents((prev) => [event, ...prev].slice(0, 200));
            onEventRef.current?.(event);
          }
        } catch {
          /* ignore malformed */
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { connected, events };
}
