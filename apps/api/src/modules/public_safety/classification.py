from __future__ import annotations

import unicodedata

_PUBLIC_SAFETY_TRANSLATE_SOURCE = "ÁÀÃÂÄáàãâäÉÈÊËéèêëÍÌÎÏíìîïÓÒÕÔÖóòõôöÚÙÛÜúùûüÇç"
_PUBLIC_SAFETY_TRANSLATE_TARGET = "AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCc"


def normalize_public_safety_category(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.upper()


def classify_public_safety_group(category: str | None) -> tuple[str, str]:
    normalized = normalize_public_safety_category(category)

    if any(keyword in normalized for keyword in ("ESTUPRO", "ASSEDIO SEX", "IMPORTUNACAO SEX", "VIOLACAO SEX")):
        return "sexual", "Violência sexual"
    if any(keyword in normalized for keyword in ("TRAFIC", "ENTORPEC", "DROGA")):
        return "drugs", "Drogas"
    if any(keyword in normalized for keyword in ("LATROC", "ROUBO", "EXTORSA")):
        return "robbery", "Roubo"
    if any(keyword in normalized for keyword in ("FURTO", "RECEPTAC")):
        return "theft", "Furto"
    if any(
        keyword in normalized
        for keyword in ("HOMIC", "LESAO", "AGRESS", "AMEACA", "SEQUESTRO", "VIOLENCIA DOMESTICA", "TORTURA", "MAUS TRATOS")
    ):
        return "violence", "Violência"
    return "other", "Outros"


def _normalized_public_safety_category_sql(column_name: str) -> str:
    return (
        "UPPER(TRANSLATE(COALESCE({column_name}, ''), '{source}', '{target}'))"
    ).format(
        column_name=column_name,
        source=_PUBLIC_SAFETY_TRANSLATE_SOURCE,
        target=_PUBLIC_SAFETY_TRANSLATE_TARGET,
    )


def public_safety_group_case_sql(column_name: str) -> str:
    normalized_sql = _normalized_public_safety_category_sql(column_name)
    return """
CASE
    WHEN {normalized_sql} LIKE '%ESTUPRO%'
      OR {normalized_sql} LIKE '%ASSEDIO SEX%'
      OR {normalized_sql} LIKE '%IMPORTUNACAO SEX%'
      OR {normalized_sql} LIKE '%VIOLACAO SEX%'
    THEN 'sexual'
    WHEN {normalized_sql} LIKE '%TRAFIC%'
      OR {normalized_sql} LIKE '%ENTORPEC%'
      OR {normalized_sql} LIKE '%DROGA%'
    THEN 'drugs'
    WHEN {normalized_sql} LIKE '%LATROC%'
      OR {normalized_sql} LIKE '%ROUBO%'
      OR {normalized_sql} LIKE '%EXTORSA%'
    THEN 'robbery'
    WHEN {normalized_sql} LIKE '%FURTO%'
      OR {normalized_sql} LIKE '%RECEPTAC%'
    THEN 'theft'
    WHEN {normalized_sql} LIKE '%HOMIC%'
      OR {normalized_sql} LIKE '%LESAO%'
      OR {normalized_sql} LIKE '%AGRESS%'
      OR {normalized_sql} LIKE '%AMEACA%'
      OR {normalized_sql} LIKE '%SEQUESTRO%'
      OR {normalized_sql} LIKE '%VIOLENCIA DOMESTICA%'
      OR {normalized_sql} LIKE '%TORTURA%'
      OR {normalized_sql} LIKE '%MAUS TRATOS%'
    THEN 'violence'
    ELSE 'other'
END
""".format(normalized_sql=normalized_sql)


def public_safety_group_label_case_sql(column_name: str) -> str:
    normalized_sql = _normalized_public_safety_category_sql(column_name)
    return """
CASE
    WHEN {normalized_sql} LIKE '%ESTUPRO%'
      OR {normalized_sql} LIKE '%ASSEDIO SEX%'
      OR {normalized_sql} LIKE '%IMPORTUNACAO SEX%'
      OR {normalized_sql} LIKE '%VIOLACAO SEX%'
    THEN 'Violencia sexual'
    WHEN {normalized_sql} LIKE '%TRAFIC%'
      OR {normalized_sql} LIKE '%ENTORPEC%'
      OR {normalized_sql} LIKE '%DROGA%'
    THEN 'Drogas'
    WHEN {normalized_sql} LIKE '%LATROC%'
      OR {normalized_sql} LIKE '%ROUBO%'
      OR {normalized_sql} LIKE '%EXTORSA%'
    THEN 'Roubo'
    WHEN {normalized_sql} LIKE '%FURTO%'
      OR {normalized_sql} LIKE '%RECEPTAC%'
    THEN 'Furto'
    WHEN {normalized_sql} LIKE '%HOMIC%'
      OR {normalized_sql} LIKE '%LESAO%'
      OR {normalized_sql} LIKE '%AGRESS%'
      OR {normalized_sql} LIKE '%AMEACA%'
      OR {normalized_sql} LIKE '%SEQUESTRO%'
      OR {normalized_sql} LIKE '%VIOLENCIA DOMESTICA%'
      OR {normalized_sql} LIKE '%TORTURA%'
      OR {normalized_sql} LIKE '%MAUS TRATOS%'
    THEN 'Violencia'
    ELSE 'Outros'
END
""".format(normalized_sql=normalized_sql)


__all__ = [
    "classify_public_safety_group",
    "normalize_public_safety_category",
    "public_safety_group_case_sql",
    "public_safety_group_label_case_sql",
]