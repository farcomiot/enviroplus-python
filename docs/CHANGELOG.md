# Changelog — Farcom Enviro+ IoT System

All notable changes to the Raspberry Pi script and web dashboard.

---

## [LCD v8] — 2026-02-16
### Added
- Logo screen (lcd_logo_screen): Programmatic Farcom ruedita spiral drawing + FARCOM Industrial text + copyright line
- Health screen (lcd_health_screen): Local IP, External IP (cached), WiFi SSID, CPU temperature (color-coded), RAM gauge with visual bar, Disk usage %, system uptime
- LCD rotation expanded to 14 screens total

### Changed
- Variables list: added logo and health to rotation after info

---

## [LCD v7] — 2026-02-16
### Added
- Info screen (lcd_info_screen): QR code, date/time display, WiFi/MQTT/SSH status dots, version/credits, uptime counter
- QR image cache (generated once, reused on every screen refresh)

### Changed
- Smart decimal formatting: .1f for all analog sensors, .0f for PM sensors
- Variables list: added info to rotation

---

## [LCD v6] — 2026-02-16
### Added
- Boot splash screen (lcd_splash): 4-second display at startup with Farcom branding + QR code
- lcd_bars() shortcode function for color bars + cursor rendering

### Changed
- Removed Farcom ruedita icon from individual sensor screens
- Proximity sensitivity: threshold 1500 to 800, delay 0.5s to 0.2s

### Removed
- generate_farcom_icon() function
- farcom_icon initialization in main loop

---

## [LCD v5] — 2026-02-16
### Added
- PMS5003 throttled reads: serial read every 2 seconds, cached values between reads
- PMS5003 initial read at boot (immediate PM data availability)
- Fallback LCD display when sensor data not yet available
- Farcom ruedita icon generator for top-right corner

### Changed
- SPI speed: 10 MHz to 32 MHz (3.2x faster screen transfer)
- Main loop sleep: 0.5s to 0.15s (~6.7 FPS LCD refresh)
- Half time scale: WIDTH//2 data points, 2px-wide bars
- Color scheme: restored original Pimoroni white background + 0.6 HSV range

---

## [Pi Script v4] — 2026-02-15
### Added
- Noise sensor (ICS-43432 MEMS microphone) — dB SPL measurement
- SQLite 24h rolling storage — local data persistence
- Noise event detection — threshold-based alert recording
- Night watch mode — armed/disarmed noise monitoring
- History publishing — 15-minute retained MQTT messages
- 2-second MQTT publish interval

### Changed
- Sensor count: 8 to 11 (added noise, retained all others)

---

## [Pi Script v3] — 2026-02-14
### Added
- MQTT publisher to HiveMQ public broker
- All 8 environmental sensors (temp, humidity, pressure, light, gas x3, PM x3)
- Pimoroni-style LCD color bars with proximity switching
- Basic command-line arguments (broker, topic, interval)

---

## [Dashboard v4.1] — 2026-02-16
### Added
- Noise threshold dropdown — adjustable 30-130 dB with named presets
- Environmental health alerts — EPA/WHO/OSHA thresholds for PM, temp, humidity, gas
- Location map widget — OpenStreetMap embed (Carolco, Monterrey)
- Copyright footer
- Alert badges in header with active count
- localStorage persistence for noise threshold

### Changed
- Security Events renamed to Environmental and Security Alerts (unified log)
- Event table expanded: Time, Source, Level, Value, Detail columns

---

## [Dashboard v4] — 2026-02-15
### Added
- 11 live gauge cards (all sensors)
- 24-hour SQLite history charts
- Noise event log with timestamps
- Night watch arm/disarm toggle
- Day/Night auto-theme based on time
- Connection quality indicator
- JetBrains Mono typography

---

2024-2026 Ing. Aaron Farias — Farcom Industrial. All Rights Reserved.
