"""Read explanation prose from string, summary and chain narratives."""


def narrative_text(value):
    """Prose leaves of a narrative; confidence and relationship data are not quotations."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(narrative_text(v) for k, v in value.items()
                         if k not in ("confidenceScore", "chainRelationGroups"))
    if isinstance(value, list):
        return "\n".join(narrative_text(v) for v in value)
    return ""
