"""Reusable Epitran and CC-CEDICT pronunciation conversion."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CEDICT_PATH = _PROJECT_ROOT / "data" / "cedict_1_0_ts_utf-8_mdbg.txt"
_EPITRAN_PATH = _PROJECT_ROOT / "epitran"


class PhoneticConverter:
    """Convert text with Epitran and a CC-CEDICT pronunciation dictionary."""

    VALID_FORMATS = ("cedict", "notone", "tonemark", "ipa", "ipa-tones")

    def __init__(
        self,
        language: str = "cmn-Hans",
        fmt: str = "cedict",
        cedict_path: Optional[Union[str, os.PathLike]] = None,
    ):
        if fmt not in self.VALID_FORMATS:
            raise ValueError(
                f"Unsupported phonetic format: {fmt}. "
                f"Choose one of: {', '.join(self.VALID_FORMATS)}"
            )
        self.language = language
        self.fmt = fmt
        self.cedict_path = Path(cedict_path).expanduser() if cedict_path else None
        self._epi: Optional[Any] = None
        self._loaded_cedict_path: Optional[Path] = None

    def load_cc_cedict(
        self, path: Optional[Union[str, os.PathLike]] = None
    ) -> Path:
        """Load CC-CEDICT from ``path`` and initialize Epitran.

        When ``path`` is omitted, an explicitly configured constructor path is
        used, followed by the bundled dictionary under ``data``.
        """
        dictionary_path = Path(path).expanduser() if path else self.cedict_path
        if dictionary_path is None:
            dictionary_path = _DEFAULT_CEDICT_PATH
        dictionary_path = dictionary_path.resolve()

        if not dictionary_path.is_file():
            raise FileNotFoundError(
                f"CC-CEDICT dictionary not found: {dictionary_path}"
            )

        if _EPITRAN_PATH.is_dir():
            epitran_path = str(_EPITRAN_PATH)
            if epitran_path not in sys.path:
                sys.path.insert(0, epitran_path)

        import epitran

        epi_kwargs = {"cedict_file": str(dictionary_path)}
        if self.fmt == "ipa-tones":
            epi_kwargs["tones"] = True

        logger.info(
            f"Initializing epitran: language={self.language}, "
            f"format={self.fmt}, cedict={dictionary_path}"
        )
        self._epi = epitran.Epitran(
            self.language,
            ligatures=False,
            **epi_kwargs,
        )
        self._loaded_cedict_path = dictionary_path
        logger.success("Epitran initialized.")
        return dictionary_path

    @property
    def is_loaded(self) -> bool:
        """Whether Epitran and the CC-CEDICT-backed converter are ready."""
        return self._epi is not None

    @property
    def loaded_cedict_path(self) -> Optional[Path]:
        """Return the dictionary path used by the current Epitran instance."""
        return self._loaded_cedict_path

    def convert(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Convert ``text`` and return pronunciation plus token details."""
        if self._epi is None:
            raise RuntimeError(
                "PhoneticConverter is not initialized. "
                "Call load_cc_cedict() first."
            )

        if self.fmt in ("ipa", "ipa-tones"):
            transliterate = getattr(self._epi, "transliterate", None)
            if transliterate is None:
                transliterate = self._epi.epi.transliterate
            pronunciation = transliterate(text)
            return pronunciation, [
                {
                    "token": text,
                    "phonetic": pronunciation,
                    "formatted": pronunciation,
                    "source": "epitran-ipa",
                    "cedict_match": None,
                }
            ]

        cedict = self._epi.epi.cedict
        tokens = cedict.tokenize(text)
        pronunciation_parts = []
        token_details: List[Dict[str, Any]] = []

        for token in tokens:
            if token in cedict.hanzi:
                pinyin, english = cedict.hanzi[token]
                pinyin_string = " ".join(pinyin)
                formatted = self._format_pinyin(pinyin_string)
                pronunciation_parts.append(formatted)
                token_details.append(
                    {
                        "token": token,
                        "cedict_raw": pinyin_string,
                        "formatted": formatted,
                        "english": " / ".join(english[:3]),
                        "source": "cedict",
                        "cedict_match": True,
                    }
                )
            else:
                pronunciation_parts.append(token)
                token_details.append(
                    {
                        "token": token,
                        "cedict_raw": None,
                        "formatted": None,
                        "english": None,
                        "source": "passthrough",
                        "cedict_match": False,
                    }
                )

        return " ".join(pronunciation_parts), token_details

    def _format_pinyin(self, pinyin: str) -> str:
        if self.fmt == "cedict":
            return pinyin
        if self.fmt == "notone":
            return re.sub(r"[1-5]", "", pinyin)
        if self.fmt == "tonemark":
            return " ".join(
                self._pinyin_add_tonemarks(syllable)
                for syllable in pinyin.split()
            )
        return pinyin

    @staticmethod
    def _pinyin_add_tonemarks(syllable: str) -> str:
        match = re.match(r"^([a-z]+?)([1-5])$", syllable)
        if not match:
            return syllable

        base, tone = match.group(1), int(match.group(2))
        if tone in (0, 5):
            return base

        tone_map = {
            "a": "āáǎàa",
            "e": "ēéěèe",
            "i": "īíǐìi",
            "o": "ōóǒòo",
            "u": "ūúǔùu",
            "ü": "ǖǘǚǜü",
        }
        target = -1
        for index, character in enumerate(base):
            if character in ("a", "e"):
                target = index
                break
        if target == -1 and "ou" in base:
            target = base.index("o")
        if target == -1:
            for index in range(len(base) - 1, -1, -1):
                if base[index] in tone_map:
                    target = index
                    break
        if target == -1:
            return base

        character = base[target]
        replacement = tone_map[character][tone - 1]
        if "ü" in base and character == "u":
            replacement = tone_map["ü"][tone - 1]
        return base[:target] + replacement + base[target + 1 :]
