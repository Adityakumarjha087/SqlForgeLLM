"""Single seeding utility used by every stage for reproducibility.

torch and numpy are optional imports: the dev environment on CPU installs
neither until the milestone that needs them, and seeding must not force them in.
"""

import os
import random

DEFAULT_SEED = 42


def set_seed(seed: int = DEFAULT_SEED) -> None:
    """Seed random, numpy and torch (the latter two only if installed)."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
