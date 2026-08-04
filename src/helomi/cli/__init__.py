"""Terminal frontend for Helomi."""

import os

# Helomi uses Transformers tokenizers through MLX without the PyTorch model runtime.
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
