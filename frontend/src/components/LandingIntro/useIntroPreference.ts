import { useCallback, useState } from "react";

const DISMISSED_VALUE = "dismissed";

function readDismissed(key: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(key) === DISMISSED_VALUE;
  } catch {
    return false;
  }
}

function writeDismissed(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, DISMISSED_VALUE);
  } catch {
    // Storage may be unavailable (private mode, quota); intro will simply
    // replay next visit.
  }
}

function clearDismissed(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export interface IntroPreference {
  shouldPlay: boolean;
  markDismissed: () => void;
  reset: () => void;
}

/**
 * Gates whether the landing intro should play based on a localStorage flag.
 * Pass `forcePlay` to bypass the stored preference (useful for previews).
 */
export function useIntroPreference(
  key: string,
  forcePlay = false,
): IntroPreference {
  const [shouldPlay, setShouldPlay] = useState<boolean>(
    () => forcePlay || !readDismissed(key),
  );

  const markDismissed = useCallback(() => {
    writeDismissed(key);
    setShouldPlay(false);
  }, [key]);

  const reset = useCallback(() => {
    clearDismissed(key);
    setShouldPlay(true);
  }, [key]);

  return { shouldPlay, markDismissed, reset };
}
