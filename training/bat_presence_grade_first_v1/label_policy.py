"""Reference bat-presence grade policy for offline trainer v1.

Same normative grading logic as the owner-installable v1 training ZIP.
This module is committed for code review and handoff. The actual owner
TrainingWorkbench integration remains in the separately delivered ZIP;
this module is not by itself proof the user's machine has been patched.
"""

REVIEWED = {"reviewed_metadata", "reviewed_confirmed"}
LABEL_POLICY_VERSION = "bat_presence_grade_first_v1"
GRADE_WEIGHT = {"1": "1.0", "2": "0.7", "4": "0.8", "5": "1.0"}


def analysis_label(row: dict) -> tuple[str, str, str]:
    """Human grade first; positive class means any bat, not a species label.

    Ignore machine-generated short-tailed species predictions and legacy
    any_short_tailed_annotation exclusions. Explicit artificial playback
    remains excluded. Unreviewed and grade-3 are never hard negatives.
    """
    if row.get("review_provenance") not in REVIEWED:
        return "unreviewed", "unreviewed", "no_trusted_human_review"
    grade = str(row.get("confidence_grade") or "").strip()
    if grade not in ("1", "2", "3", "4", "5"):
        return "unreviewed", "unreviewed", "missing_numeric_human_grade"
    reason = (row.get("excluded_reason") or "").casefold()
    old = (row.get("training_label") or "").casefold()
    if ("artificial" in old or "playback" in old or
        "playback" in reason or "artificial" in reason):
        return "excluded", "excluded", "explicit_artificial_playback"
    if grade in ("1", "2"):
        return "negative", "graded", ""
    if grade == "3":
        return "uncertain", "graded", "possible_bat"
    return "positive", "graded", ""


def presence_label(row: dict, binary_class: str) -> str:
    """BMP and WAV share human grade class; WAV still needs paired media."""
    return binary_class


def reviewed_weight(row: dict) -> str:
    """Undo old zero weights derived from machine species exclusions."""
    return GRADE_WEIGHT.get(str(row.get("confidence_grade") or "").strip(), "")
