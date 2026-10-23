"""Export a deterministic OpenAPI 3.x artifact directly from the executable API."""
import json
from pathlib import Path

from tapi_gate0.api import create_app

ROOT = Path(__file__).resolve().parents[1]
app = create_app(local_domain=True, dev_key="schema-export-only-key-with-32-chars")
spec = app.openapi()
destination = ROOT / "contracts" / "openapi.local.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(spec, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
print(f"Exported {len(spec['paths'])} routes to {destination.relative_to(ROOT)}")
