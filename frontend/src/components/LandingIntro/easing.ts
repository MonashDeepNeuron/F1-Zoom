export type EasingFn = (t: number) => number;

export const clamp01 = (t: number): number =>
  t < 0 ? 0 : t > 1 ? 1 : t;

export const linear: EasingFn = (t) => clamp01(t);

export const easeInOutCubic: EasingFn = (t) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};

export const easeInOutQuart: EasingFn = (t) => {
  const x = clamp01(t);
  return x < 0.5 ? 8 * x * x * x * x : 1 - Math.pow(-2 * x + 2, 4) / 2;
};

export const easeOutQuart: EasingFn = (t) => {
  const x = clamp01(t);
  return 1 - Math.pow(1 - x, 4);
};

export const easeInQuad: EasingFn = (t) => {
  const x = clamp01(t);
  return x * x;
};

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
