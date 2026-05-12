import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import RaceMiniGame from "../RaceMiniGame/RaceMiniGame";
import "../../styles/LandingIntro.css";
import { useEngineAudio } from "./useEngineAudio";
import { useIntroPreference } from "./useIntroPreference";
import { useLandingIntroScene } from "./useLandingIntroScene";

export type LandingIntroCompletionReason = "finished" | "skipped";

export interface LandingIntroProps {
  /** Track key matching a file under /circuit_3d/TrackCoordinateJS (e.g. "Melbourne"). */
  circuitName: string;
  /** Override URL to the TrackCoordinateJS file; defaults from `circuitName`. */
  trackSrc?: string;
  /** Focal point in the source CSV coordinate space (raw x_m, y_m). When
   *  omitted, the camera ends centred on the track's bounding-box centroid. */
  zoomTarget?: { x: number; y: number };
  /** Resolve the focal point from a `corner_id` value embedded in the
   *  TrackCoordinateJS/CSV source. Ignored if `zoomTarget` is provided. */
  zoomTargetCornerId?: number;
  /** Optional track length used to size the projection (matches CircuitHero). */
  trackLengthKm?: number | null;
  /** Path to a looping engine audio file. Optional — intro will run silently. */
  audioSrc?: string;
  /** Peak audio volume (0..1). Default 0.6. */
  audioTargetVolume?: number;
  /** Total cinematic duration in ms. Default 6000. */
  durationMs?: number;
  /** localStorage key for the dismissed flag. Default `f1zoom:landing-intro:${circuitName}`. */
  storageKey?: string;
  /** Bypass the stored preference and force the intro to play. */
  forcePlay?: boolean;
  /** Optional MP4/WebM URL. When provided, the intro cross-fades from the
   *  3D zoom into this video instead of dismissing immediately. */
  endVideoSrc?: string;
  /** Optional poster image for the end video (avoids a flash of black). */
  endVideoPosterSrc?: string;
  /** Cross-fade duration between the 3D zoom and the video. Default 700ms. */
  endVideoFadeMs?: number;
  /** Try to autoplay with audio. Falls back to muted + a "Tap for audio"
   *  prompt if the browser blocks audible autoplay. Default true. */
  endVideoWithAudio?: boolean;
  /** Loop the end video. When false (default), the overlay dismisses on
   *  the video's `ended` event. */
  endVideoLoop?: boolean;
  /** When true, the cinematic transitions into a playable pixel mini
   *  racing game on the same circuit instead of dismissing or playing a
   *  video. Takes priority over `endVideoSrc` if both are provided. */
  endGame?: boolean;
  /** Fired when the intro ends (either `"finished"` or `"skipped"`). */
  onComplete?: (reason: LandingIntroCompletionReason) => void;
  /** Rendered after the intro finishes or when the preference says skip. */
  children?: ReactNode;
}

const DEFAULT_DURATION_MS = 6000;
const DEFAULT_VOLUME = 0.6;
const FADE_OUT_MS = 320;
const DEFAULT_VIDEO_FADE_MS = 700;

function defaultStorageKey(circuitName: string): string {
  return `f1zoom:landing-intro:${circuitName}`;
}

export default function LandingIntro({
  circuitName,
  trackSrc,
  zoomTarget,
  zoomTargetCornerId,
  trackLengthKm = null,
  audioSrc,
  audioTargetVolume = DEFAULT_VOLUME,
  durationMs = DEFAULT_DURATION_MS,
  storageKey,
  forcePlay = false,
  endVideoSrc,
  endVideoPosterSrc,
  endVideoFadeMs = DEFAULT_VIDEO_FADE_MS,
  endVideoWithAudio = true,
  endVideoLoop = false,
  endGame = false,
  onComplete,
  children,
}: LandingIntroProps) {
  const resolvedKey = storageKey ?? defaultStorageKey(circuitName);
  const { shouldPlay, markDismissed } = useIntroPreference(
    resolvedKey,
    forcePlay,
  );

  // `isPlaying` controls active rendering; `isVisible` controls overlay
  // visibility (allows a fade-out before unmount). Both are seeded once
  // from `shouldPlay`. To replay after dismissal, remount with a fresh
  // React `key` (or call `useIntroPreference(key).reset()` then remount).
  const [isPlaying, setIsPlaying] = useState<boolean>(shouldPlay);
  const [isVisible, setIsVisible] = useState<boolean>(shouldPlay);
  // `intro` while the 3D zoom is playing; `video` once the camera tween
  // completes and we begin the cross-fade into `endVideoSrc`; `game`
  // when transitioning into the pixel mini racing game instead.
  const [phase, setPhase] = useState<"intro" | "video" | "game">("intro");
  // `true` when we wanted audio but the browser blocked audible autoplay
  // and we fell back to muted; reveals a "Tap for audio" affordance.
  const [videoNeedsTap, setVideoNeedsTap] = useState(false);
  const finishedRef = useRef(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const blurLayerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const audio = useEngineAudio(audioSrc, audioTargetVolume);
  const audioSetProgress = audio.setProgress;
  const audioStop = audio.stop;
  const audioStart = audio.start;

  const finish = useCallback(
    (reason: LandingIntroCompletionReason) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      markDismissed();
      void audioStop(FADE_OUT_MS);
      setIsVisible(false);
      // Allow the CSS fade-out before unmounting the canvas.
      window.setTimeout(() => {
        setIsPlaying(false);
        onComplete?.(reason);
      }, FADE_OUT_MS);
    },
    [markDismissed, audioStop, onComplete],
  );

  const handleProgress = useCallback(
    (t: number) => {
      audioSetProgress(t);
    },
    [audioSetProgress],
  );

  // When the camera tween finishes, branch on the configured end-stage:
  //   - `endGame`     → transition into the playable mini racing game.
  //   - `endVideoSrc` → cross-fade into the video.
  //   - otherwise     → dismiss the overlay and reveal the page.
  const handleSceneComplete = useCallback(() => {
    if (endGame) {
      void audioStop(FADE_OUT_MS);
      setPhase("game");
      return;
    }
    if (endVideoSrc) {
      void audioStop(FADE_OUT_MS);
      setPhase("video");
    } else {
      finish("finished");
    }
  }, [endGame, endVideoSrc, audioStop, finish]);

  // If the scene blows up (e.g. bad track URL), don't trap the user behind
  // the overlay — finish silently so children render.
  const handleSceneError = useCallback(() => {
    finish("finished");
  }, [finish]);

  const { status: sceneStatus, error: sceneError } = useLandingIntroScene({
    containerRef,
    blurLayerRef,
    circuitName,
    trackSrc,
    zoomTarget,
    zoomTargetCornerId,
    durationMs,
    isActive: isPlaying,
    trackLengthKm,
    onProgress: handleProgress,
    onComplete: handleSceneComplete,
    onError: handleSceneError,
  });

  // Best-effort autoplay with audio. If the browser rejects audible
  // autoplay, fall back to muted and reveal a "Tap for audio" prompt that
  // unmutes from a user gesture.
  useEffect(() => {
    if (phase !== "video") return;
    const video = videoRef.current;
    if (!video) return;

    let cancelled = false;
    video.muted = !endVideoWithAudio;
    setVideoNeedsTap(false);

    const playPromise = video.play();
    if (playPromise && typeof playPromise.then === "function") {
      playPromise.catch(() => {
        if (cancelled) return;
        if (!endVideoWithAudio) return;
        // Audible autoplay blocked — retry muted so something plays, and
        // surface the unmute affordance.
        video.muted = true;
        setVideoNeedsTap(true);
        video.play().catch(() => {
          // Even muted playback failed; nothing safe to do here.
        });
      });
    }

    return () => {
      cancelled = true;
    };
  }, [phase, endVideoWithAudio]);

  const handleUnmuteVideo = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = false;
    setVideoNeedsTap(false);
    void video.play();
  }, []);

  const handleVideoEnded = useCallback(() => {
    if (endVideoLoop) return;
    finish("finished");
  }, [endVideoLoop, finish]);

  // Esc key skips.
  useEffect(() => {
    if (!isPlaying) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        finish("skipped");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isPlaying, finish]);

  const overlayClassName = [
    "landing-intro-overlay",
    isVisible ? "is-visible" : "is-hidden",
    `phase-${phase}`,
  ].join(" ");

  const overlayStyle = {
    "--landing-intro-video-fade": `${endVideoFadeMs}ms`,
  } as CSSProperties;

  // Children stay mounted in a stable position so wrapped trees (e.g. the
  // 3D CircuitHero) don't reset state when the overlay fades out.
  return (
    <>
      {isPlaying && (
        <div
          className={overlayClassName}
          style={overlayStyle}
          role="dialog"
          aria-label={`${circuitName} landing intro`}
        >
          <div className="landing-intro-canvas" ref={containerRef} />
          <div className="landing-intro-motion-blur" ref={blurLayerRef} />

          {endVideoSrc && !endGame && (
            <div className="landing-intro-video-stage">
              <video
                ref={videoRef}
                className="landing-intro-video"
                src={endVideoSrc}
                poster={endVideoPosterSrc}
                playsInline
                preload="auto"
                loop={endVideoLoop}
                onEnded={handleVideoEnded}
              />
            </div>
          )}

          {endGame && (
            <div className="landing-intro-game-stage">
              <RaceMiniGame
                circuitName={circuitName}
                isActive={phase === "game"}
                onExit={() => finish("skipped")}
              />
            </div>
          )}

          {sceneStatus === "loading" && phase === "intro" && (
            <div className="landing-intro-status">Loading {circuitName}…</div>
          )}

          {sceneError && phase === "intro" && (
            <div className="landing-intro-status landing-intro-status-error">
              {sceneError}
            </div>
          )}

          {phase === "intro" && audio.status === "blocked" && (
            <button
              type="button"
              className="landing-intro-audio-prompt"
              onClick={audioStart}
            >
              Tap for sound
            </button>
          )}

          {phase === "video" && videoNeedsTap && (
            <button
              type="button"
              className="landing-intro-audio-prompt"
              onClick={handleUnmuteVideo}
            >
              Tap for audio
            </button>
          )}

          <button
            type="button"
            className="landing-intro-skip"
            onClick={() => finish("skipped")}
            aria-label="Skip intro"
          >
            Skip Intro <span aria-hidden="true">›</span>
          </button>

          <div className="landing-intro-circuit-label" aria-hidden="true">
            {circuitName}
          </div>
        </div>
      )}
      {children}
    </>
  );
}
