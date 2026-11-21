"""gui/reactor.py — Perplexity 3D Particle Point-Cloud Voice Sphere.
Contributed by Aman Kumar (@iamTechieAman).

Renders the official Perplexity-inspired 3D volumetric starlight particle sphere:
- 1,500+ organic Fibonacci surface particles projected in three dimensions.
- Perspective camera projection with volumetric depth sorting (Z-ordering).
- Dynamic breathing wave when idle, and voice-synchronized spherical harmonic
  fluid ripple waves when speaking or listening (real-time audio amplitude reactivity).
- Pure software QPainter CPU rendering with vectorized NumPy math for 60 FPS performance.
- State-aware starlight palette (pure white starlight, emerald/cyan active, warm amber speaking, muted red).
"""
from __future__ import annotations

import math
import numpy as np

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QRadialGradient

from gui.theme import C

_CAM_D = 4.2  # perspective distance in radii


def _rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _with_alpha(col: QColor, a: float) -> QColor:
    c = QColor(col)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


class Reactor3D:
    """Perplexity 3D Point-Cloud Particle Sphere renderer.
    `step()` advances physics & time, `paint()` renders the volumetric starlight cloud.
    """

    # Symmetrical vertical extent in core radii so HudCanvas centers the sphere perfectly
    TOP = 1.15
    BOTTOM = 1.15

    def __init__(self, n_points: int = 1500):
        self.n_points = n_points

        # ── 1. Fibonacci Sphere Point Cloud with Organic Jitter ─────────────────
        phi = math.pi * (3.0 - math.sqrt(5.0))  # Golden angle ~ 2.399963
        i = np.arange(n_points)
        y = 1.0 - (i / float(n_points - 1)) * 2.0  # from +1 down to -1

        rng = np.random.default_rng(101)

        # Subtle organic angular perturbation to break visible spiral tracks
        theta = phi * i + rng.uniform(-0.045, 0.045, n_points)
        y = np.clip(y + rng.uniform(-0.02, 0.02, n_points), -1.0, 1.0)
        r_plane = np.sqrt(np.maximum(0.0, 1.0 - y * y))

        x = np.cos(theta) * r_plane
        z = np.sin(theta) * r_plane

        # Volumetric shell: points distributed across radial depth [0.94, 1.06]
        rad_dist = 1.0 + rng.normal(0.0, 0.038, n_points)
        self._base_pts = np.vstack([x, y, z]) * rad_dist

        self._azimuth = np.arctan2(z, x)
        self._polar = np.arccos(np.clip(y, -1.0, 1.0))
        self._pt_sizes = rng.uniform(0.85, 1.25, n_points)
        self._twinkle = rng.uniform(0.0, 2 * math.pi, n_points)

        # ── 2. Ambient Floating Outer Starlight Motes ─────────────────────────
        n_motes = 50
        m_i = np.arange(n_motes)
        m_y = 1.0 - (m_i / float(n_motes - 1)) * 2.0
        m_r = np.sqrt(np.maximum(0.0, 1.0 - m_y * m_y))
        m_th = phi * m_i * 1.618
        m_rad = rng.uniform(1.15, 1.40, n_motes)
        self._mote_pts = np.vstack([np.cos(m_th) * m_r, m_y, np.sin(m_th) * m_r]) * m_rad
        self._mote_twinkle = rng.uniform(0.0, 2 * math.pi, n_motes)

        self.spin = 0.0
        self.time = 0.0

    # ── Motion & Animation State ──────────────────────────────────────────────
    def step(self, dt: float, speaking: bool, thinking: bool, muted: bool) -> None:
        dt = min(0.10, max(0.0, dt))
        rate = 0.12 if muted else (1.20 if thinking else (0.65 if speaking else 0.28))
        self.spin += dt * rate
        self.time += dt

    # ── Volumetric Render Frame ───────────────────────────────────────────────
    def paint(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        main: QColor,
        acc: QColor,
        white: QColor,
        amp: float,
        live: bool,
        name: str = "",
    ) -> None:
        amp = max(0.0, min(1.0, amp))
        t = self.time
        spin = self.spin

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── 1. Soft Ambient Starlight Glow (Subtle Nebula Core) ───────────────
        glow_r = r * 1.35 * (1.0 + 0.15 * amp)
        g = QRadialGradient(QPointF(cx, cy), glow_r)
        g.setColorAt(0.00, _with_alpha(white, 0.09 + 0.10 * amp))
        g.setColorAt(0.28, _with_alpha(main, 0.06 + 0.08 * amp))
        g.setColorAt(0.65, _with_alpha(main, 0.02))
        g.setColorAt(1.00, _with_alpha(main, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ── 2. Fluid Harmonic Displacement of Points (Audio Reactivity) ───────
        # Subtle organic breathing wave when idle
        idle_wave = 0.024 * np.sin(2.4 * t + 3.2 * self._base_pts[1])

        # Voice-driven spherical harmonic ripple waves
        if amp > 0.005:
            harm1 = 0.16 * np.sin(5.0 * self._azimuth + 4.5 * t) * np.cos(4.0 * self._base_pts[1] - 2.5 * t)
            harm2 = 0.09 * np.sin(8.0 * self._polar + 6.0 * t)
            harm3 = 0.06 * np.cos(3.0 * self._azimuth - 7.0 * t)
            audio_wave = amp * (harm1 + harm2 + harm3)
        else:
            audio_wave = 0.0

        r_factors = 1.0 + idle_wave + audio_wave
        pts = self._base_pts * r_factors

        # ── 3. 3D Rotation Matrix (Yaw + Pitch Precession + Roll) ─────────────
        pitch = 0.12 * math.sin(t * 0.28)
        roll = 0.06 * math.cos(t * 0.21)
        rot = _rz(roll) @ _rx(pitch) @ _ry(spin)
        rot_pts = rot @ pts

        # ── 4. Perspective Camera Projection ──────────────────────────────────
        v_z = rot_pts[2]
        s = _CAM_D / (_CAM_D - v_z)
        X = cx + rot_pts[0] * s * r
        Y = cy - rot_pts[1] * s * r
        Z = v_z

        # Depth sort from back to front
        order = np.argsort(Z)

        # ── 5. Render Particle Point Cloud ────────────────────────────────────
        X_s = X[order]
        Y_s = Y[order]
        Z_s = Z[order]
        sizes = self._pt_sizes[order]
        twinkle = np.sin(t * 3.5 + self._twinkle[order])

        for i in range(self.n_points):
            z_val = float(Z_s[i])
            # Normalized depth: 0.0 (far back) to 1.0 (nearest front)
            depth_k = max(0.0, min(1.0, (z_val + 1.0) * 0.5))

            # Dot size: back points ~0.85px, front points ~2.4px
            sz = (0.85 + 1.40 * depth_k) * float(sizes[i]) * float(s[order[i]])
            if amp > 0.05:
                sz *= (1.0 + 0.12 * amp)

            # Opacity: back points soft (0.18), front points bright (0.95)
            alpha = 0.18 + 0.78 * (depth_k ** 1.35) + 0.06 * float(twinkle[i])
            alpha = max(0.12, min(1.0, alpha))

            # Color: front points are crisp pure white starlight with subtle accent fringe
            if depth_k > 0.65:
                pt_col = _with_alpha(white, alpha)
            elif depth_k > 0.35:
                pt_col = _with_alpha(white if (i % 3 != 0) else main, alpha)
            else:
                pt_col = _with_alpha(main if (i % 2 == 0) else white, alpha * 0.85)

            px = float(X_s[i])
            py = float(Y_s[i])
            p.fillRect(QRectF(px - sz * 0.5, py - sz * 0.5, sz, sz), pt_col)

        # ── 6. Outer Floating Celestial Motes ─────────────────────────────────
        m_rot = _ry(-spin * 0.40) @ self._mote_pts
        m_s = _CAM_D / (_CAM_D - m_rot[2])
        m_X = cx + m_rot[0] * m_s * r
        m_Y = cy - m_rot[1] * m_s * r
        m_Z = m_rot[2]

        for i in range(len(m_Z)):
            d_k = max(0.0, min(1.0, (float(m_Z[i]) + 1.0) * 0.5))
            m_sz = 1.0 + 1.2 * d_k
            m_alpha = 0.20 + 0.55 * d_k
            p.fillRect(
                QRectF(float(m_X[i]) - m_sz * 0.5, float(m_Y[i]) - m_sz * 0.5, m_sz, m_sz),
                _with_alpha(white if i % 2 == 0 else main, m_alpha),
            )

        p.restore()
