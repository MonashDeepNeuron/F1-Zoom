import { useEffect, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { buildCircuitScene } from "../../three/buildCircuitScene";
import {
  clamp01,
  easeInOutCubic,
  easeInOutQuart,
  easeInQuad,
  easeOutQuart,
  lerp,
} from "./easing";

export type SceneStatus = "loading" | "playing" | "completed" | "error";

export interface LandingIntroSceneOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  blurLayerRef: RefObject<HTMLDivElement | null>;
  circuitName: string;
  trackSrc?: string;
  /** Focal point in raw CSV coordinate space. When omitted, the cinematic
   *  ends centred on the track's bounding-box centroid (scene origin). */
  zoomTarget?: { x: number; y: number };
  /** Resolve the focal point from a `corner_id` value embedded in the
   *  TrackCoordinateJS/CSV source. Ignored if `zoomTarget` is provided.
   *  Falls back to the centroid if the corner id can't be resolved. */
  zoomTargetCornerId?: number;
  durationMs: number;
  isActive: boolean;
  trackLengthKm?: number | null;
  onProgress?: (progress: number) => void;
  onComplete?: () => void;
  onError?: (message: string) => void;
}

interface CameraTween {
  startDistance: number;
  endDistance: number;
  startPhi: number;
  endPhi: number;
  startTheta: number;
  endTheta: number;
  startLook: THREE.Vector3;
  endLook: THREE.Vector3;
}

const SHAKE_START = 0.82;
const PEAK_BLUR_PX = 4;

function defaultTrackUrl(circuitName: string): string {
  return `/circuit_3d/TrackCoordinateJS/${circuitName}.js`;
}

/**
 * Resolve a raw CSV-space (x_m, y_m) coordinate for a given `corner_id`
 * from the TrackCoordinateJS/CSV source text. Prefers the row where
 * `is_corner_apex === 1` (or legacy `is_corner === 1`); otherwise returns
 * the first matching row. Returns `null` if the source has no
 * `corner_id` column or if no row matches.
 */
function resolveCornerRawCoord(
  rawText: string,
  cornerId: number,
): { x: number; y: number } | null {
  // Strip JS template-literal wrapper if present (mirrors `parseTrackData`).
  let csv = rawText;
  const wrapperMatch = rawText.match(/`([\s\S]*)`/);
  if (wrapperMatch) csv = wrapperMatch[1];

  const lines = csv.trim().split("\n");

  let xIdx = 0;
  let yIdx = 1;
  let apexIdx = -1;
  let legacyIdx = -1;
  let cornerIdIdx = -1;
  let headerSeen = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line.startsWith("#")) continue;
    const headerLine = line.replace(/^#+\s*/, "");
    const cols = headerLine.split(",").map((c) => c.trim());
    if (cols.length < 2) continue;
    const xCandidate = cols.findIndex((c) => c === "x_m");
    const yCandidate = cols.findIndex((c) => c === "y_m");
    if (xCandidate >= 0) xIdx = xCandidate;
    if (yCandidate >= 0) yIdx = yCandidate;
    apexIdx = cols.findIndex((c) => c === "is_corner_apex");
    legacyIdx = cols.findIndex((c) => c === "is_corner");
    cornerIdIdx = cols.findIndex((c) => c === "corner_id");
    headerSeen = true;
    break;
  }

  if (!headerSeen || cornerIdIdx < 0) return null;

  let firstMatch: { x: number; y: number } | null = null;
  let apexMatch: { x: number; y: number } | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.length === 0 || line.startsWith("#")) continue;
    const parts = line.split(",");
    if (parts.length <= cornerIdIdx) continue;
    const cid = parseInt(parts[cornerIdIdx].trim(), 10);
    if (cid !== cornerId) continue;

    const x = parseFloat(parts[xIdx]);
    const y = parseFloat(parts[yIdx]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;

    if (!firstMatch) firstMatch = { x, y };

    if (apexIdx >= 0 && parts.length > apexIdx) {
      if (parts[apexIdx].trim() === "1") {
        apexMatch = { x, y };
        break;
      }
    } else if (legacyIdx >= 0 && parts.length > legacyIdx) {
      if (parts[legacyIdx].trim() === "1" && !apexMatch) {
        apexMatch = { x, y };
      }
    }
  }

  return apexMatch ?? firstMatch;
}

/**
 * Builds the canonical CircuitHero scene (via `buildCircuitScene`) and
 * animates a cinematic top-down -> focal-point camera fly-in over
 * `durationMs`. Drives an external blur layer through a CSS variable so
 * callers can layer the motion blur on top of the canvas without
 * postprocessing dependencies.
 */
export function useLandingIntroScene({
  containerRef,
  blurLayerRef,
  circuitName,
  trackSrc,
  zoomTarget,
  zoomTargetCornerId,
  durationMs,
  isActive,
  trackLengthKm,
  onProgress,
  onComplete,
  onError,
}: LandingIntroSceneOptions): { status: SceneStatus; error: string | null } {
  const [status, setStatus] = useState<SceneStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  // Latest callback refs so the rAF loop never closes over stale handlers.
  const onProgressRef = useRef(onProgress);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (!isActive) return;
    const container = containerRef.current;
    if (!container) return;

    const trackUrl = trackSrc ?? defaultTrackUrl(circuitName);

    let cancelled = false;
    let rafId: number | null = null;
    let renderer: THREE.WebGLRenderer | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let disposeScene: (() => void) | null = null;

    setStatus("loading");
    setError(null);

    fetch(trackUrl, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status} for ${trackUrl}`);
        return res.text();
      })
      .then((csvText) => {
        if (cancelled) return;

        const built = buildCircuitScene({
          csvText,
          themeKey: circuitName,
          lengthKm: trackLengthKm ?? null,
        });
        if (built.rawPoints.length < 2) {
          built.dispose();
          throw new Error("Track data has too few points");
        }
        disposeScene = built.dispose;
        const { scene, trackElevation } = built;

        // Default focal point: project the layout centroid -> scene origin,
        // so callers can omit `zoomTarget` and still land on the track.
        // If only a corner id is supplied, resolve it to a raw (x, y) from
        // the source CSV/JS first; fall through to centroid on miss.
        const resolvedRaw =
          zoomTarget ??
          (typeof zoomTargetCornerId === "number"
            ? resolveCornerRawCoord(csvText, zoomTargetCornerId) ?? undefined
            : undefined);
        const focal = resolvedRaw
          ? built.project(resolvedRaw)
          : { x: 0, z: 0 };

        const width = container.clientWidth || window.innerWidth;
        const height = container.clientHeight || window.innerHeight;
        const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);

        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setSize(width, height);
        container.appendChild(renderer.domElement);

        // ── Camera tween config ────────────────────────────────────
        const tween: CameraTween = {
          startDistance: 90,
          endDistance: 14,
          startPhi: 0.001, // near-zero phi = top-down (avoid gimbal singularity)
          endPhi: Math.PI / 3,
          startTheta: 0,
          endTheta: Math.PI / 8,
          startLook: new THREE.Vector3(0, trackElevation, 0),
          endLook: new THREE.Vector3(focal.x, trackElevation, focal.z),
        };

        const positionBase = new THREE.Vector3();
        const lookTarget = new THREE.Vector3();
        const blurEl = blurLayerRef.current;

        const startTime = performance.now();
        let completedFired = false;

        const renderFrame = () => {
          if (cancelled || !renderer) return;
          const now = performance.now();
          const elapsed = now - startTime;
          const tRaw = elapsed / Math.max(1, durationMs);
          const t = clamp01(tRaw);

          const distEase = easeInOutCubic(t);
          const phiEase = easeInOutQuart(t);
          const lookEase = easeInOutCubic(t);

          const distance = lerp(tween.startDistance, tween.endDistance, distEase);
          const phi = lerp(tween.startPhi, tween.endPhi, phiEase);
          const theta = lerp(tween.startTheta, tween.endTheta, distEase);

          positionBase.set(
            distance * Math.sin(phi) * Math.cos(theta),
            distance * Math.cos(phi),
            distance * Math.sin(phi) * Math.sin(theta),
          );

          // Camera shake ramps up over the last (1 - SHAKE_START) of the run.
          if (t > SHAKE_START) {
            const shakeT = (t - SHAKE_START) / (1 - SHAKE_START);
            const shakeAmp = easeInQuad(shakeT) * 0.45;
            positionBase.x += (Math.random() - 0.5) * shakeAmp;
            positionBase.y += (Math.random() - 0.5) * shakeAmp * 0.6;
            positionBase.z += (Math.random() - 0.5) * shakeAmp;
          }

          camera.position.copy(positionBase);

          lookTarget.lerpVectors(tween.startLook, tween.endLook, lookEase);
          camera.lookAt(lookTarget);

          // Drive the canonical breathing/pulsing on the shared scene.
          built.tick(now * 0.001);

          if (blurEl) {
            const blurEnvelope = Math.sin(t * Math.PI);
            const px = (PEAK_BLUR_PX * blurEnvelope).toFixed(2);
            blurEl.style.setProperty("--landing-intro-blur", `${px}px`);
            blurEl.style.setProperty(
              "--landing-intro-blur-opacity",
              easeOutQuart(blurEnvelope).toFixed(3),
            );
          }

          onProgressRef.current?.(t);
          renderer.render(scene, camera);

          if (t >= 1) {
            if (!completedFired) {
              completedFired = true;
              setStatus("completed");
              onCompleteRef.current?.();
            }
            return;
          }

          rafId = requestAnimationFrame(renderFrame);
        };

        const handleResize = () => {
          if (!renderer) return;
          const w = container.clientWidth || window.innerWidth;
          const h = container.clientHeight || window.innerHeight;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        };

        if (typeof ResizeObserver !== "undefined") {
          resizeObserver = new ResizeObserver(handleResize);
          resizeObserver.observe(container);
        } else {
          window.addEventListener("resize", handleResize);
        }

        setStatus("playing");
        rafId = requestAnimationFrame(renderFrame);

        return handleResize;
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Failed to load track data";
        console.error("[LandingIntro] failed to initialise scene", err);
        setError(message);
        setStatus("error");
        onErrorRef.current?.(message);
      });

    // Capture mutable refs once for the cleanup closure.
    const blurEl = blurLayerRef.current;

    return () => {
      cancelled = true;
      if (rafId !== null) cancelAnimationFrame(rafId);
      if (resizeObserver) resizeObserver.disconnect();
      if (renderer) {
        const dom = renderer.domElement;
        if (dom.parentElement) dom.parentElement.removeChild(dom);
        renderer.dispose();
        renderer = null;
      }
      if (disposeScene) {
        try {
          disposeScene();
        } catch {
          // ignore
        }
        disposeScene = null;
      }
      if (blurEl) {
        blurEl.style.setProperty("--landing-intro-blur", "0px");
        blurEl.style.setProperty("--landing-intro-blur-opacity", "0");
      }
    };
    // We intentionally re-run when key inputs change; callbacks live in refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isActive,
    circuitName,
    trackSrc,
    durationMs,
    trackLengthKm,
    zoomTarget?.x,
    zoomTarget?.y,
    zoomTargetCornerId,
  ]);

  return { status, error };
}
