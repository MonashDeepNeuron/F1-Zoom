"""
Pre-race Strategy Report module.

Sibling flow to the prediction/ranking pipeline. Reuses the existing Supabase
client (data_pipeline.db.supabase_client) and the existing FastAPI app; it does
not modify the prediction path.

Ensures the repository root is importable so `data_pipeline.*` resolves no matter
where the process is launched from (mirrors the sys.path bootstrap in
Data/Simulation/lightgbm_model.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
