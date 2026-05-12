import { useEffect, useRef, useState } from "react";
import { buildTrackMap, isOnTrack, MAP_SIZE, type TrackMap } from "./mode7";
import { useKeyboardControls } from "./useKeyboardControls";
import "../../styles/RaceMiniGame.css";

export interface RaceMiniGameProps {
  /** Track key matching a file under `/circuit_3d/TrackCoordinateJS`. */
  circuitName: string;
  /** Whether the game is mounted/active. Renders nothing visible while false. */
  isActive: boolean;
  /** Called when the user requests to exit the game (Esc or Exit button). */
  onExit?: () => void;
}

// ── Internal render resolution (pixelated; CSS-scaled to fill the stage) ──
const VIEW_W = 320;
const VIEW_H = 180;
const HORIZON_Y = Math.floor(VIEW_H * 0.45);

// Mode-7 camera tuning. Map is now 2048×2048 so the visible distance
// is bumped accordingly and the fog stretches further out.
const CAMERA_HEIGHT = 30;
const FOCAL_LENGTH = 110;
const FOG_DISTANCE = 1200;

// Driving model. Scaled up for the larger map so a lap still feels
// punchy. Speeds are in map-pixels per second.
const MAX_SPEED = 380;
const ACCEL = 340;
const BRAKE = 480;
const REVERSE_CAP_FRACTION = 0.4;
const FRICTION_PER_SEC = 0.45;
const TURN_RATE = 2.5;
const TURN_LOW_SPEED_FLOOR = 0.4;

// Wall-collision speed retention. Sliding along a single axis only
// trims a bit of speed; a head-on impact dumps almost everything.
const WALL_GLANCE_RETAIN = 0.55;
const WALL_HEAD_ON_RETAIN = 0.18;

// Pre-compute the sky band once — it never changes.
function buildSkyBuffer(): Uint8ClampedArray {
  const buf = new Uint8ClampedArray(VIEW_W * HORIZON_Y * 4);
  for (let y = 0; y < HORIZON_Y; y++) {
    const t = y / HORIZON_Y;
    const r = Math.round(20 + t * 40);
    const g = Math.round(8 + t * 28);
    const b = Math.round(12 + t * 50);
    for (let x = 0; x < VIEW_W; x++) {
      const i = (y * VIEW_W + x) * 4;
      buf[i] = r;
      buf[i + 1] = g;
      buf[i + 2] = b;
      buf[i + 3] = 255;
    }
  }
  return buf;
}

export default function RaceMiniGame({
  circuitName,
  isActive,
  onExit,
}: RaceMiniGameProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const controls = useKeyboardControls(isActive);

  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const trackMapRef = useRef<TrackMap | null>(null);
  const playerRef = useRef({
    x: MAP_SIZE / 2,
    z: MAP_SIZE / 2,
    heading: 0,
    speed: 0,
  });
  // Decays toward zero each frame; non-zero values flash the brake
  // light on the F1 sprite for a few frames after a wall hit.
  const wallFlashRef = useRef(0);

  // Fetch + bake the track map.
  useEffect(() => {
    if (!isActive) return;
    let cancelled = false;
    setStatus("loading");
    setError(null);

    fetch(`/circuit_3d/TrackCoordinateJS/${circuitName}.js`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load track: HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (cancelled) return;
        const built = buildTrackMap(text);
        if (!built) throw new Error("Track has too few points");
        trackMapRef.current = built;
        playerRef.current = {
          x: built.spawn.x,
          z: built.spawn.z,
          heading: built.spawn.heading,
          speed: 0,
        };
        wallFlashRef.current = 0;
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[RaceMiniGame] failed to load track", err);
        setError(err instanceof Error ? err.message : "Failed to load track");
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [isActive, circuitName]);

  // Esc to exit.
  useEffect(() => {
    if (!isActive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onExit?.();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isActive, onExit]);

  // Render loop.
  useEffect(() => {
    if (!isActive || status !== "ready") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = VIEW_W;
    canvas.height = VIEW_H;
    ctx.imageSmoothingEnabled = false;

    const map = trackMapRef.current;
    if (!map) return;
    const mapData = map.imageData.data;

    const frame = ctx.createImageData(VIEW_W, VIEW_H);
    const sky = buildSkyBuffer();

    let lastTime = performance.now();
    let rafId = 0;

    const tick = () => {
      rafId = requestAnimationFrame(tick);
      const now = performance.now();
      const dt = Math.min(0.05, (now - lastTime) / 1000);
      lastTime = now;

      // ── Physics ────────────────────────────────────────────────
      const player = playerRef.current;
      const c = controls.current;

      if (c.forward) player.speed += ACCEL * dt;
      if (c.back) player.speed -= BRAKE * dt;

      // Exponential friction is frame-rate independent.
      player.speed *= Math.exp(-FRICTION_PER_SEC * dt);

      if (player.speed > MAX_SPEED) player.speed = MAX_SPEED;
      const reverseCap = -MAX_SPEED * REVERSE_CAP_FRACTION;
      if (player.speed < reverseCap) player.speed = reverseCap;

      // Steering scales with speed; the floor lets the player wiggle
      // out of a wall even from a near-standstill.
      const speedNorm = Math.min(1, Math.abs(player.speed) / 110);
      const turnAmount =
        TURN_RATE * dt * (TURN_LOW_SPEED_FLOOR + speedNorm * (1 - TURN_LOW_SPEED_FLOOR));
      const turnSign = player.speed >= 0 ? 1 : -1;
      if (c.left) player.heading -= turnAmount * turnSign;
      if (c.right) player.heading += turnAmount * turnSign;

      const cosH = Math.cos(player.heading);
      const sinH = Math.sin(player.heading);
      const stepX = cosH * player.speed * dt;
      const stepZ = sinH * player.speed * dt;

      // Hard collisions with axis-separated sliding. Try the full
      // move first; if the destination is a barrier, fall back to
      // moving on a single axis so the car can grind along walls.
      const newX = player.x + stepX;
      const newZ = player.z + stepZ;

      if (isOnTrack(map, newX, newZ)) {
        player.x = newX;
        player.z = newZ;
      } else if (isOnTrack(map, newX, player.z)) {
        player.x = newX;
        player.speed *= WALL_GLANCE_RETAIN;
        wallFlashRef.current = 0.25;
      } else if (isOnTrack(map, player.x, newZ)) {
        player.z = newZ;
        player.speed *= WALL_GLANCE_RETAIN;
        wallFlashRef.current = 0.25;
      } else {
        // Head-on impact — small backwards nudge to avoid sticking.
        player.x -= stepX * 0.15;
        player.z -= stepZ * 0.15;
        player.speed *= WALL_HEAD_ON_RETAIN;
        wallFlashRef.current = 0.4;
      }

      if (wallFlashRef.current > 0) {
        wallFlashRef.current = Math.max(0, wallFlashRef.current - dt);
      }

      // ── Render ─────────────────────────────────────────────────
      const data = frame.data;
      data.set(sky, 0);

      const halfW = VIEW_W / 2;
      const rx = -sinH;
      const rz = cosH;

      for (let y = HORIZON_Y; y < VIEW_H; y++) {
        const dy = y - HORIZON_Y + 0.5;
        const z = (FOCAL_LENGTH * CAMERA_HEIGHT) / dy;
        const worldStep = z / FOCAL_LENGTH;

        const cx = player.x + cosH * z;
        const cz = player.z + sinH * z;

        const fog = Math.max(0, Math.min(1, 1 - z / FOG_DISTANCE));
        const fogR = 14, fogG = 8, fogB = 22;
        const oneMinusFog = 1 - fog;

        const stepWX = rx * worldStep;
        const stepWZ = rz * worldStep;
        let wx = cx - halfW * stepWX;
        let wz = cz - halfW * stepWZ;

        let i = y * VIEW_W * 4;
        for (let x = 0; x < VIEW_W; x++) {
          const ix = wx | 0;
          const iy = wz | 0;
          let r = 18, g = 60, b = 18;
          if (ix >= 0 && iy >= 0 && ix < MAP_SIZE && iy < MAP_SIZE) {
            const mi = (iy * MAP_SIZE + ix) * 4;
            r = mapData[mi];
            g = mapData[mi + 1];
            b = mapData[mi + 2];
          }
          data[i] = (r * fog + fogR * oneMinusFog) | 0;
          data[i + 1] = (g * fog + fogG * oneMinusFog) | 0;
          data[i + 2] = (b * fog + fogB * oneMinusFog) | 0;
          data[i + 3] = 255;
          i += 4;
          wx += stepWX;
          wz += stepWZ;
        }
      }

      ctx.putImageData(frame, 0, 0);

      drawCar(ctx, player.speed, c.back, wallFlashRef.current);
      drawHUD(ctx, player.speed);
      drawMiniMap(ctx, map, player);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [isActive, status, controls]);

  if (!isActive) return null;

  return (
    <div className="race-game-stage">
      <canvas ref={canvasRef} className="race-game-canvas" />

      {status === "loading" && (
        <div className="race-game-status">Building pixel circuit…</div>
      )}

      {status === "error" && (
        <div className="race-game-status race-game-status-error">
          {error ?? "Failed to load track"}
        </div>
      )}

      {status === "ready" && (
        <div className="race-game-controls-hint">
          <span>WASD / Arrow keys to drive</span>
          <span>Esc to exit</span>
        </div>
      )}

      <button
        type="button"
        className="race-game-exit"
        onClick={() => onExit?.()}
        aria-label="Exit mini game"
      >
        Exit
      </button>
    </div>
  );
}

/**
 * Draws a chunky-pixel back-view F1 silhouette: rear wing with end
 * plates, halo cockpit, twin sidepods, diffuser, exposed rear tyres,
 * livery stripe and a brake light that flashes red while braking
 * or after a wall hit.
 */
function drawCar(
  ctx: CanvasRenderingContext2D,
  speed: number,
  braking: boolean,
  wallFlash: number,
) {
  const cx = VIEW_W / 2;
  const cy = VIEW_H - 28;
  const wobble =
    Math.sin(performance.now() * 0.025) * Math.min(1.5, Math.abs(speed) / 160);

  ctx.save();
  ctx.translate(cx + wobble, cy);

  // Ground shadow
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ctx.beginPath();
  ctx.ellipse(0, 24, 30, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  // Rear wing endplates
  ctx.fillStyle = "#0e0e0e";
  ctx.fillRect(-32, -25, 4, 16);
  ctx.fillRect(28, -25, 4, 16);

  // Rear wing main element
  ctx.fillStyle = "#1a1a1a";
  ctx.fillRect(-30, -25, 60, 4);
  // Rear wing flap (DRS line)
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(-28, -19, 56, 2);
  // Wing pillars
  ctx.fillRect(-3, -21, 2, 6);
  ctx.fillRect(1, -21, 2, 6);

  // Brake light
  const brakeOn = braking || wallFlash > 0;
  ctx.fillStyle = brakeOn ? "#ff2200" : "#660000";
  ctx.fillRect(-2, -17, 4, 2);

  // Engine cover / airbox stack
  ctx.fillStyle = "#cc0000";
  ctx.fillRect(-7, -15, 14, 10);
  // Airbox highlight band
  ctx.fillStyle = "#ff3300";
  ctx.fillRect(-5, -13, 10, 2);

  // Cockpit opening (halo interior)
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(-4, -10, 8, 4);
  // Halo bow (subtle dark line above cockpit)
  ctx.fillStyle = "#1a1a1a";
  ctx.fillRect(-5, -10, 10, 1);

  // Bodywork transitioning out to sidepods
  ctx.fillStyle = "#cc0000";
  ctx.fillRect(-10, -5, 20, 10);

  // Sidepods (slightly darker red)
  ctx.fillStyle = "#aa0000";
  ctx.fillRect(-22, 0, 12, 14);
  ctx.fillRect(10, 0, 12, 14);

  // Sidepod inlet shadows
  ctx.fillStyle = "#440000";
  ctx.fillRect(-22, 2, 4, 5);
  ctx.fillRect(18, 2, 4, 5);

  // Livery accent stripe across the cover
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(-9, -2, 18, 1);

  // Diffuser
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(-14, 14, 28, 4);
  ctx.fillStyle = "#262626";
  for (let i = -12; i <= 11; i += 6) {
    ctx.fillRect(i, 14, 1, 4);
  }

  // Rear tyres
  ctx.fillStyle = "#000";
  ctx.fillRect(-32, -2, 8, 22);
  ctx.fillRect(24, -2, 8, 22);

  // Tyre rim hub
  ctx.fillStyle = "#3a3a3a";
  ctx.fillRect(-30, 7, 4, 4);
  ctx.fillRect(26, 7, 4, 4);

  // Tyre tread suggestion
  ctx.fillStyle = "rgba(255,255,255,0.22)";
  for (let i = -1; i <= 19; i += 6) {
    ctx.fillRect(-31, i, 6, 1);
    ctx.fillRect(25, i, 6, 1);
  }

  ctx.restore();
}

function drawHUD(ctx: CanvasRenderingContext2D, speed: number) {
  ctx.save();
  const kph = Math.round(Math.abs(speed) * 1.1);

  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(4, 4, 64, 16);
  ctx.fillStyle = "#fff";
  ctx.font = "bold 10px monospace";
  ctx.textBaseline = "top";
  ctx.fillText(`${kph} KM/H`, 8, 7);

  ctx.restore();
}

function drawMiniMap(
  ctx: CanvasRenderingContext2D,
  map: TrackMap,
  player: { x: number; z: number; heading: number },
) {
  const SIZE = 60;
  const x0 = VIEW_W - SIZE - 4;
  const y0 = 4;

  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,0.65)";
  ctx.fillRect(x0, y0, SIZE, SIZE);
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1;
  ctx.strokeRect(x0 + 0.5, y0 + 0.5, SIZE - 1, SIZE - 1);

  ctx.strokeStyle = "#888";
  ctx.lineWidth = 1;
  ctx.beginPath();
  const points = map.scaledPoints;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const sx = x0 + (p.x / MAP_SIZE) * SIZE;
    const sy = y0 + (p.y / MAP_SIZE) * SIZE;
    if (i === 0) ctx.moveTo(sx, sy);
    else ctx.lineTo(sx, sy);
  }
  ctx.closePath();
  ctx.stroke();

  const px = x0 + (player.x / MAP_SIZE) * SIZE;
  const py = y0 + (player.z / MAP_SIZE) * SIZE;

  // Heading arrow
  const ax = px + Math.cos(player.heading) * 5;
  const ay = py + Math.sin(player.heading) * 5;
  ctx.strokeStyle = "#ff2200";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(px, py);
  ctx.lineTo(ax, ay);
  ctx.stroke();

  ctx.fillStyle = "#ff2200";
  ctx.beginPath();
  ctx.arc(px, py, 1.8, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}
