import math

import numpy as np
from scipy import optimize


def moody(Re: float, r: float) -> float:
    """Caluclate Moody's coefficient"""
    if Re < 2300.0:
        return 64.0 / Re / 4.0

    def colebrook(x: float) -> float:
        # ``fsolve`` passes a size-1 array; extract a Python scalar so the
        # ``math`` calls work under NumPy >= 2 (which no longer auto-converts).
        xf = float(np.asarray(x).item())
        return -2 * math.log10(r / 3.72 + 2.51 / Re / xf**0.5) - 1 / xf**0.5

    return optimize.fsolve(colebrook, 0.02)[0] / 4.0
