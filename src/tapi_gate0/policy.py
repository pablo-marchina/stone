"""Gate de autorização local, sem operações de rede. Negação por padrão.

Documentos de permissão NÃO são grants criptograficamente verificáveis.
Não incorporar lógica que converta status APPROVED de arquivo editável em direito operacional.
"""
from dataclasses import dataclass
from enum import Enum

class Operation(str, Enum):
    RETRIEVE_METADATA = "retrieve_metadata"
    PROCESS_MEDIA = "download_or_process_media"
    PERSIST_METADATA = "persist_metadata"
    CLASSIFY = "classify"
    AGGREGATE = "aggregate_cross_creator"
    PUBLISH = "publish"
    PAID_CAMPAIGN = "manage_paid_campaign"
    CRM = "read_crm"
    COMMENTS = "process_personal_comments"
    EVALUATE_SYNTHETIC = "evaluate_local_fixture"

@dataclass(frozen=True)
class Decision:
    permitted: bool
    code: str
    reason: str

EXTERNAL_SOURCES = frozenset({"instagram_metadata", "instagram_media", "youtube_metadata", "youtube_media", "stone_internal", "crm", "owned_publication", "ads_paid"})

def decide(source: str, operation: str) -> Decision:
    """Deny external integrations unconditionally until signed approval service is built.

    Synthetic fixtures are local only. Approval cannot be forged with an environment
    variable, edit of JSON or caller-supplied attribute.
    """
    if source == "synthetic_local" and operation == Operation.EVALUATE_SYNTHETIC.value:
        return Decision(True, "LOCAL_FIXTURE_ONLY", "Verificação interna sintética, sem coleta/publicação")
    if source in EXTERNAL_SOURCES:
        return Decision(False, "EXTERNAL_DENIED_PENDING_VERIFIED_GRANT", "Permissão externa e autoridade verificadas ainda inexistentes")
    return Decision(False, "OPERATION_NOT_ALLOWED", "Operação ou origem não autorizada")
