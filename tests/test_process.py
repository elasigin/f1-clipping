import numpy as np

from pipeline import process


def test_glitch_is_masked_and_normal_driving_is_not():
    v = np.r_[np.linspace(300, 300, 100), np.linspace(300, 100, 30), np.linspace(100, 300, 120)]
    assert not process.glitches(v).any()            # 150 m of hard braking, then acceleration
    v[50:55] = 180                                  # dropout and jump back
    bad = process.glitches(v)
    assert bad[49:56].all() and not bad[:40].any() and not bad[70:].any()
