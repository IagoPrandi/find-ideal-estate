from __future__ import annotations

import re
import unicodedata
from typing import Any


_TRANSLATE_SOURCE = "ÁÀÃÂÄáàãâäÉÈÊËéèêëÍÌÎÏíìîïÓÒÕÔÖóòõôöÚÙÛÜúùûüÇç"
_TRANSLATE_TARGET = "AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCc"


def normalize_location_display_name(value: Any) -> str | None:
	if value is None:
		return None

	text = str(value).strip()
	if not text:
		return None

	normalized = unicodedata.normalize("NFKD", text)
	without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
	sanitized = re.sub(r"[^0-9A-Za-z]+", " ", without_accents)
	collapsed = re.sub(r"\s+", " ", sanitized).strip()
	if not collapsed:
		return None

	return collapsed.upper()


def normalized_location_name_sql(column_name: str) -> str:
	return (
		"NULLIF(BTRIM("
		"regexp_replace("
		"regexp_replace("
		"UPPER(TRANSLATE(COALESCE({column_name}, ''), '{source}', '{target}'))"
		", '[^0-9A-Z]+', ' ', 'g'"
		")"
		", '\\s+', ' ', 'g'"
		")"
		"), '')"
	).format(
		column_name=column_name,
		source=_TRANSLATE_SOURCE,
		target=_TRANSLATE_TARGET,
	)
