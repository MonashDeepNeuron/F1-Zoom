import { useMemo } from "react";
import { useLiveTimingStore } from "../../stores/liveTimingStore";
import DriverRow from "./DriverRow";

export default function LiveTimingTable() {
  const timingData = useLiveTimingStore((s) => s.timingData);
  const driverList = useLiveTimingStore((s) => s.driverList);
  const gapMode = useLiveTimingStore((s) => s.gapMode);
  const toggleGapMode = useLiveTimingStore((s) => s.toggleGapMode);

  const sorted = Object.entries(timingData).sort(([, a], [, b]) => {
    const pa = parseInt(a.Position) || 99;
    const pb = parseInt(b.Position) || 99;
    return pa - pb;
  });

  const fastestInTeam = useMemo(() => {
    const teamBest: Record<string, { num: string; time: number }> = {};
    for (const [num] of sorted) {
      const driver = driverList[num];
      const best = timingData[num]?.BestLapTime?.Value;
      if (!driver?.TeamName || !best) continue;
      const parts = best.split(":");
      const secs = parts.length === 2
        ? parseFloat(parts[0]) * 60 + parseFloat(parts[1])
        : parseFloat(parts[0]);
      if (isNaN(secs)) continue;
      const existing = teamBest[driver.TeamName];
      if (!existing || secs < existing.time) {
        teamBest[driver.TeamName] = { num, time: secs };
      }
    }
    const result = new Set<string>();
    for (const v of Object.values(teamBest)) result.add(v.num);
    return result;
  }, [sorted, driverList, timingData]);

  return (
    <div className="timing-table-wrapper">
      <div className="timing-table-header">
        <div className="th-pos">P</div>
        <div className="th-driver">DRIVER</div>
        <div className="th-gap clickable" onClick={toggleGapMode}>
          {gapMode === "leader" ? "LEADER" : "INTERVAL"}{" "}
          <span className="toggle-icon">&#x21C5;</span>
        </div>
        <div className="th-sector">S1</div>
        <div className="th-sector">S2</div>
        <div className="th-sector">S3</div>
        <div className="th-time">LAP TIME</div>
        <div className="th-tyre">TYRE</div>
      </div>

      <div className="timing-table-body">
        {sorted.map(([num, data]) => (
          <DriverRow
            key={num}
            driverNum={num}
            driver={driverList[num]}
            timing={data}
            gapMode={gapMode}
            isFastestInTeam={fastestInTeam.has(num)}
          />
        ))}
      </div>
    </div>
  );
}
