import { useEffect, useRef } from "react";
import { useLiveTimingStore } from "../stores/liveTimingStore";

const LIVE_URL = import.meta.env.VITE_LIVE_URL ?? "";

export function useSocket() {
  const setConnected = useLiveTimingStore((s) => s.setConnected);
  const setInitialState = useLiveTimingStore((s) => s.setInitialState);
  const applyUpdate = useLiveTimingStore((s) => s.applyUpdate);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const sse = new EventSource(`${LIVE_URL}/api/realtime`);
    sourceRef.current = sse;

    sse.addEventListener("initial", (e: MessageEvent) => {
      setInitialState(JSON.parse(e.data));
      setConnected(true);
    });

    sse.addEventListener("update", (e: MessageEvent) => {
      applyUpdate(JSON.parse(e.data));
    });

    sse.onerror = () => setConnected(false);
    sse.onopen = () => setConnected(true);

    return () => {
      sse.close();
      sourceRef.current = null;
    };
    // Store actions are stable refs — safe to list once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
