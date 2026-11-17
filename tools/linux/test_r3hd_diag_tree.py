"""Tests for the LM-2 diagnostic-tree tool (pure functions; nothing is generated)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_diag_tree as T  # noqa: E402

MANIFEST = ('[project]\nname = "r3hd"\n[entrypoint]\nfile_path = "../../extracted/5841123F/Default.xex"\n'
            'includes = ["../../../config/rexglue/r3hd_functions.toml"]\ngenerate_exception_handlers = true\n')


def report(untranslated=(), unclassified=(), registered=(), entries=46207, words=1874097):
    return {"dispatch_table_entries": entries, "translated_words": words,
            "data_pointers": {"untranslated": list(untranslated), "distinct_targets": 6504,
                              "by_class": {"function_entry": 5507, "inside_translated_function": 960,
                                           "seh_except_body": 37}},
            "unclassified_synthesised": list(unclassified),
            "exception_representation": {"seh_bodies_registered_as_functions": list(registered),
                                         "seh_bodies_untranslated": []}}


class ManifestTests(unittest.TestCase):
    def test_exactly_one_line_changes(self):
        out = T.diag_manifest_text(MANIFEST)
        diff = [(a, b) for a, b in zip(MANIFEST.split("\n"), out.split("\n")) if a != b]
        self.assertEqual(diff, [(T.FLAG_ON, T.FLAG_OFF)])

    def test_refuses_a_manifest_without_or_with_two_flags(self):
        for text in (MANIFEST.replace(T.FLAG_ON, T.FLAG_OFF), MANIFEST + T.FLAG_ON + "\n", MANIFEST.replace(T.FLAG_ON, "")):
            with self.assertRaises(T.Fail):
                T.diag_manifest_text(text)


class AuditTests(unittest.TestCase):
    def test_audit_lists_count_as_zero_when_empty(self):
        # LM-2 regression: m3_target_audit writes `untranslated: []`; the gate compared it with the integer 0.
        s = T.audit_summary(report())
        self.assertEqual((s["untranslated_data_targets"], s["unclassified_synthesised"],
                          s["seh_bodies_registered_as_functions"]), (0, 0, 0))
        T.check_audit(s, T.audit_summary(report()))

    def test_each_zero_requirement_and_coverage_is_enforced(self):
        prod = T.audit_summary(report())
        for bad in (report(untranslated=["0x82000000"]), report(unclassified=[{"target": "0x1"}]),
                    report(registered=["0x82559D90"]), report(entries=46206), report(words=1)):
            with self.assertRaises(T.Fail):
                T.check_audit(T.audit_summary(bad), prod)


if __name__ == "__main__":
    unittest.main()
