import TopNav from "../components/TopNav";
import "../styles/About.css";

interface FeatureGroup {
  id: string;
  title: string;
  description: string;
  columns: { name: string; description: string }[];
}

const FEATURE_GROUPS: FeatureGroup[] = [
  {
    id: "categorical",
    title: "Identifiers",
    description:
      "Categorical features that let the model learn driver-, team-, and circuit-specific quirks.",
    columns: [
      { name: "driver", description: "Three-letter driver code (e.g. VER, HAM, PIA)." },
      { name: "team", description: "Constructor name normalised to a canonical alias (e.g. Red Bull Racing, Audi)." },
      { name: "gp_name", description: "Grand Prix name for the round being predicted." },
      { name: "race_name", description: "Race / event name as recorded in the source data." },
    ],
  },
  {
    id: "track",
    title: "Track Characteristics",
    description:
      "Circuit-level signals that encode how dramatic each track tends to be (overtaking, neutralisations, layout difficulty).",
    columns: [
      { name: "track_score", description: "Composite difficulty/quality score for the circuit." },
      { name: "track_overtakes", description: "Average overtakes per race at this circuit historically." },
      { name: "track_sc_pct", description: "Historical share of laps run under Safety Car." },
      { name: "track_vsc_pct", description: "Historical share of laps run under Virtual Safety Car." },
      { name: "track_red_pct", description: "Historical share of races interrupted by red flags." },
    ],
  },
  {
    id: "practice",
    title: "Practice Sessions",
    description:
      "Free practice signal — both finishing position and outright fastest-lap pace from FP1, FP2, and FP3.",
    columns: [
      { name: "fp1_pos", description: "Position at the end of FP1." },
      { name: "fp1_time", description: "Fastest FP1 lap (seconds)." },
      { name: "fp2_pos", description: "Position at the end of FP2." },
      { name: "fp2_time", description: "Fastest FP2 lap (seconds)." },
      { name: "fp3_pos", description: "Position at the end of FP3." },
      { name: "fp3_time", description: "Fastest FP3 lap (seconds)." },
    ],
  },
  {
    id: "qualifying",
    title: "Qualifying",
    description:
      "Qualifying pace and starting grid — typically the most predictive signal for race finishing position.",
    columns: [
      { name: "grid_pos", description: "Final qualifying / grid position (after penalties)." },
      { name: "q1_time", description: "Q1 lap time in seconds." },
      { name: "q2_time", description: "Q2 lap time in seconds." },
      { name: "q3_time", description: "Q3 lap time in seconds." },
      { name: "q1_pos", description: "Position at the end of Q1." },
      { name: "q2_pos", description: "Position at the end of Q2." },
      { name: "q3_pos", description: "Position at the end of Q3." },
    ],
  },
  {
    id: "pace",
    title: "Driver Pace Metrics",
    description:
      "Higher-order pace measures derived from the car / lap data pipeline — clean-air pace, deltas vs. the rest of the grid, and normalised 0-100 scores.",
    columns: [
      { name: "pace_avg", description: "Driver's average race-pace lap time." },
      { name: "pace_clean_air", description: "Average pace in clean air (no traffic / DRS train)." },
      { name: "pace_grid_avg", description: "Grid-wide average pace for context." },
      { name: "pace_delta_grid", description: "Driver's pace delta to the grid average." },
      { name: "pace_zscore", description: "Z-score of the driver's pace vs. the grid distribution." },
      { name: "pace_score_grid", description: "Pace score relative to the grid (signed)." },
      { name: "pace_score_100", description: "Pace score normalised to a 0-100 scale." },
    ],
  },
  {
    id: "speed",
    title: "Speed Metrics",
    description:
      "Top-end and corner-speed measurements that capture car setup and aero efficiency.",
    columns: [
      { name: "speed_top", description: "Driver's top straight-line speed." },
      { name: "speed_corner", description: "Driver's average minimum corner speed." },
      { name: "speed_top_rank", description: "Rank of top speed across the grid." },
      { name: "speed_corner_rank", description: "Rank of corner speed across the grid." },
      { name: "drag_index", description: "Estimated drag profile derived from speed traces." },
    ],
  },
  {
    id: "history-rolling",
    title: "Rolling History (computed at train time)",
    description:
      "Lag and rolling-average features built from each driver's prior races. Constructed with a one-race shift to avoid data leakage.",
    columns: [
      { name: "hist_finish_lag1", description: "Driver's finishing position in the previous race." },
      { name: "hist_finish_roll3", description: "Rolling 3-race average finishing position." },
      { name: "hist_finish_roll5", description: "Rolling 5-race average finishing position." },
      { name: "hist_grid_lag1", description: "Driver's grid position in the previous race." },
      { name: "hist_grid_roll3", description: "Rolling 3-race average grid position." },
      { name: "hist_grid_roll5", description: "Rolling 5-race average grid position." },
      { name: "hist_q3_roll3", description: "Rolling 3-race average Q3 lap time." },
      { name: "hist_q3_roll5", description: "Rolling 5-race average Q3 lap time." },
    ],
  },
  {
    id: "history-csv",
    title: "Historical Form (from data pipeline)",
    description:
      "Pre-computed historical aggregates supplied by the data pipeline.",
    columns: [
      { name: "hist_race_avg_3", description: "Average race finishing position over the last 3 events." },
      { name: "hist_race_avg_5", description: "Average race finishing position over the last 5 events." },
      { name: "hist_race_avg_7", description: "Average race finishing position over the last 7 events." },
      { name: "position_gain", description: "Average grid-to-finish positions gained per race." },
    ],
  },
];

const PIPELINE_STEPS = [
  {
    id: "ingest",
    title: "1. Ingest race weekend data",
    body:
      "The data pipeline pulls FastF1 sessions and writes structured rows into Supabase: per-driver entries for FP1-FP3, qualifying, the race itself, and the underlying car / lap telemetry.",
  },
  {
    id: "engineer",
    title: "2. Engineer features",
    body:
      "Lap-level telemetry is collapsed into pace, speed and tyre metrics. Rolling 3- / 5- / 7-race history is computed with a one-race lag so the model never sees the future.",
  },
  {
    id: "rank",
    title: "3. Train a LightGBM Ranker",
    body:
      "We use a LightGBM LambdaRank model: instead of predicting a finishing position directly, it learns to order all drivers within a race, optimised for NDCG.",
  },
  {
    id: "predict",
    title: "4. Predict the next race",
    body:
      "For the upcoming Grand Prix we feed in the latest qualifying / FP / pace data, score every driver, and rank them by score to produce a predicted classification 1-20.",
  },
  {
    id: "explain",
    title: "5. Explain the result",
    body:
      "The strongest features (typically grid position, pace delta, position gain, and rolling history) are surfaced together with a natural-language insight on the Predictions page.",
  },
];

export default function About() {
  return (
    <div className="about-page">
      <TopNav variant="solid" />

      <header className="about-hero">
        <div className="about-hero-inner">
          <span className="about-kicker">About F1-Zoom</span>
          <h1 className="about-title">How we predict the grid</h1>
          <p className="about-lede">
            F1-Zoom predicts each Grand Prix using a <strong>LightGBM Ranker</strong>
            {" "}trained on every recent race weekend. The model learns to order the
            drivers within a single race, rather than guessing a raw finishing
            position, which lines up cleanly with how Formula 1 results actually work.
          </p>
        </div>
      </header>

      <section className="about-section">
        <div className="about-section-inner">
          <h2 className="about-section-title">The model in five steps</h2>
          <div className="about-pipeline">
            {PIPELINE_STEPS.map((step) => (
              <article key={step.id} className="about-pipeline-card">
                <h3 className="about-pipeline-title">{step.title}</h3>
                <p className="about-pipeline-body">{step.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="about-section about-section-alt">
        <div className="about-section-inner">
          <h2 className="about-section-title">Model details</h2>
          <div className="about-model-grid">
            <div className="about-model-card">
              <span className="about-model-label">Algorithm</span>
              <span className="about-model-value">LightGBM Ranker</span>
              <span className="about-model-meta">objective: lambdarank · metric: NDCG</span>
            </div>
            <div className="about-model-card">
              <span className="about-model-label">Estimators</span>
              <span className="about-model-value">2,000</span>
              <span className="about-model-meta">learning rate 0.02 · 63 leaves</span>
            </div>
            <div className="about-model-card">
              <span className="about-model-label">Grouping</span>
              <span className="about-model-value">One group per race</span>
              <span className="about-model-meta">labels = race size + 1 - finish position</span>
            </div>
            <div className="about-model-card">
              <span className="about-model-label">Refresh</span>
              <span className="about-model-value">Every weekend</span>
              <span className="about-model-meta">re-trained from Supabase + FastF1</span>
            </div>
          </div>
        </div>
      </section>

      <section className="about-section">
        <div className="about-section-inner">
          <h2 className="about-section-title">The columns we feed in</h2>
          <p className="about-section-lede">
            Every feature the model consumes is listed below, grouped by where it
            comes from in the data pipeline. These are the exact column names used
            by <code>Data/Simulation/lightgbm_model.py</code>.
          </p>

          <div className="about-features">
            {FEATURE_GROUPS.map((group) => (
              <article key={group.id} className="about-feature-group">
                <header className="about-feature-header">
                  <h3 className="about-feature-title">{group.title}</h3>
                  <p className="about-feature-description">{group.description}</p>
                </header>
                <ul className="about-feature-list">
                  {group.columns.map((column) => (
                    <li key={column.name} className="about-feature-row">
                      <code className="about-feature-name">{column.name}</code>
                      <span className="about-feature-text">{column.description}</span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      <footer className="about-footer">
        <p>
          Built with React, Three.js, FastAPI and LightGBM.
          <span className="about-footer-divider">·</span>
          Data sourced from FastF1 and Supabase.
        </p>
      </footer>
    </div>
  );
}
