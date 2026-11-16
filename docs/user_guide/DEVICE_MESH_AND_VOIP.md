# Device Mesh, Smart Home & AgentRing VoIP Calling

AMATYA unifies your personal devices into a secure local mesh, providing Android TV automation, mobile notifications, and self-hosted VoIP calling (`core/devices.py`, `core/phone_ring.py`, `actions/phone_ring.py`).

---

## 1. Redmi / Android TV Automation (ADB Integration)

AMATYA connects directly to your Android TV over local Wi-Fi / Ethernet using Android Debug Bridge (ADB):

### Features
- **App Launching:** Launch Netflix, YouTube, Prime Video, Hotstar, Kodi, etc. by name.
- **Playback & Navigation:** Play, pause, directional D-Pad control, Back, Home.
- **Power & Volume:** Turn on/off TV screen, mute, and adjust volume levels.
- **Zero Disturbance Guarantee:** AMATYA will never send test ADB packets or interrupt active TV viewing during background automated testing.

### Voice Commands:
- *"Launch Netflix on the TV"*
- *"Open YouTube on the living room TV"*
- *"Pause TV playback"*
- *"Turn off the TV"*

---

## 2. Mobile Integration (KDE Connect & Ntfy.sh)

- **KDE Connect:** Seamlessly interfaces with paired smartphones over local Wi-Fi:
  - Ring phone (locating misplaced device).
  - Send actionable push notifications.
  - Clipboard sharing and battery level telemetry.
- **Ntfy.sh Push Fallback:** Delivers high-priority push alerts to your phone over encrypted HTTP when outside your home LAN.

### Voice Commands:
- *"Ring my phone"*
- *"Find my phone"*
- *"Send a notification to my phone with the summary"*

---

## 3. AgentRing VoIP Mobile Calling

AMATYA integrates with **AgentRing** (`mutonby/agentring`) to place direct VoIP calls to your mobile device:
- **Zero Carrier Fees:** Uses SIP / WebRTC over local Wi-Fi or self-hosted PBX without Twilio or cellular airtime charges.
- **Autonomous Task Completion Alert:** When a long-running research or compilation task completes, AMATYA rings your phone and reads out the debriefing.
- **Interactive Voice Bridging:** Speak directly into your phone to approve or modify AMATYA's proposed next steps while away from your desk.
