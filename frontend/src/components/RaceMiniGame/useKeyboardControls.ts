import { useEffect, useRef } from "react";

export interface RaceControls {
  forward: boolean;
  back: boolean;
  left: boolean;
  right: boolean;
}

/**
 * Mutable controls ref updated from `keydown` / `keyup` listeners so the
 * render loop can poll the latest input without re-subscribing each
 * frame. Listens to both WASD and arrow keys and `preventDefault`s the
 * relevant keys so arrow scrolling doesn't fight the game.
 */
export function useKeyboardControls(active: boolean) {
  const controlsRef = useRef<RaceControls>({
    forward: false,
    back: false,
    left: false,
    right: false,
  });

  useEffect(() => {
    if (!active) {
      controlsRef.current.forward = false;
      controlsRef.current.back = false;
      controlsRef.current.left = false;
      controlsRef.current.right = false;
      return;
    }

    const apply = (key: string, value: boolean) => {
      const k = key.toLowerCase();
      const c = controlsRef.current;
      if (k === "w" || k === "arrowup") c.forward = value;
      else if (k === "s" || k === "arrowdown") c.back = value;
      else if (k === "a" || k === "arrowleft") c.left = value;
      else if (k === "d" || k === "arrowright") c.right = value;
    };

    const isGameKey = (k: string) =>
      k === "w" || k === "a" || k === "s" || k === "d" ||
      k === "arrowup" || k === "arrowdown" ||
      k === "arrowleft" || k === "arrowright";

    const onDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (!isGameKey(k)) return;
      e.preventDefault();
      apply(e.key, true);
    };

    const onUp = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (!isGameKey(k)) return;
      apply(e.key, false);
    };

    const clear = () => {
      const c = controlsRef.current;
      c.forward = false;
      c.back = false;
      c.left = false;
      c.right = false;
    };

    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", clear);

    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("blur", clear);
      clear();
    };
  }, [active]);

  return controlsRef;
}
