import MiniSectors from "./MiniSectors";
import { useLiveTimingStore } from "../../stores/liveTimingStore";
import type {
  DriverInfo,
  TimingDataDriver,
  GapMode,
  TyreCompound,
} from "../../types/liveTiming";

interface Props {
  driverNum: string;
  driver: DriverInfo | undefined;
  timing: TimingDataDriver;
  gapMode: GapMode;
  isFastestInTeam: boolean;
}

const TYRE_COLORS: Record<string, string> = {
  SOFT: "#e10600",
  MEDIUM: "#eab308",
  HARD: "#ccc",
  INTERMEDIATE: "#22c55e",
  WET: "#3b82f6",
};

function lapTimeClass(lt?: { OverallFastest?: boolean; PersonalFastest?: boolean }): string {
  if (!lt) return "";
  if (lt.OverallFastest) return "purple";
  if (lt.PersonalFastest) return "green";
  return "";
}

function getCurrentCompound(stints: unknown): TyreCompound {
  if (!stints || typeof stints !== "object") return "";
  const arr = Array.isArray(stints) ? stints : Object.values(stints as Record<string, unknown>);
  if (arr.length === 0) return "";
  const last = arr[arr.length - 1] as { Compound?: TyreCompound } | null;
  return last?.Compound ?? "";
}

export default function DriverRow({ driverNum, driver, timing, gapMode, isFastestInTeam }: Props) {
  const stats = useLiveTimingStore((s) => s.timingStats[driverNum]);
  const appData = useLiveTimingStore((s) => s.timingAppData[driverNum]);
  const teamColor = `#${driver?.TeamColour ?? "ffffff"}`;
  const isLeader = timing.Position === "1";

  const compound = getCurrentCompound(appData?.Stints);
  const tyreColor = TYRE_COLORS[compound] ?? "#555";

  const gapValue =
    gapMode === "leader"
      ? timing.GapToLeader
      : timing.IntervalToPositionAhead?.Value ?? "";

  const rowClasses = [
    "driver-row",
    isLeader ? "leader" : "",
    timing.InPit ? " in-pit" : "",
    timing.PitOut ? " pit-out" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rowClasses}>
      <div className="dr-pos">
        <span className="pos-badge" style={{ borderLeftColor: teamColor }}>
          {timing.Position}
        </span>
      </div>

      <div className="dr-driver">
        <span className="team-bar" style={{ backgroundColor: teamColor }} />
        <span className={`driver-tla${isFastestInTeam ? " team-fastest" : ""}`}>
          {driver?.Tla ?? driverNum}
        </span>
      </div>

      <div className="dr-gap mono">
        {timing.Position === "1" ? "" : gapValue}
      </div>

      {[0, 1, 2].map((idx) => (
        <div key={idx} className="dr-sector">
          <MiniSectors
            sector={timing.Sectors?.[idx]}
            bestSector={stats?.BestSectors?.[idx]}
          />
        </div>
      ))}

      <div className="dr-laptime">
        <div className={`laptime-best mono ${lapTimeClass(timing.BestLapTime)}`}>
          {timing.BestLapTime?.Value ?? ""}
        </div>
        <div className={`laptime-last mono ${lapTimeClass(timing.LastLapTime)}`}>
          {timing.LastLapTime?.Value ?? ""}
        </div>
      </div>

      <div className="dr-tyre">
        {compound && (
          <span className="tyre-badge" style={{ borderColor: tyreColor, color: tyreColor }}>
            {compound[0]}
          </span>
        )}
      </div>
    </div>
  );
}
