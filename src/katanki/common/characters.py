"""Exact character identity shared by discovery and target classifications."""

import unicodedata


def is_kanji(character: str) -> bool:
    return (
        isinstance(character, str)
        and len(character) == 1
        and (
            character == "〇"
            or unicodedata.name(character, "").startswith(
                ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-")
            )
        )
    )
