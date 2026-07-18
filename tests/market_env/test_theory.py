"""Numerical verification of the manuscript's theorems (continuum, scipy)."""
import numpy as np
import pytest
from scipy.optimize import brentq, minimize_scalar


def share(p, rivals_w, a, w0=0.0):
    return p ** -a / (p ** -a + rivals_w + w0)


def br(rivals_w, a, c, cap, w0=0.0):
    r = minimize_scalar(lambda p: -share(p, rivals_w, a, w0) * (p - c),
                        bounds=(c * 1.0001, cap), method="bounded")
    return r.x


def sym_eq(n, a, c, cap, w0=0.0):
    p = c * 2
    for _ in range(500):
        p_new = br((n - 1) * p ** -a, a, c, cap, w0)
        if abs(p_new - p) < 1e-10:
            break
        p = p_new
    return p


C = 0.2


@pytest.mark.parametrize("n,a", [(3, 2), (4, 2), (10, 2), (3, 4), (2, 4), (5, 3)])
def test_theorem1_interior_formula(n, a):
    pred = C * a * (n - 1) / (a * (n - 1) - n)
    assert sym_eq(n, a, C, cap=100.0) == pytest.approx(pred, abs=1e-3)


@pytest.mark.parametrize("n,a", [(2, 2), (3, 1.5), (2, 1)])
def test_theorem1_knife_edge_hits_cap(n, a):
    assert sym_eq(n, a, C, cap=100.0) == pytest.approx(100.0, rel=1e-3)


def test_theorem1_lerner_floor_tight():
    for a in (2, 3, 4):
        floor = C * a / (a - 1)
        assert sym_eq(200, a, C, cap=100.0) == pytest.approx(floor, rel=2e-2)
        assert sym_eq(3, a, C, cap=100.0, w0=1e6) == pytest.approx(floor, rel=1e-3)


def test_corollary1_epsilon_formula():
    def sym_eq_eps(n, a, eps, cap=1e6):
        def profit(p_i, q):
            w = p_i ** -a
            W = (n - 1) * q ** -a
            return ((w + W) ** (-1 / a)) ** eps * w / (w + W) * (p_i - C)
        p = 2 * C
        for _ in range(800):
            r = minimize_scalar(
                lambda x, rival=p: -profit(x, rival),
                bounds=(C * 1.0001, cap),
                method="bounded",
            )
            if abs(r.x - p) < 1e-9:
                break
            p = r.x
        return p

    for (n, a, eps) in [(2, 2, -0.05), (3, 2, -0.05), (2, 2, -0.2), (2, 2, -1.0)]:
        R = a * (n - 1) / n + abs(eps) / n
        assert sym_eq_eps(n, a, eps) == pytest.approx(C * R / (R - 1), rel=1e-3)


def test_theorem2_deviation_closed_form():
    a, n, pbar, th = 2.0, 5, 1.0, 0.4
    W = (n - 1) * pbar ** -a
    r = minimize_scalar(
        lambda p: -(th * p ** -a / (th * p ** -a + W)) * (p - C),
        bounds=(C * 1.0001, pbar), method="bounded")
    assert r.x == pytest.approx(C + np.sqrt(C ** 2 + th / W), abs=1e-4)


def test_theorem2_patience_boundary():
    a, n, q, th, M = 2.0, 5, 1.0, 0.17, 7
    W = (n - 1) * q ** -a

    def max_gain(delta):
        def gain(p):
            s_th = th * p ** -a / (th * p ** -a + W)
            s_cl = p ** -a / (p ** -a + W)
            stay = (1 / n) * (q - C)
            return ((1 - delta ** M) / (1 - delta) * (s_th * (p - C) - stay)
                    + delta ** M / (1 - delta) * (s_cl * (p - C) - stay))
        return max(gain(p) for p in np.linspace(C * 1.001, q * 0.999, 300))

    dd = brentq(max_gain, 0.9, 0.9999)
    assert dd == pytest.approx(0.9895, abs=2e-3)
