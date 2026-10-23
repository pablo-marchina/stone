"""Exibe relatório factual de prontidão, sem aprovar pendências."""
from tapi_gate0.readiness import status
import json
print(json.dumps(status(),indent=2,ensure_ascii=False))
