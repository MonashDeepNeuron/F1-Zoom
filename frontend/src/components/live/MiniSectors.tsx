import type { Sector, BestTime } from "../../types/liveTiming";

interface Props {
  sector?: Sector;
  bestSector?: BestTime;
}

const STATUS_COLORS: Record<number, string> = {
  0: "#2a2a2a",
  2048: "#eab308",
  2049: "#22c55e",
  2051: "#a855f7",
  2052: "#eab308",
  2064: "#3b82f6",
};

function sectorTimeClass(sector?: Sector): string {
  if (!sector?.Value) return "";
  if (sector.OverallFastest) return "purple";
  if (sector.PersonalFastest) return "green";
  return "yellow";
}

export default function MiniSectors({ sector, bestSector }: Props) {
  const segments = sector?.Segments ?? [];
  const cls = sectorTimeClass(sector);

  return (
    <div className="mini-sectors">
      <div className="segments-row">
        {segments.map((seg, i) => (
          <span
            key={i}
            className="segment-dot"
            style={{
              backgroundColor: STATUS_COLORS[seg.Status] ?? STATUS_COLORS[0],
            }}
          />
        ))}
      </div>
      <div className={`sector-time ${cls}`}>
        {sector?.Value || sector?.PreviousValue || ""}
      </div>
      {bestSector?.Value && (
        <div className="best-sector-time">{bestSector.Value}</div>
      )}
    </div>
  );
}
