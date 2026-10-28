"""
roascan.accent: Accent restoration for Spanish/Latin OCR output.

OCR models frequently drop diacritics (accents, tildes). This module restores
them using a Hunspell lexicon with affix expansion (/G feminine, /S plural) and
process-wide dictionary caching: an unaccented word that is NOT itself a valid
dictionary word but has a unique accented dictionary form is mapped back to that
form (e.g. "REPUBLICA" -> "REPÚBLICA", "ELECTRONICA" -> "ELECTRÓNICA").
"""

import os
from typing import Dict, Optional, Set, Tuple

# Spanish accented characters -> unaccented equivalents.
_STRIP_TABLE = str.maketrans(
    "áéíóúüñÁÉÍÓÚÜÑ",
    "aeiouunAEIOUUN",
)


class AccentRestorer:
    """Restores Spanish accents on OCR words using a cached Hunspell dictionary."""

    # Process-wide cache: path -> (valid_words, stripped_to_accented)
    _DICT_CACHE: Dict[str, Tuple[Set[str], Dict[str, Set[str]]]] = {}

    def __init__(self, dict_path: Optional[str] = None):
        if dict_path is None:
            pkg_dir = os.path.dirname(os.path.abspath(__file__))
            base = os.path.dirname(pkg_dir)
            cand_pkg = os.path.join(pkg_dir, "models", "es_ES.dic")
            dict_path = cand_pkg if os.path.exists(cand_pkg) else os.path.join(base, "models", "es_ES.dic")

        abs_path = os.path.abspath(dict_path)
        if abs_path in self._DICT_CACHE:
            self.valid_words, self.stripped_to_accented = self._DICT_CACHE[abs_path]
        elif os.path.exists(abs_path):
            self.valid_words = set()
            self.stripped_to_accented = {}
            self._load(abs_path)
            self._DICT_CACHE[abs_path] = (self.valid_words, self.stripped_to_accented)
        else:
            self.valid_words = set()
            self.stripped_to_accented = {}

    def _register_word(self, w: str):
        if not w or not w.isalpha():
            return
        self.valid_words.add(w)
        stripped = self.strip_accents(w)
        if stripped != w:
            self.stripped_to_accented.setdefault(stripped, set()).add(w)

    def _load(self, path: str):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split("/")
                word = parts[0].strip().lower()
                if not word or not word.isalpha():
                    continue
                flags = parts[1] if len(parts) > 1 else ""

                self._register_word(word)

                # Expand standard Spanish Hunspell affix flags:
                # 'G' = gender inflection (-o -> -a)
                # 'S' = plural inflection (-s / -es)
                has_g = "G" in flags
                has_s = "S" in flags

                if has_g and word.endswith("o"):
                    fem = word[:-1] + "a"
                    self._register_word(fem)
                    if has_s:
                        self._register_word(fem + "s")

                if has_s:
                    if word.endswith(("a", "e", "i", "o", "u", "á", "é", "ó")):
                        self._register_word(word + "s")
                    elif word.endswith(("ión", "ion")):
                        pass  # plural loses accent (e.g. facturaciones)
                    else:
                        self._register_word(word + "es")

    @staticmethod
    def strip_accents(s: str) -> str:
        """Map Spanish accented characters to their unaccented form."""
        return s.translate(_STRIP_TABLE)

    @property
    def is_available(self) -> bool:
        return bool(self.valid_words)

    def restore(self, text: str) -> str:
        """Restore accents across a whole string (word by word)."""
        if not text:
            return ""
        return " ".join(self.restore_word(w) for w in text.split())

    def restore_word(self, word: str) -> str:
        """Restore the accent of a single token, preserving surrounding punctuation and casing."""
        if not word:
            return word

        # Separate leading and trailing non-alphabetic punctuation (e.g. "FACTURACION:")
        start = 0
        end = len(word)
        while start < end and not word[start].isalpha():
            start += 1
        while end > start and not word[end - 1].isalpha():
            end -= 1

        if start >= end:
            return word

        prefix = word[:start]
        core = word[start:end]
        suffix = word[end:]

        if not core.isalpha():
            return word

        lower = core.lower()
        stripped = self.strip_accents(lower)

        # If the unaccented form is itself a valid word (e.g. "como", "esta"),
        # leave it alone to avoid wrong disambiguation.
        if stripped in self.valid_words:
            return word

        candidates = self.stripped_to_accented.get(stripped, set())
        if len(candidates) == 1:
            accented = next(iter(candidates))
            return prefix + self._apply_case(core, accented) + suffix
        return word

    @staticmethod
    def _apply_case(original: str, accented_lower: str) -> str:
        if original.isupper():
            return accented_lower.upper()
        if original[0].isupper() and (len(original) == 1 or original[1:].islower()):
            return accented_lower.capitalize()
        return accented_lower
