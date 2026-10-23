import os
import string
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from pos import i18n  # noqa: E402
from pos.locale_ar import ARABIC_UI  # noqa: E402


def placeholders(text):
    return sorted((name, spec) for _lit, name, spec, _conv in string.Formatter().parse(text) if name)


class ArabicCatalogTests(unittest.TestCase):
    def test_every_text_is_translated(self):
        import i18n_keys
        missing = {k: where for k, where in i18n_keys.literal_keys().items() if k not in ARABIC_UI}
        self.assertEqual(missing, {}, "untranslated texts")

    def test_stored_values_are_translated(self):
        try:
            import tkinter  # noqa: F401  (the screens are imported to read their value lists)
        except ImportError:
            self.skipTest("tkinter not available")
        import i18n_keys
        missing = [v for v in i18n_keys.value_keys() if v not in ARABIC_UI]
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        for english, arabic in ARABIC_UI.items():
            self.assertEqual(placeholders(english), placeholders(arabic), english)

    def test_translate_and_marks(self):
        i18n.set_language("ar")
        try:
            text = i18n._("Total: {amount}").format(amount="$5.00")
            self.assertTrue(text.startswith(i18n.RLE) and text.endswith(i18n.PDF))
            self.assertEqual(i18n.plain(text), "المجموع: $5.00")
            self.assertEqual(i18n._("not translated"), "not translated")
            self.assertEqual(i18n.tr_reason("Damaged: dropped it"), i18n._("Damaged") + ": dropped it")
            self.assertTrue(i18n.is_rtl())
        finally:
            i18n.set_language("en")
        self.assertEqual(i18n._("Total: {amount}"), "Total: {amount}")


if __name__ == "__main__":
    unittest.main()
