"""Deterministic, namespaced ids — shared with the RRC pilot's scheme (D-013).

    3gpp:<layer>/<type>/<name>     extracted entities  (e.g. 3gpp:ims/procedure/initial-registration)
    3gpp:concept/<x>               concept-scheme nodes
    3gpp:release/<Rel-N>           release reference nodes
"""
import re

# Map a spec to the ProtocolLayer concept its entities belong to (for IN_LAYER + ids).
LAYER_BY_SPEC = {
    "TS 38.331": "C_RRC",
    "TS 24.229": "C_IMS",
}

TYPE_SLUG = {
    "Procedure": "procedure", "Message": "message", "InformationElement": "ie",
    "Timer": "timer", "State": "state", "Event": "event", "Condition": "condition",
    "Bearer": "bearer", "UEVariable": "uevar", "Capability": "capability",
    # IMS
    "SIPMethod": "sip-method", "SIPResponse": "sip-response", "SIPHeader": "sip-header",
    "Identity": "identity", "NetworkElement": "netelem",
}


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-")


def release_of(version):
    """'19.6.0' -> 'Rel-19'  (3GPP major version == release number)."""
    try:
        return "Rel-%d" % int(str(version).split(".")[0])
    except Exception:
        return None


def canonical_id(typ, label, spec=None, concept_id=None):
    """Build the namespaced id for an entity of ``typ``/``label`` defined in ``spec``.

    Concept-scheme nodes pass ``concept_id`` (their ``C_*`` id) instead of a spec.
    """
    if typ in ("ProtocolLayer", "Stratum", "DomainRoot"):
        base = concept_id[2:] if concept_id and concept_id.startswith("C_") else slug(label)
        return "3gpp:concept/" + base.lower()
    if typ == "Release":
        return "3gpp:release/" + label
    concept = LAYER_BY_SPEC.get(spec)
    layer = concept[2:].lower() if concept else "x"
    return "3gpp:%s/%s/%s" % (layer, TYPE_SLUG.get(typ, typ.lower()), slug(label))
