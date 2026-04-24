import { useRef, useEffect, useState, useCallback } from "react";
import * as THREE from "three";
import { getCircuitsBySeason, getNextRace } from "../services/api";
import "../styles/CircuitHero.css";

// ─── Track Metadata ──────────────────────────────────────────────
interface TrackHistoryEntry {
  year: number;
  winner: string;
}

interface TrackMeta {
  key: string;
  file: string;
  title: string;
  subtitle: string;
  flag: string;
  countryCode: string;
  length: string;
  laps: number;
  corners: number;
  distance: string;
  round?: number | null;
  grandPrixName?: string | null;
  weekendFormat?: "normal" | "sprint" | null;
  sessions: CircuitSession[];
  history: TrackHistoryEntry[];
}

interface CircuitSession {
  sessionType: SessionField;
  sessionDateAest?: string | null;
  sessionTimeAest?: string | null;
  sessionStartUtc?: string | null;
}

interface CircuitApiRow {
  code: string;
  fileSlug: string;
  title: string;
  subtitle: string;
  flag: string;
  lengthKm: number;
  laps: number;
  corners: number;
  distanceKm: number;
  season?: number | null;
  round?: number | null;
  grandPrixName?: string | null;
  weekendFormat?: "normal" | "sprint" | null;
  sessions?: CircuitSession[];
  history?: TrackHistoryEntry[];
}

interface NextRaceApiRace {
  raceName?: string;
  round?: string;
  date?: string;
  Circuit?: {
    circuitId?: string;
    circuitName?: string;
    Location?: {
      locality?: string;
      country?: string;
    };
  };
}

interface SessionRow {
  key: SessionField;
  label: string;
  startAt: Date;
}

type SessionField =
  | "practice_1"
  | "practice_2"
  | "practice_3"
  | "sprint_qualifying"
  | "qualifying"
  | "sprint"
  | "race";

const SESSION_SEQUENCE: { key: SessionField; label: string }[] = [
  { key: "practice_1", label: "Practice 1" },
  { key: "practice_2", label: "Practice 2" },
  { key: "practice_3", label: "Practice 3" },
  { key: "sprint_qualifying", label: "Sprint Qualifying" },
  { key: "qualifying", label: "Qualifying" },
  { key: "sprint", label: "Sprint" },
  { key: "race", label: "Race" },
];

const AEST_TIME_ZONE = "Australia/Brisbane";
const AEST_DAY_FORMATTER = new Intl.DateTimeFormat("en-AU", {
  timeZone: AEST_TIME_ZONE,
  day: "numeric",
  month: "short",
});
const AEST_TIME_FORMATTER = new Intl.DateTimeFormat("en-AU", {
  timeZone: AEST_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: false,
});

const DEFAULT_SEASON = new Date().getFullYear();

const CIRCUIT_THEME: Record<string, { primary: string; glow: string; core: string; text: string }> = {
  Melbourne:   { primary: "#228B22", glow: "#bbaa00", core: "#228B22", text: "#ffdd00" }, // AU – dark green track, bright gold text, muted gold glow
  Austin:      { primary: "#001a4d", glow: "#1a5599", core: "#ff4444", text: "#ff3333" }, // US – dark blue track, bright red text, medium blue glow
  Catalunya:   { primary: "#8b0000", glow: "#aa3333", core: "#ffdd00", text: "#ffdd00" }, // ES – dark red track, bright yellow text, medium red glow
  MexicoCity:  { primary: "#003d22", glow: "#006644", core: "#ce1126", text: "#ff3333" }, // MX – dark green track, bright red text, medium green glow
  Montreal:    { primary: "#7a0011", glow: "#aa2244", core: "#ffffff", text: "#ff3333" }, // CA – dark red track, bright red text, medium red glow
  Monza:       { primary: "#003d22", glow: "#007744", core: "#ff3333", text: "#ff3333" }, // IT – dark green track, bright red text, medium green glow
  Sakhir:      { primary: "#8b0000", glow: "#aa2244", core: "#ffffff", text: "#ffffff" }, // BH – dark red track, white text, medium red glow
  SaoPaulo:    { primary: "#004d22", glow: "#007744", core: "#ffdd00", text: "#ffdd00" }, // BR – dark green track, bright yellow text, medium green glow
  Shanghai:    { primary: "#8b0000", glow: "#aa3333", core: "#ffdd00", text: "#ffdd00" }, // CN – dark red track, bright yellow text, medium red glow
  Silverstone: { primary: "#001a4d", glow: "#1a5599", core: "#ffffff", text: "#ff3333" }, // GB – dark blue track, bright red text, medium blue glow
  Spa:         { primary: "#9d8a1a", glow: "#cc9944", core: "#ff3333", text: "#ff3333" }, // BE – dark yellow track, bright red text, medium yellow glow
  Suzuka:      { primary: "#660022", glow: "#aa3333", core: "#fb0000", text: "#f37979" }, // JP – dark red track, white text, medium red glow
  YasMarina:   { primary: "#003d22", glow: "#dd3333", core: "#ffffff", text: "#ff3333" }, // AE – dark green track, bright red text, muted red glow
  Zandvoort:   { primary: "#001a4d", glow: "#553333", core: "#ffffff", text: "#ff3333" }, // NL – dark blue track, bright red text, muted brown/red glow
  DEFAULT:     { primary: "#aa1100", glow: "#dd3333", core: "#ffcc88", text: "#ff2200" }, // dark red track, bright red text, muted red glow
};

// ─── Helpers ─────────────────────────────────────────────────────
function hexToNumber(hex: string): number {
  return parseInt(hex.replace("#", ""), 16);
}
function parseTrackData(
  raw: string,
): { x: number; y: number; isCorner: boolean }[] {
  // Strip JS template-literal wrapper if present (`const trackData = \`...\`;`)
  let csv = raw;
  const wrapperMatch = raw.match(/`([\s\S]*)`/);
  if (wrapperMatch) csv = wrapperMatch[1];

  const lines = csv.trim().split("\n");
  const points: { x: number; y: number; isCorner: boolean }[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.length === 0 || line.startsWith("#")) continue;
    const parts = line.split(",");
    if (parts.length >= 2) {
      const x = parseFloat(parts[0]);
      const y = parseFloat(parts[1]);
      if (!isNaN(x) && !isNaN(y)) {
        // 5th column (index 4) is is_corner flag produced by csv_reading.py
        const isCorner = parts.length >= 5 ? parts[4].trim() === "1" : false;
        points.push({ x, y, isCorner });
      }
    }
  }
  return points;
}

function buildScaledPoints(
  rawPoints: { x: number; y: number }[],
): THREE.Vector3[] {
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
  const rangeX = maxX - minX;
  const rangeY = maxY - minY;
  const maxRange = Math.max(rangeX, rangeY);
  const targetSize = 25;
  const scale = targetSize / maxRange;
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;
  return rawPoints.map(
    (p) =>
      new THREE.Vector3((p.x - centreX) * scale, 0, (p.y - centreY) * scale),
  );
}

function countryCodeToFlag(code: string): string {
  if (!/^[A-Za-z]{2}$/.test(code)) return code;
  return code
    .toUpperCase()
    .split("")
    .map((char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
    .join("");
}

function mapApiCircuitToTrack(row: CircuitApiRow): TrackMeta {
  return {
    key: row.code,
    file: row.fileSlug,
    title: row.title,
    subtitle: row.subtitle,
    flag: countryCodeToFlag(row.flag),
    countryCode: row.flag.toUpperCase(),
    length: `${Number(row.lengthKm).toFixed(3)} KM`,
    laps: row.laps,
    corners: row.corners,
    distance: `${Number(row.distanceKm).toFixed(3)} KM`,
    round: row.round ?? null,
    grandPrixName: row.grandPrixName ?? null,
    weekendFormat: row.weekendFormat ?? null,
    sessions: row.sessions ?? [],
    history: row.history ?? [],
  };
}

function normalizeForMatch(value?: string | null): string {
  if (!value) return "";
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function pickInitialTrack(tracks: TrackMeta[], nextRace?: NextRaceApiRace | null): TrackMeta | null {
  if (tracks.length === 0) return null;
  if (!nextRace) return tracks[0];

  const raceNameNorm = normalizeForMatch(nextRace.raceName);
  const circuitNameNorm = normalizeForMatch(nextRace.Circuit?.circuitName);
  const circuitIdNorm = normalizeForMatch(nextRace.Circuit?.circuitId);
  const localityNorm = normalizeForMatch(nextRace.Circuit?.Location?.locality);

  const byName = tracks.find((track) => {
    const titleNorm = normalizeForMatch(track.title);
    const gpNameNorm = normalizeForMatch(track.grandPrixName);
    const keyNorm = normalizeForMatch(track.key);
    const subtitleNorm = normalizeForMatch(track.subtitle);

    return (
      (raceNameNorm && (gpNameNorm === raceNameNorm || titleNorm.includes(raceNameNorm) || raceNameNorm.includes(gpNameNorm))) ||
      (circuitNameNorm && subtitleNorm.includes(circuitNameNorm)) ||
      (circuitIdNorm && (keyNorm === circuitIdNorm || titleNorm.includes(circuitIdNorm) || subtitleNorm.includes(circuitIdNorm))) ||
      (localityNorm && (titleNorm.includes(localityNorm) || subtitleNorm.includes(localityNorm)))
    );
  });

  if (byName) return byName;

  const nextRound = Number(nextRace.round);
  if (Number.isFinite(nextRound)) {
    const byRound = tracks.find((track) => track.round === nextRound);
    if (byRound) return byRound;
  }

  return tracks[0];
}

function withLocalTrackVariants(tracks: TrackMeta[]): TrackMeta[] {
  const hasMelbourne2 = tracks.some((track) => track.key === "Melbourne2");
  if (hasMelbourne2) return tracks;

  const melbourne = tracks.find((track) => track.key === "Melbourne");
  if (!melbourne) return tracks;

  const melbourne2: TrackMeta = {
    ...melbourne,
    key: "Melbourne2",
    file: "Melbourne2",
    title: "MELBOURNE 2",
    subtitle: "ALBERT PARK CIRCUIT (FASTF1 V2)",
  };

  return [melbourne, melbourne2, ...tracks.filter((track) => track.key !== "Melbourne")];
}

function parseSessionTime(session?: CircuitSession): Date | null {
  if (!session) return null;
  if (session.sessionStartUtc) {
    const fromUtc = new Date(session.sessionStartUtc);
    return Number.isNaN(fromUtc.getTime()) ? null : fromUtc;
  }

  if (!session.sessionDateAest || !session.sessionTimeAest) return null;
  const normalizedTime =
    session.sessionTimeAest.length === 5
      ? `${session.sessionTimeAest}:00`
      : session.sessionTimeAest;
  const asAest = new Date(`${session.sessionDateAest}T${normalizedTime}+10:00`);
  return Number.isNaN(asAest.getTime()) ? null : asAest;
}

function getSessionRows(track: TrackMeta | null): SessionRow[] {
  if (!track) return [];

  const sessionMap = new Map<SessionField, CircuitSession>();
  track.sessions.forEach((session) => {
    sessionMap.set(session.sessionType, session);
  });

  const rows: SessionRow[] = [];
  SESSION_SEQUENCE.forEach(({ key, label }) => {
    const startAt = parseSessionTime(sessionMap.get(key));
    if (startAt) rows.push({ key, label, startAt });
  });

  rows.sort((a, b) => a.startAt.getTime() - b.startAt.getTime());
  return rows;
}

function formatAestDayMonth(date: Date): string {
  const parts = AEST_DAY_FORMATTER.formatToParts(date);
  const day = parts.find((p) => p.type === "day")?.value ?? "";
  const month = (parts.find((p) => p.type === "month")?.value ?? "")
    .replace(".", "")
    .toUpperCase();
  return `${day} ${month}`.trim();
}

function formatAestTime(date: Date): string {
  return AEST_TIME_FORMATTER.format(date);
}

// ─── Component ───────────────────────────────────────────────────
export default function CircuitHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const animationRef = useRef<number | null>(null);
  const scrollRafRef = useRef<number | null>(null);
  const loadIdRef = useRef(0);
  const tracksRef = useRef<TrackMeta[]>([]);
  const sceneStateRef = useRef<{
    isDragging: boolean;
    autoRotate: boolean;
    prevX: number;
    cameraAngleTheta: number;
    cameraDistance: number;
  }>({
    isDragging: false,
    autoRotate: true,
    prevX: 0,
    cameraAngleTheta: Math.PI / 4,
    cameraDistance: 30,
  });

  const [tracks, setTracks] = useState<TrackMeta[]>([]);
  const [selectedTrack, setSelectedTrack] = useState("");
  const [loading, setLoading] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  // ── Scroll-driven parallax: fade/scale the hero as user scrolls past ──
  useEffect(() => {
    const handleScroll = () => {
      if (scrollRafRef.current) return;
      scrollRafRef.current = requestAnimationFrame(() => {
        const section = sectionRef.current;
        if (!section) {
          scrollRafRef.current = null;
          return;
        }
        const rect = section.getBoundingClientRect();
        const vh = window.innerHeight;
        // progress: 0 when hero fully visible, 1 when hero top reaches viewport top and beyond
        const progress = Math.max(0, Math.min(1, -rect.top / (vh * 0.6)));
        setScrollProgress(progress);
        scrollRafRef.current = null;
      });
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", handleScroll);
      if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);
    };
  }, []);

  const teardownScene = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    const container = containerRef.current;
    if (container) {
      // Remove only the canvas, not the overlay UI
      const canvas = container.querySelector("canvas");
      if (canvas) container.removeChild(canvas);
    }
    if (rendererRef.current) {
      rendererRef.current.dispose();
      rendererRef.current = null;
    }
  }, []);

  const initTrackScene = useCallback((csvData: string, fileSlug?: string) => {
    const theme = CIRCUIT_THEME[fileSlug ?? ""] ?? CIRCUIT_THEME.DEFAULT;
    const accentColor = theme.text;
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.Fog(0x000000, 30, 100);

    const camera = new THREE.PerspectiveCamera(
      50,
      container.clientWidth / container.clientHeight,
      0.1,
      1000,
    );

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // ── Lighting (subtle — most colour comes from emissive materials) ──
    scene.add(new THREE.AmbientLight(0xffffff, 0.08));

    // Overhead key light
    const pointLight1 = new THREE.PointLight(hexToNumber(theme.primary), 1.2, 60);
    pointLight1.position.set(0, 25, 0);
    scene.add(pointLight1);

    // Accent fills for subtle depth
    const pointLight2 = new THREE.PointLight(hexToNumber(theme.glow), 0.6, 50);
    pointLight2.position.set(20, 15, 20);
    scene.add(pointLight2);

    const pointLight3 = new THREE.PointLight(0xff4400, 0.4, 40);
    pointLight3.position.set(-20, 12, -20);
    scene.add(pointLight3);

    // Gentle side lights
    const sideLight1 = new THREE.PointLight(0xff1100, 0.5, 50);
    sideLight1.position.set(25, 10, 0);
    scene.add(sideLight1);

    const sideLight2 = new THREE.PointLight(0xff1100, 0.5, 50);
    sideLight2.position.set(-25, 10, 0);
    scene.add(sideLight2);

    // ── Build track geometry ─────────────────────────────────────
    const rawPoints = parseTrackData(csvData);
    const trackPoints = buildScaledPoints(rawPoints);

    // Compute scaling params (mirrors buildScaledPoints) for turn marker placement
    let _minX = Infinity,
      _maxX = -Infinity,
      _minY = Infinity,
      _maxY = -Infinity;
    rawPoints.forEach((p) => {
      if (p.x < _minX) _minX = p.x;
      if (p.x > _maxX) _maxX = p.x;
      if (p.y < _minY) _minY = p.y;
      if (p.y > _maxY) _maxY = p.y;
    });
    const _scale = 25 / Math.max(_maxX - _minX, _maxY - _minY);
    const _centreX = (_minX + _maxX) / 2;
    const _centreY = (_minY + _maxY) / 2;

    const TRACK_ELEVATION = 2.5;

    // Elevated curve for main track (raised above ground for 3D depth)
    const elevatedPoints = trackPoints.map(
      (p) => new THREE.Vector3(p.x, TRACK_ELEVATION, p.z),
    );
    const curve = new THREE.CatmullRomCurve3(
      elevatedPoints,
      true,
      "catmullrom",
      0.2,
    );

    // Shadow/bottom edge sits just below the main track
    const SHADOW_Y = TRACK_ELEVATION - 1.4;

    const shadowPoints = trackPoints.map(
      (p) => new THREE.Vector3(p.x, SHADOW_Y, p.z),
    );
    const shadowCurve = new THREE.CatmullRomCurve3(
      shadowPoints,
      true,
      "catmullrom",
      0.2,
    );

    const numSamples = Math.min(trackPoints.length * 2, 1200);
    const shadowSamples = Math.min(trackPoints.length, 600);

    // ── Connecting wall (ribbon between top track and bottom edge) ──
    const wallSegments = 500;
    const wallPositions: number[] = [];
    const wallUvs: number[] = [];
    const wallIndices: number[] = [];

    for (let i = 0; i <= wallSegments; i++) {
      const t = i / wallSegments;
      const topPt = curve.getPointAt(t);
      const u = t;

      // Top vertex (at main track level)
      wallPositions.push(topPt.x, topPt.y, topPt.z);
      wallUvs.push(u, 1);

      // Bottom vertex (at shadow level)
      wallPositions.push(topPt.x, SHADOW_Y, topPt.z);
      wallUvs.push(u, 0);
    }

    for (let i = 0; i < wallSegments; i++) {
      const tl = i * 2;
      const bl = i * 2 + 1;
      const tr = (i + 1) * 2;
      const br = (i + 1) * 2 + 1;
      wallIndices.push(tl, bl, tr);
      wallIndices.push(tr, bl, br);
    }

    const wallGeo = new THREE.BufferGeometry();
    wallGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(wallPositions, 3),
    );
    wallGeo.setAttribute("uv", new THREE.Float32BufferAttribute(wallUvs, 2));
    wallGeo.setIndex(wallIndices);
    wallGeo.computeVertexNormals();

    // Dark semi-transparent wall
    const wallMat = new THREE.MeshBasicMaterial({
      color: 0x330500,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    scene.add(new THREE.Mesh(wallGeo, wallMat));

    // Slightly brighter inner wall for depth
    const wallGlowMat = new THREE.MeshBasicMaterial({
      color: 0x441000,
      transparent: true,
      opacity: 0.1,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    scene.add(new THREE.Mesh(wallGeo, wallGlowMat));

    // ── Shadow / bottom edge track ───────────────────────────────
    // Bottom edge core — mirrors the main track shape
    const shadowCoreMat = new THREE.MeshBasicMaterial({
      color: hexToNumber(theme.glow),
      transparent: true,
      opacity: 0.4,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.12, 8, true),
        shadowCoreMat,
      ),
    );

    // Soft glow around bottom edge
    const shadowMidMat = new THREE.MeshBasicMaterial({
      color: 0x330500,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.35, 8, true),
        shadowMidMat,
      ),
    );

    // Faint outer glow on bottom edge
    const shadowOuterMat = new THREE.MeshBasicMaterial({
      color: 0x220300,
      transparent: true,
      opacity: 0.06,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.7, 6, true),
        shadowOuterMat,
      ),
    );

    // ── Main track (elevated top edge) ───────────────────────────
    // Solid track body
    const trackMesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, numSamples, 0.15, 12, true),
      new THREE.MeshPhongMaterial({
        color: hexToNumber(theme.primary),
        emissive: hexToNumber(theme.primary),
        emissiveIntensity: 0.6,
        shininess: 150,
        specular: 0xff8844,
      }),
    );
    scene.add(trackMesh);

    // Bright inner core — thin hot centre
    const coreMat = new THREE.MeshBasicMaterial({
      color: theme.core,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(curve, numSamples, 0.06, 8, true),
        coreMat,
      ),
    );

    // Tight glow layer 1 — close halo
    const glow1Mat = new THREE.MeshBasicMaterial({
      color: hexToNumber(theme.glow),
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(curve, numSamples, 0.28, 10, true),
        glow1Mat,
      ),
    );

    // Glow layer 2 — soft spread
    const glow2Mat = new THREE.MeshBasicMaterial({
      color: hexToNumber(theme.primary),
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(curve, numSamples, 0.5, 8, true),
        glow2Mat,
      ),
    );

    // Glow layer 3 — faint outer aura
    const glow3Mat = new THREE.MeshBasicMaterial({
      color: hexToNumber(theme.primary),
      transparent: true,
      opacity: 0.06,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    scene.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(curve, numSamples, 0.85, 8, true),
        glow3Mat,
      ),
    );

    // ── Turn number markers ─────────────────────────────────────
    const MARKER_Y = TRACK_ELEVATION + 2.4;

    function makeTurnLabel(num: number, textColor: string): THREE.Sprite {
      const size = 128;
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d")!;

      // Outer glow halo
      ctx.beginPath();
      ctx.arc(size / 2, size / 2, 56, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255, 34, 0, 0.12)";
      ctx.fill();

      // Solid background circle
      ctx.beginPath();
      ctx.arc(size / 2, size / 2, 38, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(12, 0, 0, 0.92)";
      ctx.fill();
      ctx.strokeStyle = textColor;
      ctx.lineWidth = 4;
      ctx.stroke();

      // Turn number text
      const fontSize = num >= 10 ? 34 : 42;
      ctx.fillStyle = textColor;
      ctx.font = `bold ${fontSize}px Arial`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(num), size / 2, size / 2 + 2);

      const texture = new THREE.CanvasTexture(canvas);
      const mat = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
      });
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(2.0, 2.0, 1);
      return sprite;
    }

    let turnNum = 0;
    for (let i = 0; i < rawPoints.length; i++) {
      const curr = rawPoints[i];
      const prev = i > 0 ? rawPoints[i - 1] : null;
      // Turn entry: is_corner transitions from false → true
      if (curr.isCorner && (!prev || !prev.isCorner)) {
        turnNum++;
        const sx = (curr.x - _centreX) * _scale;
        const sz = (curr.y - _centreY) * _scale;

        // Small glowing dot at track level
        const dotGeo = new THREE.SphereGeometry(0.22, 8, 8);
        const dotMat = new THREE.MeshBasicMaterial({
          color: 0xffaa00,
          transparent: true,
          opacity: 0.9,
          blending: THREE.AdditiveBlending,
          depthTest: false,
          depthWrite: false,
        });
        const dot = new THREE.Mesh(dotGeo, dotMat);
        dot.position.set(sx, TRACK_ELEVATION + 0.35, sz);
        scene.add(dot);

        // Numbered label sprite floating above the track
        const label = makeTurnLabel(turnNum, accentColor);
        label.position.set(sx, MARKER_Y, sz);
        scene.add(label);
      }
    }

    // Platform & grid (below shadow level — very subtle)
    const platform = new THREE.Mesh(
      new THREE.CircleGeometry(30, 64),
      new THREE.MeshBasicMaterial({
        color: 0x050000,
        transparent: true,
        opacity: 0.12,
      }),
    );
    platform.rotation.x = -Math.PI / 2;
    platform.position.y = SHADOW_Y - 1.0;
    scene.add(platform);

    const grid = new THREE.GridHelper(60, 60, 0x220000, 0x0a0000);
    grid.position.y = SHADOW_Y - 0.99;
    (grid.material as THREE.Material).opacity = 0.1;
    (grid.material as THREE.Material).transparent = true;
    scene.add(grid);

    // ── Camera & controls ────────────────────────────────────────
    const FIXED_PHI = Math.PI / 3; // Much lower angle for side-on view (try values: /8 = very low, /10 = low, /12 = moderate, /15 = higher)
    const autoRotateSpeed = 0.002;
    const state = sceneStateRef.current;
    state.cameraAngleTheta = Math.PI / 4;
    state.cameraDistance = 32;
    state.autoRotate = true;

    function updateCamera() {
      camera.position.x =
        state.cameraDistance *
        Math.sin(FIXED_PHI) *
        Math.cos(state.cameraAngleTheta);
      camera.position.y = state.cameraDistance * Math.cos(FIXED_PHI);
      camera.position.z =
        state.cameraDistance *
        Math.sin(FIXED_PHI) *
        Math.sin(state.cameraAngleTheta);
      camera.lookAt(0, 1.8, 0);
    }
    updateCamera();

    // Mouse events
    const onMouseDown = (e: MouseEvent) => {
      state.isDragging = true;
      state.autoRotate = false;
      state.prevX = e.clientX;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!state.isDragging) return;
      state.cameraAngleTheta -= (e.clientX - state.prevX) * 0.01;
      state.prevX = e.clientX;
    };
    const onMouseUp = () => {
      state.isDragging = false;
      setTimeout(() => {
        state.autoRotate = true;
      }, 2000);
    };
    const MAX_ZOOM_OUT = 50;
    const onWheel = (e: WheelEvent) => {
      // If scrolling down and already at max zoom-out, let the page scroll through
      if (e.deltaY > 0 && state.cameraDistance >= MAX_ZOOM_OUT) {
        return; // don't preventDefault — allow native scroll
      }
      e.preventDefault();
      state.cameraDistance += e.deltaY * 0.05;
      state.cameraDistance = Math.max(
        15,
        Math.min(MAX_ZOOM_OUT, state.cameraDistance),
      );
    };

    // Touch events
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        state.isDragging = true;
        state.autoRotate = false;
        state.prevX = e.touches[0].clientX;
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (!state.isDragging || e.touches.length !== 1) return;
      state.cameraAngleTheta -= (e.touches[0].clientX - state.prevX) * 0.01;
      state.prevX = e.touches[0].clientX;
    };
    const onTouchEnd = () => {
      state.isDragging = false;
      setTimeout(() => {
        state.autoRotate = true;
      }, 2000);
    };

    renderer.domElement.addEventListener("mousedown", onMouseDown);
    renderer.domElement.addEventListener("mousemove", onMouseMove);
    renderer.domElement.addEventListener("mouseup", onMouseUp);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });
    renderer.domElement.addEventListener("touchstart", onTouchStart);
    renderer.domElement.addEventListener("touchmove", onTouchMove);
    renderer.domElement.addEventListener("touchend", onTouchEnd);

    // ── Animation loop with enhanced dynamics ────────────────────
    function animate() {
      animationRef.current = requestAnimationFrame(animate);
      if (state.autoRotate) state.cameraAngleTheta += autoRotateSpeed;
      updateCamera();

      const t = Date.now() * 0.001;

      // Subtle light pulsing
      pointLight1.intensity = 1.2 + Math.sin(t * 1.8) * 0.15;
      pointLight2.intensity = 0.6 + Math.sin(t * 2.3) * 0.08;
      pointLight3.intensity = 0.4 + Math.sin(t * 1.6) * 0.06;
      sideLight1.intensity = 0.5 + Math.sin(t * 2.7) * 0.08;
      sideLight2.intensity = 0.5 + Math.cos(t * 2.7) * 0.08;

      // Pulsing track core
      coreMat.opacity = 0.8 + Math.sin(t * 3) * 0.1;

      // Animated glow layers
      glow1Mat.opacity = 0.35 + Math.sin(t * 2.5) * 0.06;
      glow2Mat.opacity = 0.15 + Math.sin(t * 2.0) * 0.04;
      glow3Mat.opacity = 0.06 + Math.sin(t * 1.5) * 0.02;

      // Animate shadow reflection layers
      shadowCoreMat.opacity = 0.35 + Math.sin(t * 1.8) * 0.05;
      shadowMidMat.opacity = 0.18 + Math.sin(t * 1.5) * 0.03;
      shadowOuterMat.opacity = 0.08 + Math.sin(t * 1.2) * 0.02;

      // Breathing effect on main track
      trackMesh.material.emissiveIntensity = 1.8 + Math.sin(t * 2.5) * 0.2;

      renderer.render(scene, camera);
    }

    // Handle resize
    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener("resize", onResize);

    animate();

    // Cleanup function for this specific scene instance
    return () => {
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("mousedown", onMouseDown);
      renderer.domElement.removeEventListener("mousemove", onMouseMove);
      renderer.domElement.removeEventListener("mouseup", onMouseUp);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.domElement.removeEventListener("touchstart", onTouchStart);
      renderer.domElement.removeEventListener("touchmove", onTouchMove);
      renderer.domElement.removeEventListener("touchend", onTouchEnd);
    };
  }, []);

  // Load track data
  const loadTrack = useCallback(
    async (trackKey: string, sourceTracks?: TrackMeta[]) => {
      const availableTracks = sourceTracks ?? tracksRef.current;
      const meta = availableTracks.find((track) => track.key === trackKey);
      if (!meta) return;

      setLoading(true);
      teardownScene();
      const currentLoadId = ++loadIdRef.current;

      try {
        const response = await fetch(
          `/circuit_3d/TrackCoordinateJS/${meta.file}.js`,
          {
            cache: "no-store",
          },
        );
        if (!response.ok) {
          throw new Error(`Failed to load track data: ${meta.file}`);
        }
        const csvData = await response.text();
        if (currentLoadId !== loadIdRef.current) return;
        initTrackScene(csvData, meta.file);
        requestAnimationFrame(() => {
          if (currentLoadId !== loadIdRef.current) return;
          setLoading(false);
        });
      } catch (error) {
        console.error("[F1] Failed to load track file:", meta.file, error);
        setLoading(false);
      }
    },
    [teardownScene, initTrackScene],
  );

  useEffect(() => {
    tracksRef.current = tracks;
  }, [tracks]);

  useEffect(() => {
    let active = true;
    setScheduleLoading(true);
    setScheduleError(null);

    getNextRace()
      .catch(() => null)
      .then((nextRaceRes) => {
        const nextRace: NextRaceApiRace | null =
          nextRaceRes?.data?.MRData?.RaceTable?.Races?.[0] ?? null;
        const nextRaceSeason = nextRace?.date
          ? new Date(nextRace.date).getUTCFullYear()
          : NaN;
        const seasonToLoad = Number.isFinite(nextRaceSeason)
          ? nextRaceSeason
          : DEFAULT_SEASON;

        return getCircuitsBySeason(seasonToLoad).then((circuitsRes) => ({
          circuitsRes,
          nextRace,
        }));
      })
      .then(({ circuitsRes, nextRace }) => {
        if (!active) return;
        const rows: CircuitApiRow[] = Array.isArray(circuitsRes.data) ? circuitsRes.data : [];
        const mapped = withLocalTrackVariants(
          rows
          .map(mapApiCircuitToTrack)
          .sort((a, b) => (a.round ?? 999) - (b.round ?? 999)),
        );

        tracksRef.current = mapped;
        setTracks(mapped);

        if (mapped.length === 0) {
          setScheduleError("No circuits found in database.");
          setLoading(false);
          return;
        }

        const initialTrack = pickInitialTrack(mapped, nextRace);
        if (!initialTrack) {
          setScheduleError("No circuits found in database.");
          setLoading(false);
          return;
        }
        setSelectedTrack(initialTrack.key);
        loadTrack(initialTrack.key, mapped);
      })
      .catch((error) => {
        console.error("[F1] Failed to load circuits from database:", error);
        if (!active) return;
        tracksRef.current = [];
        setTracks([]);
        let detail = "";
        if (typeof error === "object" && error !== null) {
          const maybeAxios = error as {
            response?: { data?: unknown; status?: number };
            message?: string;
          };
          if (typeof maybeAxios.response?.data === "string") {
            detail = maybeAxios.response.data;
          } else if (
            typeof maybeAxios.response?.data === "object" &&
            maybeAxios.response?.data !== null &&
            "message" in
              (maybeAxios.response.data as Record<string, unknown>) &&
            typeof (maybeAxios.response.data as Record<string, unknown>)
              .message === "string"
          ) {
            detail = (maybeAxios.response.data as Record<string, string>)
              .message;
          } else if (typeof maybeAxios.message === "string") {
            detail = maybeAxios.message;
          }
        }
        setScheduleError(
          detail
            ? `Unable to load circuits from database. ${detail}`
            : "Unable to load circuits from database.",
        );
        setLoading(false);
      })
      .finally(() => {
        if (active) setScheduleLoading(false);
      });

    return () => {
      active = false;
      teardownScene();
    };
  }, [loadTrack, teardownScene]);

  useEffect(() => {
    const timerId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timerId);
  }, []);

  const trackKeys = tracks.map((track) => track.key);
  const selectedTrackMeta =
    tracks.find((track) => track.key === selectedTrack) ?? null;
  const sessionRows = getSessionRows(selectedTrackMeta);
  const nextSessionIndex = sessionRows.findIndex(
    (session) => session.startAt.getTime() > nowMs,
  );

  const handleTrackChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value;
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handlePrevTrack = () => {
    const idx = trackKeys.indexOf(selectedTrack);
    if (idx === -1 || trackKeys.length === 0) return;
    const prevIdx = (idx - 1 + trackKeys.length) % trackKeys.length;
    const key = trackKeys[prevIdx];
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handleNextTrack = () => {
    const idx = trackKeys.indexOf(selectedTrack);
    if (idx === -1 || trackKeys.length === 0) return;
    const nextIdx = (idx + 1) % trackKeys.length;
    const key = trackKeys[nextIdx];
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handleScrollDown = () => {
    const heroEl = containerRef.current?.closest(".circuit-hero-section");
    if (heroEl) {
      const nextSection = heroEl.nextElementSibling;
      if (nextSection) {
        nextSection.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  // Parallax style computed from scroll progress
  const heroParallaxStyle: React.CSSProperties = {
    opacity: 1 - scrollProgress * 0.85,
    transform: `scale(${1 - scrollProgress * 0.08}) translateY(${scrollProgress * 30}px)`,
    transition: "none",
  };

  const overlayOpacity = scrollProgress * 0.9;
  const accentColor = CIRCUIT_THEME[selectedTrackMeta?.file ?? ""]?.text ?? CIRCUIT_THEME.DEFAULT.text;
  const themeGlow = CIRCUIT_THEME[selectedTrackMeta?.file ?? ""]?.glow ?? CIRCUIT_THEME.DEFAULT.glow;
  
  // Convert hex glow color to rgba for text-shadow
  const glowR = (themeGlow >> 16) & 255;
  const glowG = (themeGlow >> 8) & 255;
  const glowB = themeGlow & 255;
  
  const containerStyle: React.CSSProperties = {
    ...heroParallaxStyle,
    '--accent-color': accentColor,
    '--glow-shadow-1': `rgba(${glowR}, ${glowG}, ${glowB}, 0.8)`,
    '--glow-shadow-2': `rgba(${glowR}, ${glowG}, ${glowB}, 0.5)`,
    '--glow-shadow-3': `rgba(${glowR}, ${glowG}, ${glowB}, 0.3)`,
    '--glow-shadow-bright-1': `rgba(${glowR}, ${glowG}, ${glowB}, 1)`,
    '--glow-shadow-bright-2': `rgba(${glowR}, ${glowG}, ${glowB}, 0.7)`,
    '--glow-shadow-bright-3': `rgba(${glowR}, ${glowG}, ${glowB}, 0.5)`,
  } as React.CSSProperties;

  return (
    <section className="circuit-hero-section" ref={sectionRef}>
      <div
        className="circuit-hero-container"
        ref={containerRef}
        style={containerStyle}
      >
        {/* Loading indicator */}
        {loading && <div className="circuit-loading">LOADING CIRCUIT...</div>}

        {!loading && !selectedTrackMeta && (
          <div className="circuit-loading">
            {scheduleError ?? "No circuit data available."}
          </div>
        )}

        {/* Info panel */}
        {!loading && selectedTrackMeta && (
          <div className="circuit-info-panel">
            <h1 className="circuit-title">
              {selectedTrackMeta.title}
            </h1>
            <div className="circuit-subtitle">{selectedTrackMeta.subtitle}</div>
            <div className="circuit-stats">
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Length</span>
                <span className="circuit-stat-value">
                  {selectedTrackMeta.length}
                </span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Laps</span>
                <span className="circuit-stat-value">
                  {selectedTrackMeta.laps}
                </span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Corners</span>
                <span className="circuit-stat-value">
                  {selectedTrackMeta.corners}
                </span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Distance</span>
                <span className="circuit-stat-value">
                  {selectedTrackMeta.distance}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Race weekend schedule */}
        {!loading && selectedTrackMeta && (
          <div className="circuit-schedule-panel">
            <div className="circuit-schedule-topbar">
              <span className="circuit-schedule-heading">Schedule</span>
              <span className="circuit-schedule-flag">
                {selectedTrackMeta.flag}
              </span>
            </div>
            <div className="circuit-schedule-race">
              {selectedTrackMeta.grandPrixName ??
                `${selectedTrackMeta.title} GP`}
            </div>
            <div className="circuit-schedule-columns">
              <span>Event</span>
              <span>Date</span>
              <span>Time</span>
            </div>

            {scheduleLoading && (
              <div className="circuit-schedule-empty">Loading sessions...</div>
            )}

            {!scheduleLoading && scheduleError && (
              <div className="circuit-schedule-empty">{scheduleError}</div>
            )}

            {!scheduleLoading && !scheduleError && sessionRows.length === 0 && (
              <div className="circuit-schedule-empty">
                No session times available.
              </div>
            )}

            {!scheduleLoading && !scheduleError && sessionRows.length > 0 && (
              <div className="circuit-schedule-list">
                {sessionRows.map((session, index) => {
                  const sessionStartMs = session.startAt.getTime();
                  const isNext = nextSessionIndex === index;
                  const isPast = sessionStartMs <= nowMs;
                  const rowClassName = [
                    "circuit-schedule-row",
                    isNext ? "is-next" : "",
                    isPast ? "is-past" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");

                  return (
                    <div
                      key={`${session.key}-${sessionStartMs}`}
                      className={rowClassName}
                    >
                      <span>{session.label}</span>
                      <span>{formatAestDayMonth(session.startAt)}</span>
                      <span>{formatAestTime(session.startAt)}</span>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="circuit-schedule-footnote">*AEST (UTC+10)</div>
          </div>
        )}

        {/* Prev / Next circuit nav arrows */}
        {trackKeys.length > 0 && (
          <>
            <button
              className="circuit-nav-arrow circuit-nav-prev"
              onClick={handlePrevTrack}
              aria-label="Previous circuit"
            >
              <svg
                viewBox="0 0 24 24"
                width="32"
                height="32"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button
              className="circuit-nav-arrow circuit-nav-next"
              onClick={handleNextTrack}
              aria-label="Next circuit"
            >
              <svg
                viewBox="0 0 24 24"
                width="32"
                height="32"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="9 6 15 12 9 18" />
              </svg>
            </button>
          </>
        )}

        {/* Controls hint */}
        <div className="circuit-controls-hint">
          <span>CLICK + DRAG TO ROTATE</span>
          <span>SCROLL TO ZOOM</span>
        </div>

        {/* Past winners panel */}
        {!loading &&
          selectedTrackMeta &&
          selectedTrackMeta.history.length > 0 && (
            <div className="circuit-history-panel">
              <div className="circuit-history-topbar">
                <span className="circuit-history-heading">Past Winners</span>
                <span className="circuit-history-flag">
                  {selectedTrackMeta.flag}
                </span>
              </div>
              <div className="circuit-history-columns">
                <span>Year</span>
                <span>Winner</span>
              </div>
              <div className="circuit-history-list">
                {selectedTrackMeta.history.map((entry) => (
                  <div key={entry.year} className="circuit-history-row">
                    <span className="circuit-history-year">{entry.year}</span>
                    <span className="circuit-history-winner">
                      {entry.winner}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

        {/* Track selector */}
        {trackKeys.length > 0 && (
          <div className="circuit-track-selector">
            <label>Select Circuit</label>
            <select value={selectedTrack} onChange={handleTrackChange}>
              {tracks.map((track) => (
                <option key={track.key} value={track.key}>
                  {track.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Bottom gradient overlay for seamless bleed into dashboard */}
      <div
        className="circuit-hero-gradient-overlay"
        style={{ opacity: overlayOpacity }}
      />

      {/* Scroll down indicator — fade out as user scrolls */}
      <button
        className="scroll-down-indicator"
        onClick={handleScrollDown}
        aria-label="Scroll down"
        style={{ opacity: Math.max(0, 1 - scrollProgress * 3) }}
      >
        <div className="scroll-arrow" />
        <span className="scroll-text">EXPLORE</span>
      </button>
    </section>
  );
}
