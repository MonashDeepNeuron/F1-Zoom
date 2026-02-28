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
        <div className="th-time">LAST</div>
        <div className="th-time">BEST</div>
      </div>

      <div className="timing-table-body">
        {sorted.map(([num, data]) => (
          <DriverRow
            key={num}
            driverNum={num}
            driver={driverList[num]}
            timing={data}
            gapMode={gapMode}
          />
        ))}
      </div>
    </div>
  );
}
