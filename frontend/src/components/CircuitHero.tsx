import { useRef, useEffect, useState, useCallback } from "react";
import * as THREE from "three";
import { getCircuitsBySeason, getNextRace } from "../services/api";
import { buildCircuitScene } from "../three/buildCircuitScene";
import { CIRCUIT_THEME, hexToRgb, themeRgba } from "../three/trackScene";
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
  lengthKm: number;
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
  { key: "race", label: "Race" }
];

const AEST_TIME_ZONE = "Australia/Brisbane";
const AEST_DAY_FORMATTER = new Intl.DateTimeFormat("en-AU", {
  timeZone: AEST_TIME_ZONE,
  day: "numeric",
  month: "short"
});
const AEST_TIME_FORMATTER = new Intl.DateTimeFormat("en-AU", {
  timeZone: AEST_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: false
});

const DEFAULT_SEASON = new Date().getFullYear();

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
    lengthKm: row.lengthKm,
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
    subtitle: "ALBERT PARK CIRCUIT (FASTF1 V2)"
  };

  return [
    melbourne,
    melbourne2,
    ...tracks.filter((track) => track.key !== "Melbourne")
  ];
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
    cameraDistance: 30
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

  const initTrackScene = useCallback((csvData: string, fileSlug?: string, lengthKm?: number | null) => {
    const container = containerRef.current;
    if (!container) return;

    const camera = new THREE.PerspectiveCamera(
      50,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Build the canonical circuit scene (track + glow layers + turn markers
    // + grid + lights + per-frame breathing) via the shared helper so the
    // landing intro and the hero render identically.
    const built = buildCircuitScene({
      csvText: csvData,
      themeKey: fileSlug ?? null,
      lengthKm: lengthKm ?? null,
    });
    const { scene, tick: tickScene } = built;

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
        Math.min(MAX_ZOOM_OUT, state.cameraDistance)
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

      tickScene(Date.now() * 0.001);

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
      built.dispose();
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
            cache: "no-store"
          }
        );
        if (!response.ok) {
          throw new Error(`Failed to load track data: ${meta.file}`);
        }
        const csvData = await response.text();
        if (currentLoadId !== loadIdRef.current) return;
        initTrackScene(csvData, meta.file, meta.lengthKm);
        requestAnimationFrame(() => {
          if (currentLoadId !== loadIdRef.current) return;
          setLoading(false);
        });
      } catch (error) {
        console.error("[F1] Failed to load track file:", meta.file, error);
        setLoading(false);
      }
    },
    [teardownScene, initTrackScene]
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
            .sort((a, b) => (a.round ?? 999) - (b.round ?? 999))
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
            : "Unable to load circuits from database."
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
    (session) => session.startAt.getTime() > nowMs
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
    transition: "none"
  };

  const overlayOpacity = scrollProgress * 0.9;
  const selectedTheme = CIRCUIT_THEME[selectedTrackMeta?.file ?? ""] ?? CIRCUIT_THEME.DEFAULT;
  const accentColor = selectedTheme.text;
  const { r: glowR, g: glowG, b: glowB } = hexToRgb(selectedTheme.glow);
  
  const containerStyle: React.CSSProperties = {
    ...heroParallaxStyle,
    '--accent-color': accentColor,
    '--theme-core-color': selectedTheme.core,
    '--theme-primary-color': selectedTheme.primary,
    '--theme-glow-color': selectedTheme.glow,
    '--glow-shadow-1': `rgba(${glowR}, ${glowG}, ${glowB}, 0.8)`,
    '--glow-shadow-2': `rgba(${glowR}, ${glowG}, ${glowB}, 0.5)`,
    '--glow-shadow-3': `rgba(${glowR}, ${glowG}, ${glowB}, 0.3)`,
    '--glow-shadow-bright-1': `rgba(${glowR}, ${glowG}, ${glowB}, 1)`,
    '--glow-shadow-bright-2': `rgba(${glowR}, ${glowG}, ${glowB}, 0.7)`,
    '--glow-shadow-bright-3': `rgba(${glowR}, ${glowG}, ${glowB}, 0.5)`,
    '--theme-panel-bg': `linear-gradient(135deg, ${themeRgba(selectedTheme.primary, 0.24)}, ${themeRgba(selectedTheme.glow, 0.08)}), rgba(6, 4, 7, 0.88)`,
    '--theme-control-bg': `linear-gradient(135deg, ${themeRgba(selectedTheme.primary, 0.28)}, ${themeRgba(selectedTheme.glow, 0.1)}), rgba(6, 4, 7, 0.88)`,
    '--theme-border-soft': themeRgba(selectedTheme.text, 0.22),
    '--theme-border': themeRgba(selectedTheme.text, 0.42),
    '--theme-border-strong': themeRgba(selectedTheme.text, 0.78),
    '--theme-row-border': themeRgba(selectedTheme.text, 0.13),
    '--theme-row-border-strong': themeRgba(selectedTheme.text, 0.18),
    '--theme-shadow': themeRgba(selectedTheme.glow, 0.14),
    '--theme-shadow-strong': themeRgba(selectedTheme.glow, 0.32),
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
                    isPast ? "is-past" : ""
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
            <div className="circuit-track-select-wrap">
              <select value={selectedTrack} onChange={handleTrackChange}>
                {tracks.map((track) => (
                  <option key={track.key} value={track.key}>
                    {track.title}
                  </option>
                ))}
              </select>
            </div>
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
