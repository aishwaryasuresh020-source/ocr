"""
Step 1 — SROIE2019 preprocessing.

Parses SROIE box/entities/img triples into structured records.
Does NOT modify original SROIE2019 train/, test/, or layoutlm-base-uncased/ contents.

The dataset root is a separate sibling directory from this project
(OCR_DECISION_SYSTEM/), so it is passed in explicitly rather than derived
from this script's location.
"""

import argparse
import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_ENTITY_KEYS = ("company", "date", "address", "total")

# Default dataset location — override with --dataset-root if it ever moves.
DEFAULT_DATASET_ROOT = Path("/Users/aishwaryasuresh/Downloads/SROIE2019")


@dataclass
class InvoiceRecord:
    id: str
    image_path: str
    words: list = field(default_factory=list)
    boxes: list = field(default_factory=list)  # each box: [x1,y1,x2,y2,x3,y3,x4,y4]
    ground_truth: dict = field(default_factory=dict)


def parse_box_file(box_path: Path) -> tuple[list[list[int]], list[str], int]:
    """
    Parse a SROIE box file.

    Each line: x1,y1,x2,y2,x3,y3,x4,y4,TEXT
    TEXT may itself contain commas, so we split at most 8 times —
    the 9th resulting piece is the full text, commas and all.

    Returns (boxes, words, malformed_line_count).
    """
    boxes: list[list[int]] = []
    words: list[str] = []
    malformed = 0

    with open(box_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue

            parts = line.split(",", 8)  # max 8 splits -> up to 9 parts
            if len(parts) < 9:
                malformed += 1
                logger.warning(
                    "Malformed box line %d in %s: %r", line_num, box_path.name, line
                )
                continue

            coord_strs, text = parts[:8], parts[8]

            try:
                coords = [int(c) for c in coord_strs]
            except ValueError:
                malformed += 1
                logger.warning(
                    "Non-integer coordinates on line %d in %s: %r",
                    line_num, box_path.name, line,
                )
                continue

            boxes.append(coords)
            words.append(text)

    return boxes, words, malformed


def parse_entities_file(entities_path: Path) -> Optional[dict]:
    """Parse a SROIE entities JSON file. Returns None if invalid/missing keys."""
    try:
        with open(entities_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not parse entities file %s: %s", entities_path, e)
        return None

    missing = [k for k in REQUIRED_ENTITY_KEYS if k not in data]
    if missing:
        logger.warning(
            "Entities file %s missing keys: %s", entities_path.name, missing
        )
    return data


def find_image_path(img_dir: Path, sample_id: str) -> Optional[Path]:
    """SROIE images are .jpg, but check a couple of extensions defensively."""
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = img_dir / f"{sample_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def process_split(split_dir: Path, output_dir: Path) -> dict:
    """
    Process one split (train or test) of SROIE.

    Returns a validation report dict.
    """
    box_dir = split_dir / "box"
    entities_dir = split_dir / "entities"
    img_dir = split_dir / "img"

    box_ids = {p.stem for p in box_dir.glob("*.txt")}
    entities_ids = {p.stem for p in entities_dir.glob("*.txt")}
    img_ids = {p.stem for p in img_dir.glob("*.*")}

    all_ids = box_ids | entities_ids | img_ids
    common_ids = box_ids & entities_ids & img_ids

    missing_images = sorted(all_ids - img_ids)
    missing_box = sorted(all_ids - box_ids)
    missing_entities = sorted(all_ids - entities_ids)

    output_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = 0
    total_malformed_lines = 0

    for sample_id in sorted(common_ids):
        image_path = find_image_path(img_dir, sample_id)
        if image_path is None:
            skipped += 1
            continue

        boxes, words, malformed = parse_box_file(box_dir / f"{sample_id}.txt")
        total_malformed_lines += malformed

        ground_truth = parse_entities_file(entities_dir / f"{sample_id}.txt")
        if ground_truth is None:
            skipped += 1
            continue

        record = InvoiceRecord(
            id=sample_id,
            image_path=str(image_path),
            words=words,
            boxes=boxes,
            ground_truth=ground_truth,
        )

        out_path = output_dir / f"{sample_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)

        processed += 1

    report = {
        "split": split_dir.name,
        "total_ids_seen": len(all_ids),
        "processed": processed,
        "skipped": skipped,
        "missing_images": len(missing_images),
        "missing_box_files": len(missing_box),
        "missing_entity_files": len(missing_entities),
        "malformed_box_lines": total_malformed_lines,
    }
    return report


def test_single_invoice(split_dir: Path, sample_id: str) -> None:
    """Step 1 smoke test: parse and print one invoice's structure."""
    box_dir = split_dir / "box"
    entities_dir = split_dir / "entities"
    img_dir = split_dir / "img"

    boxes, words, malformed = parse_box_file(box_dir / f"{sample_id}.txt")
    ground_truth = parse_entities_file(entities_dir / f"{sample_id}.txt")
    image_path = find_image_path(img_dir, sample_id)

    print("=" * 50)
    print(f"SINGLE INVOICE TEST — {sample_id}")
    print("=" * 50)
    print(f"Image path       : {image_path}")
    print(f"Number of words  : {len(words)}")
    print(f"Malformed lines  : {malformed}")
    print(f"First 5 words    : {words[:5]}")
    print(f"First 5 boxes    : {boxes[:5]}")
    print("--- Ground truth ---")
    if ground_truth:
        print(f"Company : {ground_truth.get('company')}")
        print(f"Date    : {ground_truth.get('date')}")
        print(f"Address : {ground_truth.get('address')}")
        print(f"Total   : {ground_truth.get('total')}")
    else:
        print("Ground truth: FAILED TO PARSE")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="SROIE2019 Step 1 preprocessing")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Path to the SROIE2019 dataset folder (contains train/, test/).",
    )
    args = parser.parse_args()

    dataset_root: Path = args.dataset_root
    # This script's own location determines where OUTPUTS go — that part
    # of the original logic was correct and is unchanged.
    project_root = Path(__file__).resolve().parent.parent

    train_dir = dataset_root / "train"
    test_dir = dataset_root / "test"

    if not train_dir.exists() or not test_dir.exists():
        raise FileNotFoundError(
            f"Could not find train/ and test/ under dataset root: {dataset_root}\n"
            f"Pass the correct path with --dataset-root, e.g.:\n"
            f"  python3 src/preprocessing.py --dataset-root /path/to/SROIE2019"
        )

    # --- Step 1 smoke test on one invoice ---
    first_id = sorted((train_dir / "img").glob("*.*"))[0].stem
    test_single_invoice(train_dir, first_id)

    # --- Full processing ---
    reports = []
    reports.append(process_split(train_dir, project_root / "processed" / "train"))
    reports.append(process_split(test_dir, project_root / "processed" / "test"))

    print("\n" + "=" * 50)
    print("VALIDATION REPORT")
    print("=" * 50)
    for r in reports:
        print(f"\nSplit: {r['split']}")
        for k, v in r.items():
            if k == "split":
                continue
            print(f"  {k}: {v}")
    print("=" * 50)


if __name__ == "__main__":
    main()