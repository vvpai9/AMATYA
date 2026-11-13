# Maha-AMATYA (महामात्य) Private Edition Architecture

## Overview
Maha-AMATYA is the private extension architecture for AMATYA, designed to provide high-specialization laboratories and private domain capabilities without committing confidential personal data, internal hardware topologies, or private scientific code to the public open-source repository.

---

## 1. Directory Layout & Discovery

Maha-AMATYA extensions reside outside the Git tracking tree in the user's standard personal data directory:

- **Linux:** `~/.local/share/maha-amatya/plugins/` (or `$XDG_DATA_HOME/maha-amatya/plugins/`)
- **macOS:** `~/Library/Application Support/maha-amatya/plugins/`
- **Windows:** `%LOCALAPPDATA%/maha-amatya/plugins/`

The AMATYA core discovery engine (`core/plugin_loader.py`) discovers both standard public plugins and private Maha-AMATYA plugins automatically at runtime.

---

## 2. Domain Laboratories

```
Maha-AMATYA
├── Orbit Lab (maha_orbit_lab.py)
│   ├── Keplerian orbital elements calculation
│   ├── Two-body orbital propagation & velocity vectors
│   └── 2-impulse coplanar Hohmann transfer delta-v
├── Analog Lab (maha_analog_lab.py)
│   ├── Cadence Spectre / SPICE log parsing
│   ├── PVT corner sensitivity matrix (TT, FF, SS, FS, SF)
│   └── Feedback amplifier stability analysis (PM, GM, UGBW, damping ratio)
├── Vedic Jyotisha Lab
│   ├── High-precision planetary ephemeris (Swiss Ephemeris integration)
│   ├── D1 through D60 varga divisional charts
│   └── Shadbala, Chara Karakas, and Ashtakavarga matrices
├── Personal Vault
│   ├── Zero-knowledge local credential storage
│   └── Personal document encryption
└── Digital Operations & Hardware Mesh
    ├── Android TV atvremote integration
    └── Local IoT bridge & telemetry
```

---

## 3. Security Boundary & Execution Governance

Every action executed by a Maha-AMATYA module is validated through the centralized gateway (`core/security.py`). Permissions default to `PermissionTier.REMOTE_DEVICE_CONTROL` and can be elevated dynamically based on the module's declared requirements.

