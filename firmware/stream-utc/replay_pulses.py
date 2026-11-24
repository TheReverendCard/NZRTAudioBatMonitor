"""Compare both Stream trigger rules on one or more WAVs with the Trial 01 host scorer."""
import argparse
import hashlib
import sys
from collections import deque
from pathlib import Path

MODEL_SHA = "f9f857b24d21666831e3d5eaa145904003fc2cb0a93a64e59d0f68f4eb69588e"
OUTPUT_SCALE = 0.00080443843035027385
SCORE_FLOOR = 702
RELEASE_FRAMES = 8
WINDOW_FRAMES = 187


def summarise(frames):
    quiet = RELEASE_FRAMES
    onsets = deque(maxlen=3)
    peak = strong_time = train_time = None
    pulse_times = []
    for frame, (end, logit, _) in enumerate(frames):
        score = round(logit / OUTPUT_SCALE)
        peak = score if peak is None else max(peak, score)
        if score >= 1404 and strong_time is None:
            strong_time = end
        if score < SCORE_FLOOR:
            quiet = min(quiet + 1, RELEASE_FRAMES)
            continue
        if quiet == RELEASE_FRAMES:
            onsets.append(frame)
            pulse_times.append(end)
            if len(onsets) == 3 and frame - onsets[0] <= WINDOW_FRAMES and train_time is None:
                train_time = end
        quiet = 0
    return peak, strong_time, train_time, pulse_times


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", required=True, type=Path,
                        help="extracted Xiao_Stream_Recogniser_Trial_01 folder")
    parser.add_argument("wavs", nargs="+", type=Path)
    args = parser.parse_args()
    model = args.trial / "output" / "frame_model.npz"
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA:
        parser.error("Expected the original Trial 01 frame_model.npz in the trial's output folder.")
    sys.path.insert(0, str(args.trial.resolve()))
    from score_wav import stream_scores

    for wav in args.wavs:
        peak, strong, train, pulses = summarise(stream_scores(wav, model))
        print(wav)
        print("  Peak integer score:", peak)
        print("  First frame at 1404 (seconds):", "none" if strong is None else f"{strong:.4f}")
        print("  First three-pulse qualification (seconds):", "none" if train is None else f"{train:.4f}")
        print("  Distinct score onsets at 702 (seconds):",
              ", ".join(f"{t:.4f}" for t in pulses) or "none")


if __name__ == "__main__":
    main()
