import React, { useState, useRef, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import LiveTrackMap from "../components/live/LiveTrackMap";
import LiveTimingTable from "../components/live/LiveTimingTable";
import NextRaceInfo from "../components/NextRaceInfo";
import { useSocket } from "../hooks/useSocket";
import { useLiveTimingStore } from "../stores/liveTimingStore";
import "../styles/Live.css";

export default function Live() {
  useSocket();

  const connected = useLiveTimingStore((s) => s.connected);
  const sessionInfo = useLiveTimingStore((s) => s.sessionInfo);
  const sessionStatus = useLiveTimingStore((s) => s.sessionStatus);

  const [sidebarWidth, setSidebarWidth] = useState<number>(360);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(360);

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      isDraggingRef.current = true;
      dragStartXRef.current = e.clientX;
      dragStartWidthRef.current = sidebarWidth;
    },
    [sidebarWidth]
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      const next = Math.max(260, Math.min(520, dragStartWidthRef.current + delta));
      setSidebarWidth(next);
    };

    const handleMouseUp = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const hasActiveSession =
    connected &&
    !!sessionInfo &&
    sessionStatus !== "Finished" &&
    sessionStatus !== "Inactive";

  return (
    <div className="live-page">
      <header className="live-header">
        <div className="live-header-left">
          <Link to="/" className="live-back-link">
            &#x2190; Home
          </Link>
          <h1 className="live-title">
            <span className="f1">F1</span> LIVE TIMING
          </h1>
          {sessionInfo && (
            <span className="live-session-badge">
              {sessionInfo.Meeting?.Circuit?.ShortName ?? ""} &middot;{" "}
              {sessionInfo.Name}
            </span>
          )}
        </div>
        <div className="live-header-right">
          <span
            className={`live-status ${connected ? "connected" : "disconnected"}`}
          >
            <span className="status-dot" />
            {connected ? "Live" : "Connecting\u2026"}
          </span>
        </div>
      </header>

      {hasActiveSession ? (
        <div className="live-content live-content-active">
          <div className="live-left-pane" style={{ width: sidebarWidth }}>
            <LiveTimingTable />
          </div>
          <div
            className="live-resize-handle"
            onMouseDown={onResizeMouseDown}
          />
          <div className="live-right-pane">
            <LiveTrackMap />
          </div>
        </div>
      ) : (
        <div className="live-content">
          <div className="live-standby">
            <div className="live-standby-card">
              <h2 className="live-standby-title">
                No live session is currently active
              </h2>
              <p className="live-standby-subtitle">
                Countdown to the next Grand Prix
              </p>
              <NextRaceInfo showCountdown />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
