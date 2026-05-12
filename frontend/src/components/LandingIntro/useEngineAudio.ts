import { useCallback, useEffect, useRef, useState } from "react";
import { clamp01, easeOutQuart } from "./easing";

export type EngineAudioStatus =
  | "idle"
  | "playing"
  | "blocked"
  | "ended"
  | "unsupported";

export interface EngineAudioControls {
  status: EngineAudioStatus;
  /** Drive volume from outside; expects 0..1 progress. */
  setProgress: (progress: number) => void;
  /** Manually start playback (call from a user gesture if autoplay is blocked). */
  start: () => void;
  /** Fade out and stop. Resolves when the audio is paused. */
  stop: (fadeMs?: number) => Promise<void>;
}

const DEFAULT_TARGET_VOLUME = 0.6;

/**
 * Manages an HTMLAudioElement whose volume is driven by external animation
 * progress. Tries to autoplay on mount; falls back to `status === "blocked"`
 * so the caller can render a "tap to start" affordance.
 */
export function useEngineAudio(
  audioSrc: string | undefined,
  targetVolume: number = DEFAULT_TARGET_VOLUME,
): EngineAudioControls {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fadeRafRef = useRef<number | null>(null);
  // Initial status is derived from the first `audioSrc` value. Changing
  // `audioSrc` at runtime is not supported (treat the audio source as
  // immutable per intro mount) — to swap audio, remount with a `key`.
  const [status, setStatus] = useState<EngineAudioStatus>(
    audioSrc ? "idle" : "unsupported",
  );

  // Construct / tear down the audio element when the source changes.
  useEffect(() => {
    if (!audioSrc) {
      audioRef.current = null;
      return;
    }

    const audio = new Audio(audioSrc);
    audio.loop = true;
    audio.preload = "auto";
    audio.volume = 0;
    audioRef.current = audio;

    let cancelled = false;
    // Defer the autoplay attempt to a microtask so any setState lives in
    // an async callback (keeps react-hooks/set-state-in-effect happy).
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.then === "function") {
      playPromise.then(
        () => {
          if (!cancelled) setStatus("playing");
        },
        () => {
          if (!cancelled) setStatus("blocked");
        },
      );
    } else {
      // Older browsers: promise-less play(). Schedule the status update
      // out of the effect body.
      const handle = window.setTimeout(() => {
        if (!cancelled) setStatus("playing");
      }, 0);
      // Make sure the cleanup also clears the scheduled update.
      const prevCleanup = () => window.clearTimeout(handle);
      // Stash on the audio element so the cleanup below can access it.
      (audio as HTMLAudioElement & { __pendingTimeout?: () => void }).__pendingTimeout =
        prevCleanup;
    }

    return () => {
      cancelled = true;
      const pending = (audio as HTMLAudioElement & {
        __pendingTimeout?: () => void;
      }).__pendingTimeout;
      pending?.();
      if (fadeRafRef.current !== null) {
        cancelAnimationFrame(fadeRafRef.current);
        fadeRafRef.current = null;
      }
      try {
        audio.pause();
        audio.src = "";
        audio.load();
      } catch {
        // ignore teardown errors
      }
      audioRef.current = null;
    };
  }, [audioSrc]);

  const setProgress = useCallback(
    (progress: number) => {
      const audio = audioRef.current;
      if (!audio) return;
      const eased = easeOutQuart(clamp01(progress));
      const nextVolume = Math.max(0, Math.min(1, targetVolume * eased));
      // Avoid spamming identical assignments (helps Safari).
      if (Math.abs(audio.volume - nextVolume) > 0.001) {
        audio.volume = nextVolume;
      }
    },
    [targetVolume],
  );

  const start = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.then === "function") {
      playPromise
        .then(() => setStatus("playing"))
        .catch(() => setStatus("blocked"));
    } else {
      setStatus("playing");
    }
  }, []);

  const stop = useCallback((fadeMs = 400) => {
    const audio = audioRef.current;
    if (!audio) return Promise.resolve();

    if (fadeRafRef.current !== null) {
      cancelAnimationFrame(fadeRafRef.current);
      fadeRafRef.current = null;
    }

    const startVolume = audio.volume;
    if (startVolume <= 0.001 || fadeMs <= 0) {
      audio.pause();
      setStatus("ended");
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      const startTime = performance.now();
      const tick = () => {
        const elapsed = performance.now() - startTime;
        const t = clamp01(elapsed / fadeMs);
        audio.volume = startVolume * (1 - t);
        if (t >= 1) {
          fadeRafRef.current = null;
          audio.pause();
          audio.volume = 0;
          setStatus("ended");
          resolve();
          return;
        }
        fadeRafRef.current = requestAnimationFrame(tick);
      };
      fadeRafRef.current = requestAnimationFrame(tick);
    });
  }, []);

  return { status, setProgress, start, stop };
}
