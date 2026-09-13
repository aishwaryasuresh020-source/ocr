"""
ocr_engine.py

Step 2 — OCR engine.

Runs Tesseract on SROIE images and produces word-level OCR JSON files,
one per invoice, matching the schema that field_extractor.py expects:

    {
        "id": "<invoice_id>",
        "image_path": "<absolute path>",
        "words": [
            {
                "text": "...",
                "confidence": <float>,
                "bbox": {"x":, "y":, "width":, "height":},
                "block_num": <int>,
                "par_num":   <int>,
                "line_num":  <int>
            },
            ...
        ]
    }

Design notes:
- Deterministic: images processed in sorted order; JSON written with
  sorted keys off (preserving list order) and stable formatting.
- Idempotent: re-running overwrites existing output files.
- Split-agnostic: --split {train,test,both}
- Dataset root is a CLI argument, defaulting to the local SROIE2019 path.
- Failures are logged per-image and do not abort the run.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pytesseract
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_DATASET_ROOT = Path("/Users/aishwaryasuresh/Downloads/SROIE2019")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MIN_CONFIDENCE = -1.0    # keep everything; Tesseract uses -1 for non-text tokens


# ---------------------------------------------------------
# 1. PER-IMAGE OCR
# ---------------------------------------------------------

def run_ocr(image_path: Path) -> list[dict]:
    """
    Run Tesseract on one image and return a list of word dicts.

    Words with empty text after stripping are dropped.
    Confidence is kept as float (Tesseract uses -1 for non-text blocks).
    """
    image = Image.open(image_path)

    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )

    words = []
    n = len(data["text"])

    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0

        words.append({
            "text": text,
            "confidence": conf,
            "bbox": {
                "x":      int(data["left"][i]),
                "y":      int(data["top"][i]),
                "width":  int(data["width"][i]),
                "height": int(data["height"][i]),
            },
            "block_num": int(data["block_num"][i]),
            "par_num":   int(data["par_num"][i]),
            "line_num":  int(data["line_num"][i]),
        })

    return words


# ---------------------------------------------------------
# 2. PER-SPLIT PROCESSING
# ---------------------------------------------------------

def process_split(image_folder: Path, output_folder: Path) -> dict:
    """
    Run OCR on every image in `image_folder`, write one JSON per image
    to `output_folder`. Returns a small report dict.
    """
    if not image_folder.exists():
        raise FileNotFoundError(f"Image folder not found: {image_folder}")

    output_folder.mkdir(parents=True, exist_ok=True)

    image_files = sorted(
        p for p in image_folder.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
    )

    total = len(image_files)
    if total == 0:
        logger.warning("No images found in %s", image_folder)
        return {
            "split": image_folder.parent.name,
            "total": 0,
            "succeeded": 0,
            "failed": 0,
        }

    logger.info("Found %d images in %s", total, image_folder)

    succeeded = 0
    failed = 0

    for i, image_path in enumerate(image_files, start=1):
        logger.info("[%d/%d] OCR: %s", i, total, image_path.name)

        try:
            words = run_ocr(image_path)

            result = {
                "id": image_path.stem,
                "image_path": str(image_path.resolve()),
                "words": words,
            }

            out_file = output_folder / f"{image_path.stem}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            succeeded += 1

        except Exception as e:
            logger.error("Failed on %s: %s", image_path.name, e)
            failed += 1

    report = {
        "split": image_folder.parent.name,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "output_dir": str(output_folder),
    }
    return report


# ---------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Tesseract OCR on SROIE images.",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Path to SROIE2019 root (contains train/ and test/).",
    )
    parser.add_argument(
        "--split",
        choices=["train", "test", "both"],
        default="both",
        help="Which split(s) to process.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("ocr_results"),
        help="Root folder for OCR JSON output.",
    )
    args = parser.parse_args()

    dataset_root: Path = args.dataset_root
    if not dataset_root.exists():
        logger.error("Dataset root does not exist: %s", dataset_root)
        return 2

    splits = ["train", "test"] if args.split == "both" else [args.split]

    reports = []
    for split in splits:
        image_folder = dataset_root / split / "img"
        output_folder = args.output_root / split

        if not image_folder.exists():
            logger.error("Missing image folder: %s", image_folder)
            return 2

        logger.info("=" * 60)
        logger.info("Processing split: %s", split)
        logger.info("=" * 60)

        try:
            report = process_split(image_folder, output_folder)
            reports.append(report)
        except FileNotFoundError as e:
            logger.error(str(e))
            return 2

    # --- Summary ---
    print()
    print("=" * 60)
    print("OCR SUMMARY")
    print("=" * 60)
    for r in reports:
        print(f"\nSplit     : {r['split']}")
        print(f"Total     : {r['total']}")
        print(f"Succeeded : {r['succeeded']}")
        print(f"Failed    : {r['failed']}")
        if "output_dir" in r:
            print(f"Output    : {r['output_dir']}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())