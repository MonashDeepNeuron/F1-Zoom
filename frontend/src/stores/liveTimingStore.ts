import { create } from "zustand";
import type {
  DriverInfo,
  TimingDataDriver,
  TimingStatsDriver,
  CarPosition,
  SessionInfo,
  GapMode,
} from "../types/liveTiming";

/* eslint-disable @typescript-eslint/no-explicit-any */

function deepMerge(base: any, update: any): any {
  if (
    base !== null &&
    typeof base === "object" &&
    update !== null &&
    typeof update === "object" &&
    !Array.isArray(update)
  ) {
    if (Array.isArray(base)) {
      const merged = [...base];
      for (const key of Object.keys(update)) {
        const idx = parseInt(key, 10);
        if (!isNaN(idx)) {
          while (merged.length <= idx) merged.push(null);
          merged[idx] =
            merged[idx] != null
              ? deepMerge(merged[idx], update[key])
              : update[key];
        }
      }
      return merged;
    }
    const merged = { ...base };
    for (const key of Object.keys(update)) {
      merged[key] =
        key in merged ? deepMerge(merged[key], update[key]) : update[key];
    }
    return merged;
  }
  return update;
}

interface LiveTimingState {
  connected: boolean;
  driverList: Record<string, DriverInfo>;
  timingData: Record<string, TimingDataDriver>;
  timingStats: Record<string, TimingStatsDriver>;
  positions: Record<string, CarPosition>;
  sessionInfo: SessionInfo | null;
  sessionStatus: string;
  trackStatus: string;
  gapMode: GapMode;

  setConnected: (val: boolean) => void;
  setInitialState: (data: any) => void;
  applyUpdate: (data: any) => void;
  toggleGapMode: () => void;
}

export const useLiveTimingStore = create<LiveTimingState>((set, get) => ({
  connected: false,
  driverList: {},
  timingData: {},
  timingStats: {},
  positions: {},
  sessionInfo: null,
  sessionStatus: "",
  trackStatus: "",
  gapMode: "leader",

  setConnected: (val) => set({ connected: val }),

  setInitialState: (data) =>
    set({
      driverList: data.DriverList ?? {},
      timingData: data.TimingData?.Lines ?? {},
      timingStats: data.TimingStats?.Lines ?? {},
      positions: data.Position?.Entries ?? {},
      sessionInfo: data.SessionInfo ?? null,
      sessionStatus: data.SessionStatus?.Status ?? "",
      trackStatus: data.TrackStatus?.Status ?? "",
    }),

  applyUpdate: (data) => {
    const s = get();
    const patch: Partial<LiveTimingState> = {};

    if (data.DriverList)
      patch.driverList = deepMerge(s.driverList, data.DriverList);
    if (data.TimingData?.Lines)
      patch.timingData = deepMerge(s.timingData, data.TimingData.Lines);
    if (data.TimingStats?.Lines)
      patch.timingStats = deepMerge(s.timingStats, data.TimingStats.Lines);
    if (data.Position?.Entries)
      patch.positions = deepMerge(s.positions, data.Position.Entries);
    if (data.SessionInfo)
      patch.sessionInfo = deepMerge(s.sessionInfo ?? {}, data.SessionInfo);
    if (data.SessionStatus?.Status)
      patch.sessionStatus = data.SessionStatus.Status;
    if (data.TrackStatus?.Status)
      patch.trackStatus = data.TrackStatus.Status;

    if (Object.keys(patch).length > 0) set(patch);
  },

  toggleGapMode: () =>
    set((s) => ({ gapMode: s.gapMode === "leader" ? "interval" : "leader" })),
}));
