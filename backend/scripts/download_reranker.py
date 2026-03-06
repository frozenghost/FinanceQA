"""One-time script to download and convert BGE-reranker-v2-m3 to ONNX.

This script requires `optimum` and `torch` (which are dev-dependencies).
After running once, the ONNX model is saved locally and only `onnxruntime`
+ `transformers` are needed at runtime.

Usage:
    uv run --with optimum --with torch python scripts/download_reranker.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

HF_MODEL_ID = "BAAI/bge-reranker-base"


def download_and_convert(output_dir: str | None = None):
    """Download the HuggingFace model and export to ONNX format."""
    model_dir = Path(output_dir or settings.RERANKER_MODEL_DIR)
    model_dir.mkdir(parents=True, exist_ok=True)

    if (model_dir / "model.onnx").exists():
        print(f"ONNX model already exists at {model_dir}/model.onnx")
        resp = input("Overwrite? [y/N] ").strip().lower()
        if resp != "y":
            print("Skipped.")
            return

    print(f"Downloading {HF_MODEL_ID} and exporting to ONNX...")
    print(f"Output directory: {model_dir}")

    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    # Export model to ONNX
    ort_model = ORTModelForSequenceClassification.from_pretrained(
        HF_MODEL_ID, export=True
    )
    ort_model.save_pretrained(str(model_dir))

    # Save tokenizer alongside
    tokenizer = AutoTokenizer.from_pretrained(HF_MODEL_ID)
    tokenizer.save_pretrained(str(model_dir))

    print(f"Done! ONNX model saved to {model_dir}")
    print(f"Model files: {[f.name for f in model_dir.iterdir()]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download and convert BGE-reranker-v2-m3 to ONNX"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=f"Output directory (default: {settings.RERANKER_MODEL_DIR})",
    )
    args = parser.parse_args()
    download_and_convert(args.output_dir)
