#!/usr/bin/env python3
"""Procedural poster renderer, standard library only.

python3 render.py               -> art/entry.png (1024 px, adaptive 3x3 supersampling)
python3 render.py --preview     -> candidates/preview.png (256 px, 1 sample)
python3 render.py --candidates  -> candidates/excite-1..3.png (+ 300 px previews)
python3 render.py --cand N --out PATH   render one candidate somewhere
"""
import hashlib, math, os, random, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def hexc(s):
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


# ----------------------------------------------------------------- config
CANDIDATES = [
    dict(name='paper-boom', concept='plane', angle=27.0, nose=(0.70, 0.34), length=0.56,
         cone=50.0, pleats=11, seed=7, ringw=0.30, rmax=1.5, shards=40,
         pal=dict(sky0='#06031a', sky1='#2b0c66', sky2='#d01c7c', hot='#ffb01f',
                  core='#fff4d6', cyan='#27d8ff', violet='#5b2bff', paper='#f6f3ff')),
]
ENTRY = 3   # paper-dart-ahead (round 2): the pick


# ----------------------------------------------------------------- helpers
def hsh(i, s=0):
    x = (i * 374761393 + s * 668265263 + 1442695041) & 0xffffffff
    x = ((x ^ (x >> 13)) * 1274126177) & 0xffffffff
    return ((x ^ (x >> 16)) & 0xffffff) / 16777216.0


def mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ramp(stops, t):
    """stops: list of (pos, colour) sorted by pos."""
    if t <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return mix(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


def in_tri(px, py, t):
    (ax, ay), (bx, by), (cx, cy) = t
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = clamp(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy))
    return math.hypot(px - ax - vx * t, py - ay - vy * t)


def shoulder(c):
    return c if c < 0.82 else 0.82 + 0.18 * (1.0 - math.exp(-(c - 0.82) / 0.18))


# ----------------------------------------------------------------- scene: paper plane
def scene_plane(cfg):
    P = {k: hexc(v) for k, v in cfg['pal'].items()}
    a = math.radians(cfg['angle'])
    dx, dy = math.cos(a), -math.sin(a)          # flight direction (screen, y down)
    nx, ny = -dy, dx                            # perpendicular, "below" the axis
    Nx, Ny = cfg['nose']
    L = cfg['length']
    alpha = math.radians(cfg['cone'])
    pleats = cfg['pleats']

    def W(f, s):                                 # local -> world
        return (Nx + dx * f + nx * s, Ny + dy * f + ny * s)

    # plane polygons in local (f, s) coordinates
    nose = (0.0, 0.0)
    back = (-0.84 * L, 0.0)
    tip_top = (-L, -0.40 * L)
    crease = (-0.96 * L, -0.15 * L)
    tip_keel = (-0.70 * L, 0.20 * L)
    tip_far = (-0.93 * L, 0.11 * L)
    wing_top = (nose, tip_top, back)
    wing_far = (nose, back, tip_far)
    keel = (nose, back, tip_keel)
    outline = [(nose, tip_top), (tip_top, back), (nose, tip_keel), (back, tip_keel),
               (nose, tip_far), (back, tip_far)]
    ink = mix(P['sky0'], P['violet'], 0.15)

    sky = [(0.0, P['core']), (0.06, P['hot']), (0.25, P['sky2']), (0.6, P['sky1']), (1.15, P['sky0'])]
    lit = [(0.0, P['core']), (0.08, P['paper']), (0.28, mix(P['paper'], P['hot'], 0.8)), (0.55, P['sky2']), (0.85, P['sky1']), (1.0, P['sky0'])]
    cool = [(0.0, P['cyan']), (0.3, P['violet']), (0.65, P['sky1']), (1.0, P['sky0'])]
    ringw = cfg.get('ringw', 0.13)
    rmax = cfg.get('rmax', 1.05)

    rng = random.Random(cfg['seed'])
    shards = []                                   # paper shards torn off the shock front
    for _ in range(cfg.get('shards', 26)):
        side = rng.choice((-1, 1))
        r = 0.12 + rng.random() ** 0.8 * 0.7
        th = side * (alpha + (rng.random() * 0.22 + 0.02) * (0.4 + r))
        sz = 0.008 + 0.022 * rng.random() * (1.2 - r * 0.6)
        rot = rng.random() * math.pi * 2
        verts = []
        for k in range(3):
            ang = rot + k * 2.09 + rng.uniform(-0.5, 0.5)
            rad = sz * rng.uniform(0.55, 1.15)
            verts.append((rad * math.cos(ang), rad * math.sin(ang)))
        cf = -r * math.cos(th) + 0.015
        cs = r * math.sin(th)
        shards.append((cf, cs, sz * 1.2, verts, rng.random() < 0.5, r))

    def shade(x, y):
        qx, qy = x - Nx, y - Ny
        f = qx * dx + qy * dy
        s = qx * nx + qy * ny
        d0 = math.hypot(qx, qy)
        col = ramp(sky, d0)
        along = -f + 0.015
        th = math.atan2(s, along)
        ath = abs(th)
        # burst rays radiating from the nose (behind it only)
        if along > 0:
            br = 0.5 + 0.5 * math.cos(th * 46.0)
            br = br ** 6 * clamp(1.0 - d0 / 0.9) * clamp(along * 8.0)
            col = mix(col, P['hot'], 0.22 * br)
        # speed streaks parallel to the flight
        if f < 0.08:
            lw = 0.0085
            lane = math.floor(s / lw)
            h1 = hsh(lane, 1)
            if h1 < 0.42:
                head = -0.02 - hsh(lane, 2) * 0.55
                ln = 0.12 + hsh(lane, 3) * 0.45
                if head - ln < f < head:
                    off = abs(s - (lane + 0.5) * lw)
                    wdt = lw * (0.08 + 0.14 * hsh(lane, 4))
                    if off < wdt:
                        tt = (f - (head - ln)) / ln
                        c2 = P['cyan'] if hsh(lane, 5) < 0.5 else P['core']
                        col = mix(col, c2, 0.85 * tt * tt)
        # the shock cone: rings of pleated paper
        if along > 0 and ath < alpha + 0.02:
            r = math.hypot(along, s)
            u = (th + alpha) / (2 * alpha) * pleats
            tri = abs((u % 1.0) - 0.5) * 2.0          # 0 at a fold ridge centre, 1 at valleys
            rr = r + 0.028 * tri * (0.3 + r)          # zig-zag pleated hem
            j = int(rr / ringw)
            fr = rr / ringw - j
            u2 = u + 0.5 * j
            k = math.floor(u2)
            t = u2 - k
            edge = r * math.sin(alpha - ath)        # distance to the shock front
            if edge > 0:
                rn = r / rmax
                if k % 2 == 0:
                    pc = ramp(lit, rn + 0.15 * t)
                    pc = mix(pc, P['core'], 0.35 * (1 - t) * clamp(1 - rn * 1.5))
                else:
                    pc = ramp(cool, rn + 0.1 * (1 - t))
                    pc = mix(pc, P['sky0'], 0.25 * (1 - t))
                pc = mix(P['sky0'], pc, 0.8 + 0.2 * fr)  # overlap shadow at each ring hem
                al = clamp(1.0 - rn) ** 0.55 * clamp(along * 30.0)
                col = mix(col, pc, al)
            # bright shock front line
            ew = 0.003 + 0.005 * r
            e = abs(edge)
            if e < ew * 3:
                g = clamp(1.0 - e / ew) + 0.35 * clamp(1.0 - e / (ew * 3)) ** 2
                col = mix(col, P['core'], clamp(g) * clamp(1.0 - r / (rmax * 0.95)))
        # paper shards
        for (cf, cs, bound, verts, lite, rs) in shards:
            ef, es = f - cf, s - cs
            if ef * ef + es * es < bound * bound:
                if in_tri(ef, es, verts):
                    c2 = mix(P['paper'], P['hot'], 0.3 * rs) if lite else mix(P['cyan'], P['violet'], rs)
                    col = mix(col, c2, clamp(1.15 - rs))
        # the plane
        hit = None
        if in_tri(f, s, wing_far):
            hit = mix(P['sky1'], P['violet'], 0.3 + 0.7 * clamp(1 + f / L))
        if in_tri(f, s, keel):
            hit = mix(mix(P['violet'], P['cyan'], 0.45), P['paper'], 0.1 + 0.55 * clamp(1 + f / L) ** 2)
        if in_tri(f, s, wing_top):
            gl = clamp(1 + f / L)
            hit = mix(mix(P['cyan'], P['paper'], 0.8), P['paper'], gl)
            # second fold: inner strip next to the spine is a touch warmer
            if in_tri(f, s, (nose, crease, back)):
                hit = mix(hit, P['hot'], 0.18 * gl)
        if hit is not None or (-L * 1.08 < f < 0.02 and -0.48 * L < s < 0.28 * L):
            dmin = min(seg_dist(f, s, a[0], a[1], b[0], b[1]) for a, b in outline)
            crd = seg_dist(f, s, nose[0], nose[1], crease[0], crease[1])
            if hit is not None:
                col = hit
                if crd < 0.0018:
                    col = mix(col, P['cyan'], 0.5 * (1 - crd / 0.0018))
            elif dmin < 0.02:
                col = mix(col, ink, 0.7 * (1.0 - dmin / 0.02) ** 1.5)
            if dmin < 0.0038:
                col = mix(col, ink, 1.0 - dmin / 0.0038)
        # bloom on the nose, over everything
        bl = 1.1 * math.exp(-d0 / 0.028) + 0.35 * math.exp(-d0 / 0.11)
        col = (col[0] + P['hot'][0] * bl * 0.8 + bl * 0.25,
               col[1] + P['hot'][1] * bl * 0.8 + bl * 0.25,
               col[2] + P['hot'][2] * bl * 0.8 + bl * 0.25)
        return col

    return shade


# ----------------------------------------------------------------- scene: match lights the sunrise
def scene_match(cfg):
    P = {k: hexc(v) for k, v in cfg['pal'].items()}
    H = cfg['horizon']
    Fx, Fy = cfg['flame']                        # flame base (sits on the horizon)
    fa = math.radians(cfg['lean'])               # flame axis, tilted by the wind
    ax, ay = math.sin(fa), -math.cos(fa)
    px, py = -ay, ax
    FH, FR = cfg['flame_h'], cfg['flame_r']
    hx, hy = Fx + 0.012, Fy + 0.05                # match head
    sx, sy = cfg['stick_end']
    ink = mix(P['sky0'], P['violet'], 0.2)
    sky = [(0.0, P['core']), (0.07, P['hot']), (0.22, P['orange']), (0.42, P['sky2']),
           (0.7, P['sky1']), (1.1, P['sky0'])]
    sun_r = cfg['sun_r']

    def flame(x, y, k, bend):
        qx, qy = x - Fx, y - Fy
        u = qx * ax + qy * ay
        v = qx * px + qy * py
        h, r = FH * k, FR * k
        v -= bend * h * (u / h) ** 2 if u > 0 else 0.0
        if u < 0:
            return u * u + v * v < r * r
        if u >= h:
            return False
        return abs(v) < r * (1.0 - u / h) ** 1.5 * (1.0 + 0.6 * math.sin(math.pi * u / h) ** 2)

    def shade(x, y):
        qx, qy = x - Fx, y - Fy
        d0 = math.hypot(qx, qy)
        if y < H:
            col = ramp(sky, d0)
            th = math.atan2(qy, qx)
            br = (0.5 + 0.5 * math.cos(th * 36.0)) ** 5 * clamp(1.0 - d0 / 1.2)
            col = mix(col, P['hot'], 0.35 * br * clamp(d0 * 6))
            # banded sun disc around the flame, cut by the horizon
            if d0 < sun_r:
                band = int(d0 / sun_r * 7)
                sc = mix(P['core'], P['hot'], band / 6.0) if band % 2 == 0 else mix(P['hot'], P['orange'], band / 6.0)
                col = mix(col, sc, 0.85)
        else:
            dy_ = y - H
            col = mix(mix(P['sky1'], P['sky0'], 0.4), P['sky0'], clamp(dy_ / 0.3))
            # glitter path: horizontal dashes, wider with depth
            lane = int(dy_ / 0.011)
            spread = 0.04 + dy_ * 1.2
            if (dy_ % 0.011) < 0.004 + 0.012 * dy_:
                off = (x - Fx) / spread
                n = math.floor(off * 1.6 + hsh(lane, 9) * 3)
                if hsh(n, lane) < clamp(1.0 - abs(off)) * 0.95:
                    c2 = P['core'] if abs(off) < 0.25 else P['hot'] if abs(off) < 0.6 else P['sky2']
                    col = mix(col, c2, clamp(1.1 - dy_ * 2.0))
        # the match stick: capsule from head to the end
        ds = seg_dist(x, y, hx, hy, sx, sy)
        sw = cfg['stick_w']
        if ds < sw + 0.004:
            vx, vy = sx - hx, sy - hy
            vl = math.hypot(vx, vy)
            side = ((x - hx) * vy - (y - hy) * vx) / vl / sw   # -1..1 across the stick
            along = ((x - hx) * vx + (y - hy) * vy) / (vl * vl)
            wood = mix(P['wood'], P['hot'], clamp(0.6 - side * 0.5) * clamp(1 - along * 1.5))
            wood = mix(wood, P['violet'], clamp(side) * 0.6)
            col = wood if ds < sw else ink
        # match head
        ex, ey = (x - hx) / 0.045, (y - hy) / 0.055
        eh = ex * ex + ey * ey
        if eh < 1.25:
            col = ink if eh > 1.0 else mix(P['red'], P['hot'], clamp(0.6 - ey * 0.6 - ex * 0.3))
        # layered flame
        if flame(x, y, 1.06, cfg['bend']):
            col = ink
        if flame(x, y, 1.0, cfg['bend']):
            col = P['orange']
            if flame(x, y, 0.78, cfg['bend'] * 1.2):
                col = P['hot']
                if flame(x, y, 0.5, cfg['bend'] * 1.4):
                    col = P['core']
        bl = 0.9 * math.exp(-d0 / 0.05) + 0.35 * math.exp(-d0 / 0.16)
        return (col[0] + P['hot'][0] * bl * 0.6, col[1] + P['hot'][1] * bl * 0.6, col[2] + P['hot'][2] * bl * 0.6)

    return shade


CANDIDATES += [
    dict(name='match-sunrise', concept='match', horizon=0.66, flame=(0.44, 0.585), lean=-14.0,
         flame_h=0.34, flame_r=0.095, bend=-0.07, stick_end=(1.02, 1.25), stick_w=0.045, sun_r=0.30,
         pal=dict(sky0='#05041c', sky1='#2a0d5c', sky2='#c8186e', orange='#ff5a1a', hot='#ffb627',
                  core='#fff6dc', violet='#4f2bd8', wood='#e9b97a', red='#d6202e')),
    dict(name='paper-boom-teal', concept='plane', angle=36.0, nose=(0.72, 0.30), length=0.64,
         cone=46.0, pleats=9, seed=11, ringw=0.34, rmax=1.6, shards=48,
         pal=dict(sky0='#020f1c', sky1='#063a5a', sky2='#e0244e', hot='#ffa21a',
                  core='#fff7e0', cyan='#1fe3d0', violet='#2f5bff', paper='#fbfaf4')),
]

# ----------------------------------------------------------------- scene: paper dart ahead of its boom (round 2)
def scene_dart(cfg):
    P = {k: hexc(v) for k, v in cfg['pal'].items()}
    a = math.radians(cfg['angle'])
    dx, dy = math.cos(a), -math.sin(a)          # flight direction (screen, y down)
    nx, ny = -dy, dx                            # perpendicular, "below" the flight axis
    Nx, Ny = cfg['nose']
    L = cfg['length']
    alpha = math.radians(cfg['cone'])
    pleats = cfg['pleats']
    gap = cfg['gap']
    Fx, Fy = Nx + dx * gap, Ny + dy * gap         # the white-hot flare, just ahead of the nose
    ink = mix(P['sky0'], P['violet'], 0.12)

    # classic dart, local (f, s): s < 0 is the upper (near, lit) wing
    nose = (0.0, 0.0)
    tail = (-0.90 * L, 0.0)
    tip_up = (-L, -0.31 * L)
    tip_lo = (-0.95 * L, 0.19 * L)
    keel_a, keel_b = (-0.42 * L, 0.0), (-0.86 * L, 0.075 * L)
    wing_up = (nose, tip_up, tail)
    wing_lo = (nose, tail, tip_lo)
    keel = (keel_a, tail, keel_b)
    outline = [(nose, tip_up), (tip_up, tail), (nose, tip_lo), (tip_lo, tail),
               (keel_a, keel_b), (keel_b, tail), (nose, tail)]

    sky = [(0.0, P['core']), (0.035, P['core']), (0.09, P['hot']), (0.28, P['sky2']),
           (0.62, P['sky1']), (1.2, P['sky0'])]
    lit = [(0.0, P['core']), (0.10, P['paper']), (0.30, mix(P['paper'], P['hot'], 0.85)),
           (0.6, P['sky2']), (1.0, P['sky1'])]
    cool = [(0.0, P['cyan']), (0.25, P['violet']), (0.6, P['sky1']), (1.0, P['sky0'])]
    rmax = cfg['rmax']
    tilt = 0.30                                   # ellipse squash of the cone's cross-sections

    def wpos(f, s):
        return (Nx + dx * f + nx * s, Ny + dy * f + ny * s)

    rng = random.Random(cfg['seed'])
    shards = []
    while len(shards) < cfg['shards']:
        side = rng.choice((-1, 1))
        r = 0.10 + rng.random() ** 0.9 * 0.75
        th = side * (alpha + (rng.random() * 0.20 + 0.025) * (0.5 + r))
        sz = 0.007 + 0.02 * rng.random() * (1.1 - r * 0.6)
        rot = rng.random() * math.pi * 2
        verts = []
        for k in range(3):
            ang = rot + k * 2.09 + rng.uniform(-0.5, 0.5)
            rad = sz * rng.uniform(0.55, 1.15)
            verts.append((rad * math.cos(ang), rad * math.sin(ang)))
        cf, cs = -r * math.cos(th), r * math.sin(th)
        wx, wy = wpos(cf, cs)
        if wx + wy < 0.62 or not (-0.05 < wx < 1.05 and -0.05 < wy < 1.05):
            continue                               # keep the top-left calm and stay on canvas
        shards.append((cf, cs, sz * 1.2, verts, rng.random() < 0.55, r))

    def shade(x, y):
        qx, qy = x - Nx, y - Ny
        f = qx * dx + qy * dy
        s = qx * nx + qy * ny
        fx, fy = x - Fx, y - Fy
        dF = math.hypot(fx, fy)
        col = ramp(sky, dF)
        # calm, dark top-left corner
        vig = clamp((0.75 - (x + y)) / 0.75)
        col = mix(col, P['sky0'], 0.55 * vig * vig)
        along = -f
        th = math.atan2(s, along) if along > 0 else (math.pi if s >= 0 else -math.pi)
        ath = abs(th)
        # faint burst rays from the flare, outside the cone only
        if ath > alpha:
            ph = math.atan2(fy, fx)
            br = (0.5 + 0.5 * math.cos(ph * 40.0)) ** 6 * clamp(1.0 - dF / 0.8) * clamp(dF * 10 - 0.4)
            col = mix(col, P['hot'], 0.25 * br * (1 - vig))
        # speed streaks
        if f < -0.02 and x + y > 0.7:
            lw = 0.0095
            lane = math.floor(s / lw)
            if hsh(lane, 1) < 0.38:
                head = -0.06 - hsh(lane, 2) * 0.55
                ln = 0.12 + hsh(lane, 3) * 0.4
                if head - ln < f < head:
                    off = abs(s - (lane + 0.5) * lw)
                    wdt = lw * (0.08 + 0.12 * hsh(lane, 4))
                    if off < wdt:
                        tt = (f - (head - ln)) / ln
                        c2 = P['cyan'] if hsh(lane, 5) < 0.5 else P['core']
                        col = mix(col, c2, 0.75 * tt * tt * clamp((x + y - 0.7) * 4))
        # the shock cone: radial paper pleats converging on the nose
        if along > 0:
            r = math.hypot(along, s)
            edge = r * math.sin(alpha - ath)       # distance to the shock line (inside > 0)
            if edge > 0:
                w = th / alpha                      # -1 (upper rim) .. 1 (lower rim)
                u = (w + 1.0) * 0.5 * pleats
                k = int(u)
                t = u - k
                rn = r / rmax
                # cross-section ripples: ellipses centred on the axis -> reads as a round cone
                if k % 2 == 0:
                    pc = ramp(lit, rn + 0.12 * t)
                    pc = mix(pc, P['core'], 0.3 * (1 - t) * clamp(1 - rn * 2))
                else:
                    pc = ramp(cool, rn * 0.9 + 0.12 * (1 - t))
                # round-cone shading: upper half faces the flare, lower half falls into shadow
                lightw = clamp(0.5 - 0.5 * w)
                pc = mix(mix(pc, P['sky0'], 0.45), pc, 0.35 + 0.65 * lightw + 0.3 * (1 - abs(w)))
                al = clamp(1.0 - rn) ** 0.6 * clamp(along * 40.0)
                col = mix(col, pc, al)
            # boom rings: elliptical cross-sections of the cone (back half dimmer)
            for ai in cfg['rings']:
                rho = ai * math.tan(alpha)
                ee = math.sqrt(((along - ai) / (tilt * rho)) ** 2 + (s / rho) ** 2) - 1.0
                dd = abs(ee) * tilt * rho
                rw = 0.0016 + 0.0028 * ai
                if dd < rw * 3:
                    front = 1.0 if along > ai else 0.35
                    g = clamp(1.0 - dd / rw) + 0.3 * clamp(1.0 - dd / (rw * 3)) ** 2
                    col = mix(col, P['core'], clamp(g) * front * clamp(1.0 - ai / rmax) ** 0.5)
            # white shock lines along both edges
            e = abs(edge)
            ew = 0.0024 + 0.0035 * r
            if e < ew * 4:
                g = clamp(1.0 - e / ew) + 0.4 * clamp(1.0 - e / (ew * 4)) ** 2
                col = mix(col, P['core'], clamp(g) * clamp(1.0 - r / (rmax * 0.9)) ** 0.7)
        # paper shards
        for (cf, cs, bound, verts, lite, rs) in shards:
            ef, es = f - cf, s - cs
            if ef * ef + es * es < bound * bound and in_tri(ef, es, verts):
                c2 = mix(P['paper'], P['hot'], 0.3 * rs) if lite else mix(P['cyan'], P['violet'], rs)
                col = mix(col, c2, clamp(1.15 - rs))
        # the paper dart
        if -L * 1.06 < f < 0.02 and -0.36 * L < s < 0.22 * L:
            hit = None
            gl = clamp(1 + f / L)
            if in_tri(f, s, wing_lo):
                hit = mix(mix(P['violet'], P['sky1'], 0.35), mix(P['cyan'], P['violet'], 0.35), gl * gl)
            if in_tri(f, s, keel):
                hit = mix(P['sky0'], P['violet'], 0.45 * gl)
            if in_tri(f, s, wing_up):
                hit = mix(mix(P['cyan'], P['paper'], 0.78), P['paper'], gl)
                # rim light along the leading edge that faces the flare
                rd = seg_dist(f, s, 0, 0, tip_up[0], tip_up[1])
                if rd < 0.012:
                    hit = mix(hit, P['core'], (1 - rd / 0.012) ** 2 * 0.9)
                    hit = mix(hit, P['hot'], 0.35 * (1 - rd / 0.012) * gl)
            dmin = min(seg_dist(f, s, p[0], p[1], q[0], q[1]) for p, q in outline)
            if hit is not None:
                col = hit
            elif dmin < 0.018:
                col = mix(col, ink, 0.6 * (1.0 - dmin / 0.018) ** 1.5)
            if dmin < 0.0036:
                col = mix(col, ink, 1.0 - dmin / 0.0036)
        # bloom on the flare (ahead of the nose)
        bl = 1.2 * math.exp(-dF / 0.022) + 0.35 * math.exp(-dF / 0.10)
        return (col[0] + P['hot'][0] * bl * 0.8 + bl * 0.25,
                col[1] + P['hot'][1] * bl * 0.8 + bl * 0.25,
                col[2] + P['hot'][2] * bl * 0.8 + bl * 0.25)

    return shade


CANDIDATES += [
    dict(name='paper-dart-ahead', concept='dart', angle=30.0, nose=(0.73, 0.35), length=0.66,
         cone=29.0, pleats=6, seed=11, rmax=1.45, shards=44, gap=0.075, rings=(0.30, 0.58, 0.92),
         pal=dict(sky0='#020f1c', sky1='#063a5a', sky2='#e0244e', hot='#ffa21a',
                  core='#fff7e0', cyan='#1fe3d0', violet='#2f5bff', paper='#fbfaf4')),
]

SCENES = {'plane': scene_plane, 'match': scene_match, 'dart': scene_dart}


# ----------------------------------------------------------------- rendering
def render(cfg, size, ss=3):
    shade = SCENES[cfg['concept']](cfg)
    inv = 1.0 / size

    def sample(x, y):
        c = shade(x * inv, y * inv)
        return (shoulder(c[0]), shoulder(c[1]), shoulder(c[2]))

    img = [[sample(i + 0.5, j + 0.5) for i in range(size)] for j in range(size)]
    if ss > 1:
        # adaptive supersampling: every pixel whose colour differs from a neighbour
        # gets a full ss x ss grid (edges, thin lines); flat/smooth areas keep 1 sample.
        thr = 0.02
        mark = [bytearray(size) for _ in range(size)]
        for j in range(size):
            row, mr = img[j], mark[j]
            nxt = img[j + 1] if j + 1 < size else None
            for i in range(size):
                c = row[i]
                if i + 1 < size:
                    o = row[i + 1]
                    if abs(c[0] - o[0]) + abs(c[1] - o[1]) + abs(c[2] - o[2]) > thr:
                        mr[i] = mr[i + 1] = 1
                if nxt is not None:
                    o = nxt[i]
                    if abs(c[0] - o[0]) + abs(c[1] - o[1]) + abs(c[2] - o[2]) > thr:
                        mr[i] = mark[j + 1][i] = 1
        offs = [(k + 0.5) / ss for k in range(ss)]
        n = float(ss * ss)
        for j in range(size):
            mr, row = mark[j], img[j]
            for i in range(size):
                if mr[i]:
                    r = g = b = 0.0
                    for oy in offs:
                        for ox in offs:
                            c = sample(i + ox, j + oy)
                            r += c[0]; g += c[1]; b += c[2]
                    row[i] = (r / n, g / n, b / n)
    out = []
    for row in img:
        bb = bytearray(3 * size)
        for i, c in enumerate(row):
            bb[3 * i] = int(clamp(c[0]) * 255 + 0.5)
            bb[3 * i + 1] = int(clamp(c[1]) * 255 + 0.5)
            bb[3 * i + 2] = int(clamp(c[2]) * 255 + 0.5)
        out.append(bytes(bb))
    return out


# ----------------------------------------------------------------- PNG I/O
def _chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _filter_row(ft, row, prev, bpp=3):
    n = len(row)
    if ft == 0:
        return row
    out = bytearray(n)
    for i in range(n):
        a = row[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if ft == 1:
            p = a
        elif ft == 2:
            p = b
        elif ft == 3:
            p = (a + b) >> 1
        else:
            p = _paeth(a, b, c)
        out[i] = (row[i] - p) & 0xff
    return bytes(out)


def png_bytes(rows):
    h, w = len(rows), len(rows[0]) // 3
    raw = bytearray()
    prev = bytes(len(rows[0]))
    for row in rows:
        best = None
        for ft in range(5):
            fr = _filter_row(ft, row, prev)
            score = sum(v if v < 128 else 256 - v for v in fr)
            if best is None or score < best[0]:
                best = (score, ft, fr)
        raw.append(best[1])
        raw += best[2]
        prev = row
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + _chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + _chunk(b'IEND', b''))


def read_png(path):
    """Minimal decoder for 8-bit RGB non-interlaced PNGs -> (w, h, rows)."""
    with open(path, 'rb') as fh:
        data = fh.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos, idat, w, h = 8, b'', 0, 0
    while pos < len(data):
        ln, = struct.unpack('>I', data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b'IHDR':
            w, h = struct.unpack('>II', body[:8])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = 3 * w
    rows, prev = [], bytes(stride)
    for j in range(h):
        ft = raw[j * (stride + 1)]
        line = bytearray(raw[j * (stride + 1) + 1:(j + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            p = 0 if ft == 0 else a if ft == 1 else b if ft == 2 else (a + b) >> 1 if ft == 3 else _paeth(a, b, c)
            line[i] = (line[i] + p) & 0xff
        rows.append(bytes(line))
        prev = rows[-1]
    return w, h, rows


def box_downscale(rows, w, h, out):
    """Area-weighted box filter from w x h to out x out."""
    sx, sy = w / out, h / out

    def spans(n, s):
        res = []
        for o in range(n):
            a, b = o * s, (o + 1) * s
            lst, k = [], int(a)
            while k < b and k < int(math.ceil(b)):
                wgt = min(b, k + 1) - max(a, k)
                if wgt > 0:
                    lst.append((k, wgt))
                k += 1
            res.append(lst)
        return res

    xs, ys = spans(out, sx), spans(out, sy)
    res = []
    for yl in ys:
        bb = bytearray(3 * out)
        for o, xl in enumerate(xs):
            r = g = b = tw = 0.0
            for (y, wy) in yl:
                row = rows[y]
                for (x, wx) in xl:
                    wt = wx * wy
                    r += row[3 * x] * wt; g += row[3 * x + 1] * wt; b += row[3 * x + 2] * wt
                    tw += wt
            bb[3 * o] = int(r / tw + 0.5); bb[3 * o + 1] = int(g / tw + 0.5); bb[3 * o + 2] = int(b / tw + 0.5)
        res.append(bytes(bb))
    return res


def write(path, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data = png_bytes(rows)
    with open(path, 'wb') as fh:
        fh.write(data)
    print('%s  %s  %d bytes' % (hashlib.sha256(data).hexdigest(), os.path.relpath(path, HERE), len(data)))
    return data


def preview300(src, dst):
    w, h, rows = read_png(src)
    write(dst, box_downscale(rows, w, h, 300))


def main(argv):
    cand = ENTRY
    if '--cand' in argv:
        cand = int(argv[argv.index('--cand') + 1]) - 1
    if '--preview' in argv:
        size = int(argv[argv.index('--size') + 1]) if '--size' in argv else 256
        write(os.path.join(HERE, 'candidates', 'preview.png'), render(CANDIDATES[cand], size, ss=1))
        return
    if '--candidates' in argv:
        for k, cfg in enumerate(CANDIDATES):
            p = os.path.join(HERE, 'candidates', 'excite-%d.png' % (k + 1))
            write(p, render(cfg, 1024))
            preview300(p, os.path.join(HERE, 'candidates', 'excite-%d-300.png' % (k + 1)))
        return
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(HERE, 'art', 'entry.png')
    write(out, render(CANDIDATES[cand], 1024))


if __name__ == '__main__':
    main(sys.argv[1:])
