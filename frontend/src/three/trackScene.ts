import * as THREE from "three";

// ─── Theme ────────────────────────────────────────────────────────
export type CircuitTheme = {
  primary: string;
  glow: string;
  core: string;
  text: string;
};

export const CIRCUIT_THEME: Record<string, CircuitTheme> = {
  Melbourne:   { primary: "#228B22", glow: "#bbaa00", core: "#228B22", text: "#ffdd00" },
  Austin:      { primary: "#001a4d", glow: "#1a5599", core: "#ff4444", text: "#ff3333" },
  Catalunya:   { primary: "#8b0000", glow: "#aa3333", core: "#ffdd00", text: "#ffdd00" },
  MexicoCity:  { primary: "#003d22", glow: "#006644", core: "#ce1126", text: "#ff3333" },
  Montreal:    { primary: "#7a0011", glow: "#aa2244", core: "#ffffff", text: "#ff3333" },
  Monza:       { primary: "#003d22", glow: "#007744", core: "#ff3333", text: "#ff3333" },
  Sakhir:      { primary: "#8b0000", glow: "#aa2244", core: "#ffffff", text: "#ffffff" },
  SaoPaulo:    { primary: "#004d22", glow: "#007744", core: "#ffdd00", text: "#ffdd00" },
  Shanghai:    { primary: "#8b0000", glow: "#aa3333", core: "#ffdd00", text: "#ffdd00" },
  Silverstone: { primary: "#001a4d", glow: "#1a5599", core: "#ffffff", text: "#ff3333" },
  Spa:         { primary: "#9d8a1a", glow: "#cc9944", core: "#ff3333", text: "#ff3333" },
  Suzuka:      { primary: "#660022", glow: "#aa3333", core: "#fb0000", text: "#f37979" },
  YasMarina:   { primary: "#003d22", glow: "#dd3333", core: "#ffffff", text: "#ff3333" },
  Zandvoort:   { primary: "#001a4d", glow: "#553333", core: "#ffffff", text: "#ff3333" },
  DEFAULT:     { primary: "#aa1100", glow: "#dd3333", core: "#ffcc88", text: "#ff2200" },
};

// ─── Colour helpers ───────────────────────────────────────────────
export function hexToNumber(hex: string): number {
  return parseInt(hex.replace("#", ""), 16);
}

export function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const value = hexToNumber(hex);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

export function themeRgba(hex: string, alpha: number): string {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ─── Track CSV parsing & layout ───────────────────────────────────
export interface TrackPoint {
  x: number;
  y: number;
  isCorner: boolean;
}

export function parseTrackData(raw: string): TrackPoint[] {
  // Strip JS template-literal wrapper if present (`const trackData = \`...\`;`)
  let csv = raw;
  const wrapperMatch = raw.match(/`([\s\S]*)`/);
  if (wrapperMatch) csv = wrapperMatch[1];

  const lines = csv.trim().split("\n");
  const points: TrackPoint[] = [];
  let isCornerIdx: number | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line.startsWith("#")) continue;
    const headerLine = line.replace(/^#\s*/, "");
    const cols = headerLine.split(",").map((c) => c.trim());
    if (cols.length < 2) continue;

    const idxApex = cols.findIndex((c) => c === "is_corner_apex");
    const idxLegacy = cols.findIndex((c) => c === "is_corner");
    isCornerIdx =
      idxApex >= 0 ? idxApex : idxLegacy >= 0 ? idxLegacy : null;
    break;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.length === 0 || line.startsWith("#")) continue;
    const parts = line.split(",");
    if (parts.length >= 2) {
      const x = parseFloat(parts[0]);
      const y = parseFloat(parts[1]);
      if (!isNaN(x) && !isNaN(y)) {
        const idx = isCornerIdx ?? 4;
        const isCorner = parts.length > idx ? parts[idx].trim() === "1" : false;
        points.push({ x, y, isCorner });
      }
    }
  }
  return points;
}

const BASE_TRACK_TARGET_SIZE = 25;
const MIN_TRACK_TARGET_SIZE = 18;
const MAX_TRACK_TARGET_SIZE = 32;
const REFERENCE_TRACK_LENGTH_KM = 5.4;

export function getTrackTargetSize(lengthKm?: number | null): number {
  if (!lengthKm || !Number.isFinite(lengthKm)) return BASE_TRACK_TARGET_SIZE;
  const targetSize =
    BASE_TRACK_TARGET_SIZE * Math.sqrt(lengthKm / REFERENCE_TRACK_LENGTH_KM);
  return Math.min(MAX_TRACK_TARGET_SIZE, Math.max(MIN_TRACK_TARGET_SIZE, targetSize));
}

export interface TrackLayout {
  centreX: number;
  centreY: number;
  scale: number;
}

export function getTrackLayout(
  rawPoints: { x: number; y: number }[],
  lengthKm?: number | null,
): TrackLayout {
  let minX = Infinity,
    maxX = -Infinity;
  let minY = Infinity,
    maxY = -Infinity;
  rawPoints.forEach((p) => {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  });

  const maxRange = Math.max(maxX - minX, maxY - minY, 1);
  const targetSize = getTrackTargetSize(lengthKm);

  return {
    centreX: (minX + maxX) / 2,
    centreY: (minY + maxY) / 2,
    scale: targetSize / maxRange,
  };
}

export function buildScaledPoints(
  rawPoints: { x: number; y: number }[],
  lengthKm?: number | null,
): THREE.Vector3[] {
  const { centreX, centreY, scale } = getTrackLayout(rawPoints, lengthKm);

  return rawPoints.map(
    (p) =>
      new THREE.Vector3((p.x - centreX) * scale, 0, (p.y - centreY) * scale),
  );
}

// Project a raw CSV-space (x, y) point into scene-space (x, z) using the
// same layout maths used to build the track tube. Handy for placing focal
// points (e.g. zoom targets) that live in source CSV coordinates.
export function projectRawPointToScene(
  raw: { x: number; y: number },
  layout: TrackLayout,
): { x: number; z: number } {
  return {
    x: (raw.x - layout.centreX) * layout.scale,
    z: (raw.y - layout.centreY) * layout.scale,
  };
}
