import MiniSectors from "./MiniSectors";
import { useLiveTimingStore } from "../../stores/liveTimingStore";
import type {
  DriverInfo,
  TimingDataDriver,
  GapMode,
} from "../../types/liveTiming";

interface Props {
  driverNum: string;
  driver: DriverInfo | undefined;
  timing: TimingDataDriver;
  gapMode: GapMode;
}

function lapTimeClass(lt?: { OverallFastest?: boolean; PersonalFastest?: boolean }): string {
  if (!lt) return "";
  if (lt.OverallFastest) return "purple";
  if (lt.PersonalFastest) return "green";
  return "";
}

export default function DriverRow({ driverNum, driver, timing, gapMode }: Props) {
  const stats = useLiveTimingStore((s) => s.timingStats[driverNum]);
  const teamColor = `#${driver?.TeamColour ?? "ffffff"}`;
  const isLeader = timing.Position === "1";

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
        <span className="driver-tla">{driver?.Tla ?? driverNum}</span>
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

      <div className={`dr-time mono ${lapTimeClass(timing.LastLapTime)}`}>
        {timing.LastLapTime?.Value ?? ""}
      </div>

      <div className={`dr-time mono best ${lapTimeClass(timing.BestLapTime)}`}>
        {timing.BestLapTime?.Value ?? ""}
      </div>
    </div>
  );
}
