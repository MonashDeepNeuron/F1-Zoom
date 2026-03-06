export interface DriverInfo {
  RacingNumber: string;
  BroadcastName: string;
  FullName: string;
  Tla: string;
  TeamName: string;
  TeamColour: string;
  Line: number;
}

export interface Segment {
  Status: number;
}

export interface Sector {
  Value: string;
  PreviousValue?: string;
  Status: number;
  OverallFastest: boolean;
  PersonalFastest: boolean;
  Stopped: boolean;
  Segments: Segment[];
}

export interface LapTime {
  Value: string;
  OverallFastest?: boolean;
  PersonalFastest?: boolean;
  Lap?: number;
}

export interface IntervalData {
  Value: string;
  Catching: boolean;
}

export interface TimingDataDriver {
  Position: string;
  ShowPosition: boolean;
  GapToLeader: string;
  IntervalToPositionAhead?: IntervalData;
  Sectors: Sector[];
  BestLapTime: LapTime;
  LastLapTime: LapTime;
  NumberOfLaps: number;
  InPit: boolean;
  PitOut: boolean;
  Retired: boolean;
}

export interface BestTime {
  Value: string;
  Lap?: number;
}

export interface TimingStatsDriver {
  RacingNumber: string;
  PersonalBestLapTime: BestTime;
  BestSectors: BestTime[];
}

export type TyreCompound = "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET" | "";

export interface Stint {
  Compound: TyreCompound;
  New: string;
  TotalLaps: number;
  StartLaps: number;
}

export interface TimingAppDataDriver {
  Stints: Stint[];
}

export interface CarPosition {
  X: number;
  Y: number;
  Z: number;
  Status: string;
}

export interface SessionInfo {
  Meeting?: {
    Name: string;
    Circuit?: { ShortName: string };
  };
  Name: string;
  Type: string;
}

export type GapMode = "leader" | "interval";
