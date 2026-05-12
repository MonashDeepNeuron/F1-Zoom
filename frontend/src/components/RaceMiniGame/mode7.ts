import { parseTrackData } from "../../three/trackScene";

// Map (top-down) is rendered into an offscreen canvas at this resolution.
// World coordinates used by the game are simply "map pixels".
export const MAP_SIZE = 2048;

// Lateral widths used when stamping the track polyline into the map.
//   ASPHALT_WIDTH ............ pure tarmac (full grip)
//   + CURB_WIDTH (each side) . red/white kerb (still drivable)
//   + WALL_WIDTH (each side) . tire-wall band (visible barrier)
export const ASPHALT_WIDTH = 38;
export const CURB_WIDTH = 8;
export const WALL_WIDTH = 14;

const DRIVABLE_WIDTH = ASPHALT_WIDTH + CURB_WIDTH;
const FULL_WIDTH = DRIVABLE_WIDTH + WALL_WIDTH;

export interface SpawnInfo {
  x: number;
  z: number;
  heading: number;
}

export interface TrackMap {
  /** Visible top-down map. Sampled per-pixel by the Mode-7 renderer. */
  canvas: HTMLCanvasElement;
  /** ImageData wrapper around `canvas` (cached for fast sampling). */
  imageData: ImageData;
  /** 1 = pixel is drivable (asphalt or kerb). 0 = barrier (tire wall, grass, off-map). */
  collisionMask: Uint8Array;
  /** Starting position + heading for the player. */
  spawn: SpawnInfo;
  /** Polyline points in map-pixel coordinates (used for the mini-map). */
  scaledPoints: { x: number; y: number }[];
}

/**
 * Parse a TrackCoordinateJS file and bake (a) a richly-decorated visible
 * top-down map and (b) a binary drivability mask. The visible map is
 * later sampled by the Mode-7 renderer; the mask is queried by the
 * collision system so cars cannot drive off the circuit.
 */
export function buildTrackMap(rawText: string): TrackMap | null {
  const rawPoints = parseTrackData(rawText);
  if (rawPoints.length < 2) return null;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of rawPoints) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const range = Math.max(maxX - minX, maxY - minY, 1);
  const target = MAP_SIZE * 0.86;
  const scale = target / range;
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;

  const half = MAP_SIZE / 2;
  const scaledPoints = rawPoints.map((p) => ({
    x: half + (p.x - centreX) * scale,
    y: half + (p.y - centreY) * scale,
  }));

  // ── Visible map ──────────────────────────────────────────────────
  const canvas = document.createElement("canvas");
  canvas.width = MAP_SIZE;
  canvas.height = MAP_SIZE;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;

  // Grass base.
  ctx.fillStyle = "#143d14";
  ctx.fillRect(0, 0, MAP_SIZE, MAP_SIZE);

  // Subtle grass banding for visual interest.
  for (let y = 0; y < MAP_SIZE; y += 16) {
    ctx.fillStyle =
      (y / 16) % 2 === 0 ? "rgba(0,0,0,0.05)" : "rgba(255,255,255,0.025)";
    ctx.fillRect(0, y, MAP_SIZE, 8);
  }

  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // Tire-wall band: dark base + dashed lighter accent for that
  // "stacked tire" pattern. Drawn at FULL_WIDTH so it sits just
  // outside the kerb.
  ctx.strokeStyle = "#0d0d0d";
  ctx.lineWidth = FULL_WIDTH;
  strokePolyline(ctx, scaledPoints, true);

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = FULL_WIDTH;
  ctx.setLineDash([8, 10]);
  strokePolyline(ctx, scaledPoints, true);
  ctx.setLineDash([]);

  // Kerb: red base + white dashes for classic candy-stripe look.
  ctx.strokeStyle = "#cc0000";
  ctx.lineWidth = DRIVABLE_WIDTH;
  strokePolyline(ctx, scaledPoints, true);

  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = DRIVABLE_WIDTH;
  ctx.setLineDash([22, 22]);
  strokePolyline(ctx, scaledPoints, true);
  ctx.setLineDash([]);

  // Asphalt.
  ctx.strokeStyle = "#2a2a2a";
  ctx.lineWidth = ASPHALT_WIDTH;
  strokePolyline(ctx, scaledPoints, true);

  // Centre dashed line.
  ctx.strokeStyle = "rgba(255,220,60,0.55)";
  ctx.lineWidth = 2;
  ctx.setLineDash([12, 18]);
  strokePolyline(ctx, scaledPoints, true);
  ctx.setLineDash([]);

  // Start / finish stripe perpendicular to forward direction at p0.
  const p0 = scaledPoints[0];
  const p1 = scaledPoints[1];
  const dx = p1.x - p0.x;
  const dy = p1.y - p0.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const halfStripe = ASPHALT_WIDTH / 2;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(p0.x - nx * halfStripe, p0.y - ny * halfStripe);
  ctx.lineTo(p0.x + nx * halfStripe, p0.y + ny * halfStripe);
  ctx.stroke();

  const imageData = ctx.getImageData(0, 0, MAP_SIZE, MAP_SIZE);

  // ── Collision mask ───────────────────────────────────────────────
  // Re-stroke the same polyline at DRIVABLE_WIDTH onto a fresh canvas
  // and threshold the red channel into a packed Uint8Array. This mask
  // is what the physics step queries — anywhere outside the tarmac /
  // kerb (i.e. inside the tire wall or beyond) is a hard barrier.
  const collisionCanvas = document.createElement("canvas");
  collisionCanvas.width = MAP_SIZE;
  collisionCanvas.height = MAP_SIZE;
  const cctx = collisionCanvas.getContext("2d");
  if (!cctx) return null;
  cctx.fillStyle = "#000";
  cctx.fillRect(0, 0, MAP_SIZE, MAP_SIZE);
  cctx.lineCap = "round";
  cctx.lineJoin = "round";
  cctx.strokeStyle = "#ffffff";
  cctx.lineWidth = DRIVABLE_WIDTH;
  strokePolyline(cctx, scaledPoints, true);

  const collisionData = cctx.getImageData(0, 0, MAP_SIZE, MAP_SIZE).data;
  const collisionMask = new Uint8Array(MAP_SIZE * MAP_SIZE);
  for (let i = 0; i < collisionMask.length; i++) {
    collisionMask[i] = collisionData[i * 4] > 128 ? 1 : 0;
  }

  // Spawn slightly forward of the start/finish stripe so the camera
  // already shows the track stretching ahead on the very first frame.
  const spawnDistance = 28;
  const spawn: SpawnInfo = {
    x: p0.x + (dx / len) * spawnDistance,
    z: p0.y + (dy / len) * spawnDistance,
    heading: Math.atan2(dy, dx),
  };

  return { canvas, imageData, collisionMask, spawn, scaledPoints };
}

function strokePolyline(
  ctx: CanvasRenderingContext2D,
  points: { x: number; y: number }[],
  closed: boolean,
) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
  if (closed) ctx.lineTo(points[0].x, points[0].y);
  ctx.stroke();
}

/**
 * Returns true if the world-space point sits on a drivable surface
 * (asphalt or kerb). Used by the physics step for axis-separated
 * sliding against barriers.
 */
export function isOnTrack(map: TrackMap, x: number, z: number): boolean {
  const ix = x | 0;
  const iy = z | 0;
  if (ix < 0 || iy < 0 || ix >= MAP_SIZE || iy >= MAP_SIZE) return false;
  return map.collisionMask[iy * MAP_SIZE + ix] === 1;
}
