"""Bộ sinh ECG tổng hợp (mô hình tổng Gaussian) cho các nhịp giảng dạy.

Trả về tín hiệu (mV) theo thời gian và chú thích vị trí sóng của 1 nhịp mẫu
để vẽ vùng highlight (p, pr, qrs, st, t, qt, rr).
"""
from __future__ import annotations

import numpy as np

FS = 500  # Hz

# ---- hình thái cơ bản: (biên độ mV, lệch so với đỉnh R (s), sigma (s)) ----
P_WAVE = [(0.15, 0.0, 0.025)]
QRS_NARROW = [(-0.12, -0.025, 0.008), (1.1, 0.0, 0.011), (-0.25, 0.028, 0.009)]
T_WAVE = [(0.30, 0.26, 0.045)]


def _g(t, a, mu, s):
    return a * np.exp(-((t - mu) ** 2) / (2 * s * s))


class Strip:
    def __init__(self, seconds: float):
        self.t = np.arange(0, seconds, 1 / FS)
        self.y = np.zeros_like(self.t)
        self.ann: dict[str, tuple[float, float]] = {}

    def add(self, center: float, comps):
        for a, off, s in comps:
            self.y += _g(self.t, a, center + off, s)

    def p(self, at, comps=P_WAVE):
        self.add(at, comps)

    def beat(self, r, qrs=QRS_NARROW, t=T_WAVE, extra=()):
        self.add(r, list(qrs) + list(t) + list(extra))


def _span(comps, r):
    lo = min(r + off - 2.2 * s for _, off, s in comps)
    hi = max(r + off + 2.2 * s for _, off, s in comps)
    return lo, hi


def _annotate(st: Strip, r, pr, qrs, t, nxt=None, p=P_WAVE):
    """Chú thích dựa trên nhịp mẫu có đỉnh R tại r, sóng P ở r-pr."""
    q0, q1 = _span(qrs, r)
    t0, t1 = _span(t, r)
    st.ann["qrs"] = (q0, q1)
    st.ann["t"] = (t0, t1)
    st.ann["st"] = (q1, t0 + 0.02)
    st.ann["qt"] = (q0, t1)
    if pr is not None:
        p0, p1 = _span(p, r - pr)
        st.ann["p"] = (p0, p1)
        st.ann["pr"] = (p0, q0)
    if nxt is not None:
        st.ann["rr"] = (r, nxt)


def _rr(hr):
    return 60.0 / max(hr, 1)


def _t_for(hr, base=T_WAVE):
    # QT ngắn lại khi nhịp nhanh (xấp xỉ Bazett)
    k = np.sqrt(_rr(hr) / 0.8)
    return [(a, off * k, s * max(k, 0.6)) for a, off, s in base]


# ---------------- các nhịp ----------------

def regular(hr, seconds, pr=0.17, p=P_WAVE, qrs=QRS_NARROW, t=None, extra=(), show_p=True):
    st = Strip(seconds)
    rr = _rr(hr)
    t = t or _t_for(hr)
    beats = np.arange(0.45, seconds + rr, rr)
    for r in beats:
        if show_p:
            st.p(r - pr, p)
        st.beat(r, qrs, t, extra)
    _annotate(st, beats[1], pr if show_p else None, qrs, t, beats[2], p)
    return st


def af(hr, seconds, rng):
    st = Strip(seconds)
    mean = _rr(hr)
    r, beats = 0.35, []
    while r < seconds + 1:
        beats.append(r)
        r += mean * rng.uniform(0.55, 1.45)
    for b in beats:
        st.beat(b, t=_t_for(hr, [(0.22, 0.26, 0.045)]))
    f = np.zeros_like(st.t)
    for _ in range(4):
        f += rng.uniform(0.02, 0.045) * np.sin(2 * np.pi * rng.uniform(5, 8) * st.t + rng.uniform(0, 6))
    st.y += f
    _annotate(st, beats[1], None, QRS_NARROW, T_WAVE, beats[2])
    st.ann["p"] = (beats[1] - 0.35, beats[1] - 0.05)  # vùng sóng f
    return st


def flutter(hr, seconds):
    st = Strip(seconds)
    fr = 0.2  # sóng F 300/ph
    ph = (st.t % fr) / fr
    st.y += 0.1 + 0.25 * np.where(ph < 0.8, -ph / 0.8, -(1 - ph) / 0.2)  # răng cưa âm ở DII
    conduct = 2 if hr >= 120 else 4
    beats = np.arange(0.4, seconds + 1, fr * conduct)
    for r in beats:
        st.beat(r, t=[(0.2, 0.22, 0.04)])
    _annotate(st, beats[1], None, QRS_NARROW, [(0.2, 0.22, 0.04)], beats[2])
    st.ann["p"] = (beats[1] + 0.25, beats[1] + 0.25 + 2 * fr)
    return st


def ectopic(hr, seconds, kind):
    st = Strip(seconds)
    rr = _rr(hr)
    t = _t_for(hr)
    times, r = [], 0.45
    i = 0
    wide = [(0.25, -0.04, 0.03), (1.35, 0.03, 0.035), (-0.3, 0.1, 0.03)]
    while r < seconds + rr:
        if i == 3:
            early = r - rr + rr * 0.6
            if kind == "pvc":
                st.beat(early, wide, [(-0.45, 0.34, 0.06)])
                _annotate(st, early, None, wide, [(-0.45, 0.34, 0.06)])
                r = early + 2 * rr - rr * 0.6  # nghỉ bù hoàn toàn
            else:
                st.p(early - 0.14, [(0.1, 0.0, 0.02), (-0.04, 0.03, 0.015)])
                st.beat(early, t=t)
                _annotate(st, early, 0.14, QRS_NARROW, t, p=[(0.1, 0.0, 0.02)])
                r = early + rr
            i += 1
            continue
        st.p(r - 0.17)
        st.beat(r, t=t)
        times.append(r)
        r += rr
        i += 1
    return st


def av_block(hr, seconds, kind):
    st = Strip(seconds)
    t = _t_for(hr)
    if kind == "avb3":
        pp = 0.75
        for p in np.arange(0.2, seconds + 1, pp):
            st.p(p)
        rr = _rr(max(hr, 30))
        wide = [(-0.1, -0.03, 0.02), (1.0, 0.02, 0.03), (-0.3, 0.08, 0.025)]
        tw = [(-0.3, 0.38, 0.07)]
        beats = np.arange(0.6, seconds + 1, rr)
        for r in beats:
            st.beat(r, wide, tw)
        _annotate(st, beats[1], None, wide, tw, beats[2])
        st.ann["p"] = (0.2 - 0.06, 0.2 + 2 * pp + 0.06)
        return st
    pp = _rr(hr)
    p_times = np.arange(0.25, seconds + 1, pp)
    pr_seq = {"wenckebach": [0.16, 0.25, 0.32, None], "mobitz2": [0.18, 0.18, None]}[kind]
    first = None
    for i, p in enumerate(p_times):
        st.p(p)
        pr = pr_seq[i % len(pr_seq)]
        if pr is not None:
            st.beat(p + pr, t=t)
            if first is None and i >= 0:
                first = (p + pr, pr)
        elif "drop" not in st.ann:
            st.ann["drop"] = (p - 0.06, p + 0.06)
    _annotate(st, first[0], first[1], QRS_NARROW, t)
    if kind == "mobitz2":
        st.ann["p"] = st.ann["drop"]
    else:
        # highlight PR dài nhất trước nhát rớt
        r3 = p_times[2] + pr_seq[2]
        st.ann["pr"] = (p_times[2] - 0.055, r3 - 0.04)
    return st


def vf(seconds, rng):
    st = Strip(seconds)
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 0.4 * st.t + rng.uniform(0, 6))
    for _ in range(5):
        st.y += env * rng.uniform(0.08, 0.2) * np.sin(2 * np.pi * rng.uniform(3, 7) * st.t + rng.uniform(0, 6))
    return st


def build(rhythm: str, hr: int, seconds: float = 4.0, seed: int = 7) -> Strip:
    rng = np.random.default_rng(seed)
    hr = int(hr or 75)
    if rhythm == "normal":
        st = regular(max(60, min(hr, 100)), seconds)
    elif rhythm == "brady":
        st = regular(min(hr, 55), seconds)
    elif rhythm == "tachy":
        st = regular(max(hr, 110), seconds, pr=0.14)
    elif rhythm == "long_qt":
        st = regular(hr, seconds, t=[(0.28, 0.42, 0.06)])
    elif rhythm == "af":
        st = af(hr, seconds, rng)
    elif rhythm == "flutter":
        st = flutter(hr, seconds)
    elif rhythm in ("pvc", "pac"):
        st = ectopic(hr, seconds, rhythm)
    elif rhythm == "avb1":
        st = regular(hr, seconds, pr=0.32)
    elif rhythm in ("wenckebach", "mobitz2", "avb3"):
        st = av_block(hr, seconds, rhythm)
    elif rhythm == "rbbb":  # V1: rSR'
        st = regular(hr, seconds, qrs=[(0.3, -0.035, 0.012), (-0.45, 0.0, 0.014), (0.85, 0.055, 0.016)],
                     t=[(-0.18, 0.3, 0.05)])
    elif rhythm == "lbbb":  # V6: R rộng có khía
        st = regular(hr, seconds, qrs=[(0.85, -0.02, 0.022), (0.95, 0.045, 0.024)], t=[(-0.3, 0.32, 0.055)])
    elif rhythm == "svt":
        st = regular(max(hr, 160), seconds, show_p=False, t=[(0.22, 0.17, 0.035)])
    elif rhythm == "vt":
        rr = _rr(max(hr, 150))
        st = Strip(seconds)
        wide = [(1.4, 0.0, 0.04), (-0.35, 0.08, 0.03)]
        tw = [(-0.5, 0.2, 0.045)]
        beats = np.arange(0.3, seconds + rr, rr)
        for r in beats:
            st.beat(r, wide, tw)
        _annotate(st, beats[2], None, wide, tw, beats[3])
    elif rhythm == "vf":
        st = vf(seconds, rng)
    elif rhythm == "stemi":
        st = regular(hr, seconds, t=[(0.5, 0.24, 0.05)], extra=[(0.32, 0.12, 0.06)])
        st.ann["st"] = (st.ann["qrs"][1], st.ann["qrs"][1] + 0.16)
    elif rhythm == "st_depression":
        st = regular(hr, seconds, t=[(-0.12, 0.27, 0.045)], extra=[(-0.15, 0.11, 0.05)])
        st.ann["st"] = (st.ann["qrs"][1], st.ann["qrs"][1] + 0.15)
    elif rhythm == "hyperk":
        st = regular(hr, seconds, p=[(0.07, 0, 0.025)], pr=0.22,
                     qrs=[(-0.1, -0.03, 0.012), (1.0, 0.0, 0.016), (-0.3, 0.04, 0.014)], t=[(0.95, 0.24, 0.028)])
    elif rhythm == "hypok":
        st = regular(hr, seconds, t=[(0.08, 0.25, 0.05)], extra=[(-0.06, 0.12, 0.05), (0.14, 0.42, 0.045)])
        st.ann["t"] = (st.ann["t"][0], st.ann["t"][1] + 0.18)
    elif rhythm == "lvh":
        st = regular(hr, seconds, qrs=[(-0.1, -0.025, 0.008), (2.8, 0.0, 0.013), (-0.3, 0.03, 0.01)],
                     t=[(-0.3, 0.28, 0.06)], extra=[(-0.12, 0.12, 0.05)])
    elif rhythm == "wpw":
        qrs = [(0.3, -0.035, 0.022), (1.0, 0.01, 0.012), (-0.2, 0.04, 0.01)]
        st = regular(hr, seconds, pr=0.11, qrs=qrs)
    elif rhythm == "pericarditis":
        st = regular(hr, seconds, t=[(0.35, 0.23, 0.05)], extra=[(0.16, 0.13, 0.07), (-0.07, -0.08, 0.03)])
    else:
        st = regular(75, seconds)
    return st


RHYTHMS = ["normal", "brady", "tachy", "long_qt", "af", "flutter", "pac", "pvc", "avb1", "wenckebach",
           "mobitz2", "avb3", "rbbb", "lbbb", "svt", "vt", "vf", "stemi", "st_depression", "hyperk", "hypok",
           "lvh", "wpw", "pericarditis"]
HIGHLIGHTS = ["none", "p", "pr", "qrs", "st", "t", "qt", "rr"]
