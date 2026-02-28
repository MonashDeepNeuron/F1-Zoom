import { useRef, useEffect, useState, useCallback } from "react";
import { useLiveTimingStore } from "../../stores/liveTimingStore";

interface Pt {
  x: number;
  y: number;
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

export default function LiveTrackMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trackRef = useRef<Pt[]>([]);
  const sizeRef = useRef({ w: 0, h: 0 });
  const [loaded, setLoaded] = useState(false);
  const lastRawPositionsRef = useRef<Record<string, { X: number; Y: number }>>(
    {}
  );
  const prevPosRef = useRef<Record<string, { X: number; Y: number }>>({});
  const targetPosRef = useRef<Record<string, { X: number; Y: number }>>({});
  const lastUpdateRef = useRef<Record<string, number>>({});

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
    const { positions, driverList } = useLiveTimingStore.getState();
    const now = performance.now();
    const dpr = window.devicePixelRatio;
    const w = sizeRef.current.w;
    const h = sizeRef.current.h;
    if (w === 0 || h === 0) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

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

    // track glow (thicker for more presence)
    ctx.beginPath();
    pts.forEach((p, i) => {
      const { cx: px, cy: py } = toC(p.x, p.y);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 22;
    ctx.stroke();

    // track line
    ctx.strokeStyle = "rgba(255,255,255,0.26)";
    ctx.lineWidth = 4.5;
    ctx.stroke();

    // update interpolation targets when raw positions change
    const smoothMs = 300;
    const rawEntries = Object.entries(positions);
    const seen: Set<string> = new Set();
    for (const [num, pos] of rawEntries) {
      seen.add(num);
      const last = lastRawPositionsRef.current[num];
      if (!last || last.X !== pos.X || last.Y !== pos.Y) {
        const current =
          targetPosRef.current[num] ??
          last ??
          { X: pos.X, Y: pos.Y };
        prevPosRef.current[num] = current;
        targetPosRef.current[num] = { X: pos.X, Y: pos.Y };
        lastUpdateRef.current[num] = now;
        lastRawPositionsRef.current[num] = { X: pos.X, Y: pos.Y };
      }
    }
    // clean up drivers no longer present
    for (const key of Object.keys(lastRawPositionsRef.current)) {
      if (!seen.has(key)) {
        delete lastRawPositionsRef.current[key];
        delete prevPosRef.current[key];
        delete targetPosRef.current[key];
        delete lastUpdateRef.current[key];
      }
    }

    // car dots (larger icons + clearer labels, interpolated positions)
    const entries = rawEntries;
    for (const [num, pos] of entries) {
      const drv = driverList[num];
      const color = `#${drv?.TeamColour ?? "ffffff"}`;
      const start = lastUpdateRef.current[num] ?? now;
      const prev = prevPosRef.current[num] ?? { X: pos.X, Y: pos.Y };
      const target = targetPosRef.current[num] ?? { X: pos.X, Y: pos.Y };
      let t = (now - start) / smoothMs;
      if (t < 0) t = 0;
      if (t > 1) t = 1;
      const interpX = prev.X + (target.X - prev.X) * t;
      const interpY = prev.Y + (target.Y - prev.Y) * t;
      const { cx: dx, cy: dy } = toC(interpX, interpY);

      // glow
      ctx.beginPath();
      ctx.arc(dx, dy, 13, 0, Math.PI * 2);
      ctx.fillStyle = color + "30";
      ctx.fill();

      // dot
      ctx.beginPath();
      ctx.arc(dx, dy, 7, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // label
      if (drv?.Tla) {
        const label = drv.Tla;
        ctx.font = "bold 12px monospace";
        const textWidth = ctx.measureText(label).width;
        const paddingX = 6;
        const paddingY = 3;
        const labelX = dx + 16;
        const labelY = dy + 4;

        // background pill
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

        // text
        ctx.fillStyle = "rgba(255,255,255,0.96)";
        ctx.fillText(label, labelX, labelY);
      }
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
