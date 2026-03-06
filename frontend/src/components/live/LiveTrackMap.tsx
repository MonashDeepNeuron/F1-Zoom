import { useRef, useEffect, useState, useCallback } from "react";
import { useLiveTimingStore } from "../../stores/liveTimingStore";
import type { TimingDataDriver, Sector, Segment } from "../../types/liveTiming";

interface Pt {
  x: number;
  y: number;
}

interface PosSnapshot {
  x: number;
  y: number;
  t: number;
}

function parseTrackData(raw: string): Pt[] {
  let csv = raw;
  const m = raw.match(/`([\s\S]*)`/);
  if (m) csv = m[1];
  const pts: Pt[] = [];
  for (const line of csv.trim().split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const p = t.split(",");
    if (p.length >= 2) {
      const x = parseFloat(p[0]);
      const y = parseFloat(p[1]);
      if (!isNaN(x) && !isNaN(y)) pts.push({ x, y });
    }
  }
  return pts;
}

/**
 * Find highest completed segment and total segment count from sector data.
 * Sectors have variable segment counts (e.g. 9, 5, 10 for Melbourne = 24 total).
 * Returns { highest: absolute index of last completed segment, total: total segments }.
 */
function getSegmentProgress(
  sectors: Sector[] | Record<string, Sector>
): { highest: number; total: number } {
  const sectorEntries: [number, Sector][] = Array.isArray(sectors)
    ? sectors.map((s, i) => [i, s])
    : Object.entries(sectors)
        .sort(([a], [b]) => parseInt(a) - parseInt(b))
        .map(([k, v]) => [parseInt(k), v]);

  let total = 0;
  let highest = -1;
  let offset = 0;

  for (const [, sector] of sectorEntries) {
    if (!sector?.Segments) continue;

    const segs: (Segment | null)[] = Array.isArray(sector.Segments)
      ? sector.Segments
      : Object.entries(sector.Segments)
          .sort(([a], [b]) => parseInt(a) - parseInt(b))
          .map(([, v]) => v);

    for (let g = 0; g < segs.length; g++) {
      const seg = segs[g];
      if (seg && seg.Status !== 0) {
        const absolute = offset + g;
        if (absolute > highest) highest = absolute;
      }
    }
    offset += segs.length;
    total += segs.length;
  }

  return { highest, total: total || 24 };
}

function interpolateTrack(pts: Pt[], progress: number): Pt {
  const n = pts.length;
  const clamped = Math.max(0, Math.min(progress, 0.9999));
  const idxF = clamped * (n - 1);
  const i = Math.floor(idxF);
  const frac = idxF - i;
  if (i >= n - 1) return pts[n - 1];
  return {
    x: pts[i].x + frac * (pts[i + 1].x - pts[i].x),
    y: pts[i].y + frac * (pts[i + 1].y - pts[i].y),
  };
}

export default function LiveTrackMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trackRef = useRef<Pt[]>([]);
  const sizeRef = useRef({ w: 0, h: 0 });
  const [loaded, setLoaded] = useState(false);

  const prevProgressRef = useRef<Record<string, number>>({});
  const targetProgressRef = useRef<Record<string, number>>({});
  const lastUpdateRef = useRef<Record<string, number>>({});

  const posBufferRef = useRef<Record<string, { prev: PosSnapshot; curr: PosSnapshot }>>({});

  useEffect(() => {
    fetch("/circuit_3d/TrackCoordinateJS/Melbourne.js")
      .then((r) => r.text())
      .then((data) => {
        trackRef.current = parseTrackData(data);
        setLoaded(true);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      const dpr = window.devicePixelRatio;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      sizeRef.current = { w: width, h: height };
    });
    observer.observe(canvas.parentElement!);
    return () => observer.disconnect();
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const pts = trackRef.current;
    if (!canvas || !pts.length) return;

    const ctx = canvas.getContext("2d")!;
    const { positions, timingData, driverList } = useLiveTimingStore.getState();
    const now = performance.now();
    const dpr = window.devicePixelRatio;
    const w = sizeRef.current.w;
    const h = sizeRef.current.h;
    if (w === 0 || h === 0) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // compute bounding box for track-to-canvas mapping
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const p of pts) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    const pad = 40;
    const scale = Math.min(
      (w - pad * 2) / (maxX - minX),
      (h - pad * 2) / (maxY - minY)
    );
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    const toC = (x: number, y: number) => ({
      cx: (x - cx) * scale + w / 2,
      cy: (y - cy) * scale + h / 2,
    });

    // draw track glow
    ctx.beginPath();
    pts.forEach((p, i) => {
      const { cx: px, cy: py } = toC(p.x, p.y);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 22;
    ctx.stroke();

    // draw track line
    ctx.strokeStyle = "rgba(255,255,255,0.26)";
    ctx.lineWidth = 4.5;
    ctx.stroke();

    // choose position source: raw XY positions (from mock/Position.z) or
    // estimated from microsector progress (live F1 where Position data unavailable)
    const hasRawPositions = Object.keys(positions).length > 0;
    const smoothMs = 350;

    type DriverPos = { num: string; x: number; y: number; color: string; tla: string };
    const driverPositions: DriverPos[] = [];

    if (hasRawPositions) {
      const MAX_EXTRAPOLATE = 1.5;

      for (const [num, pos] of Object.entries(positions)) {
        const drv = driverList[num];
        const buf = posBufferRef.current[num];
        const snap: PosSnapshot = { x: pos.X, y: pos.Y, t: now };

        if (!buf) {
          posBufferRef.current[num] = { prev: snap, curr: snap };
        } else if (buf.curr.x !== pos.X || buf.curr.y !== pos.Y) {
          posBufferRef.current[num] = { prev: buf.curr, curr: snap };
        }

        const { prev, curr } = posBufferRef.current[num];
        const interval = curr.t - prev.t;
        let t: number;
        if (interval > 0) {
          t = Math.min((now - curr.t) / interval + 1, MAX_EXTRAPOLATE);
        } else {
          t = 1;
        }

        const lerpX = prev.x + (curr.x - prev.x) * t;
        const lerpY = prev.y + (curr.y - prev.y) * t;

        const { cx: dx, cy: dy } = toC(lerpX, lerpY);
        driverPositions.push({
          num,
          x: dx,
          y: dy,
          color: `#${drv?.TeamColour ?? "ffffff"}`,
          tla: drv?.Tla ?? num,
        });
      }
    } else {
      // derive positions from microsector data
      for (const [num, td] of Object.entries(timingData) as [string, TimingDataDriver][]) {
        if (td.InPit || td.Retired) continue;
        if (!td.Sectors) continue;

        const { highest: seg, total: totalSegs } = getSegmentProgress(td.Sectors);
        if (seg < 0) continue;

        const progress = Math.min((seg + 1) / totalSegs, 0.9999);

        // smooth animation between segment steps
        const prev = targetProgressRef.current[num];
        if (prev === undefined || prev !== progress) {
          prevProgressRef.current[num] = prev ?? progress;
          targetProgressRef.current[num] = progress;
          lastUpdateRef.current[num] = now;
        }

        const start = lastUpdateRef.current[num] ?? now;
        let t = (now - start) / smoothMs;
        if (t > 1) t = 1;

        const fromP = prevProgressRef.current[num] ?? progress;
        let delta = progress - fromP;
        // handle wrap-around (sector 3 segment 7 → sector 0 segment 0)
        if (delta < -0.5) delta += 1;
        if (delta > 0.5) delta -= 1;
        let interp = fromP + delta * t;
        if (interp < 0) interp += 1;
        if (interp >= 1) interp -= 1;

        const trackPt = interpolateTrack(pts, interp);
        const { cx: dx, cy: dy } = toC(trackPt.x, trackPt.y);
        const drv = driverList[num];

        driverPositions.push({
          num,
          x: dx,
          y: dy,
          color: `#${drv?.TeamColour ?? "ffffff"}`,
          tla: drv?.Tla ?? num,
        });
      }
    }

    // draw car dots
    for (const dp of driverPositions) {
      // glow
      ctx.beginPath();
      ctx.arc(dp.x, dp.y, 13, 0, Math.PI * 2);
      ctx.fillStyle = dp.color + "30";
      ctx.fill();

      // dot
      ctx.beginPath();
      ctx.arc(dp.x, dp.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = dp.color;
      ctx.fill();

      // label
      ctx.font = "bold 12px monospace";
      const textWidth = ctx.measureText(dp.tla).width;
      const paddingX = 6;
      const paddingY = 3;
      const labelX = dp.x + 16;
      const labelY = dp.y + 4;

      ctx.fillStyle = "rgba(0,0,0,0.78)";
      ctx.beginPath();
      ctx.roundRect(
        labelX - paddingX,
        labelY - 11,
        textWidth + paddingX * 2,
        16 + paddingY,
        8
      );
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.96)";
      ctx.fillText(dp.tla, labelX, labelY);
    }

  }, []);

  useEffect(() => {
    if (!loaded) return;
    let id: number;
    const loop = () => {
      draw();
      id = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(id);
  }, [loaded, draw]);

  return (
    <div className="track-map-container">
      <canvas ref={canvasRef} className="track-map-canvas" />
    </div>
  );
}
