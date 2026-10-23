"""Export bearer-auth secure OpenAPI from executable FastAPI routes (no secrets)."""
from pathlib import Path
import json
from tapi_gate0.secure_api import create_secure_app
root=Path(__file__).resolve().parents[1]
app=create_secure_app("sqlite:///:memory:",initialize_schema=True,allow_http_local=True)
spec=app.openapi()
path=root/"contracts"/"openapi.secure.local.json"
path.write_text(json.dumps(spec,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
print(f"Exported {len(spec['paths'])} authenticated API routes")