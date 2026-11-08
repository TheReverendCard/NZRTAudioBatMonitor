"""Standalone regression tests for the Git-tracked grade-first policy reference.

Run from repository root:
    python -m unittest discover -s training/bat_presence_grade_first_v1 -p 'test_*.py'
The ZIP's end-to-end trainer tests are separate and additionally required.
"""
import unittest
from label_policy import analysis_label, presence_label, reviewed_weight, LABEL_POLICY_VERSION


def sample(grade, provenance="reviewed_metadata", reason="any_short_tailed_annotation"):
    return {
        "review_provenance": provenance,
        "confidence_grade": grade,
        "excluded_reason": reason,
        "training_label": "excluded_short_tailed_or_mixed",
        "species_annotations": "Long-tailed bat | Short-tailed bat",
        "machine_species_annotations": "Short-tailed bat",
        "suggested_weight": "0.0",
    }


class TestPresencePolicy(unittest.TestCase):
    def test_human_positive_overrides_machine_species(self):
        for g in ("4", "5"):
            r = sample(g)
            self.assertEqual(analysis_label(r)[0], "positive")
            self.assertEqual(presence_label(r, analysis_label(r)[0]), "positive")

    def test_human_negative_overrides_machine_species(self):
        for g in ("1", "2"):
            self.assertEqual(analysis_label(sample(g))[0], "negative")

    def test_uncertain_is_neither_bat_nor_no_bat(self):
        self.assertEqual(analysis_label(sample("3"))[0], "uncertain")

    def test_no_human_grade_or_machine_only_not_training(self):
        self.assertEqual(analysis_label(sample(""))[0], "unreviewed")
        self.assertEqual(analysis_label(sample("5", provenance="machine_only"))[0], "unreviewed")

    def test_known_playback_excluded(self):
        self.assertEqual(analysis_label(sample("5",reason="known_playback"))[0], "excluded")

    def test_zero_legacy_weight_not_reused(self):
        self.assertEqual(reviewed_weight(sample("5")), "1.0")
        self.assertEqual(reviewed_weight(sample("4")), "0.8")
        self.assertEqual(reviewed_weight(sample("2")), "0.7")
        self.assertEqual(LABEL_POLICY_VERSION, "bat_presence_grade_first_v1")


if __name__=="__main__":
    unittest.main()
