# 🌿 Farcom Industrial — Enviro+ IoT Monitoring System

> **Real-time environmental monitoring** powered by Raspberry Pi + Pimoroni Enviro+ sensor hat,
> publishing via MQTT to a live web dashboard.

[![Dashboard](https://img.shields.io/badge/Live%20Dashboard-farcomindustrial.com%2Fenviropi-blue)](https://farcomindustrial.com/enviropi)
[![License](https://img.shields.io/badge/License-All%20Rights%20Reserved-red)](#license)
[![Python](https://img.shields.io/badge/Python-3.9+-green)](https://python.org)

---

## 📐 Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Raspberry Pi 4 (Raspbian Bookworm)                                  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  farcom-mqtt-enviro.py  (1060 lines, Python 3)                 │ │
│  │  ├── 11 Sensor Channels (BME280, LTR559, MICS-6814, PMS5003)  │ │
│  │  ├── ST7735 LCD: 14 screens (sensor bars, info, logo, health)  │ │
│  │  ├── MQTT Publisher (2s interval, HiveMQ broker)               │ │
│  │  ├── SQLite 24h rolling storage                                │ │
│  │  └── Noise event detection + night watch mode                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│         │ MQTT (TCP 1883)                                            │
└─────────┼────────────────────────────────────────────────────────────┘
          ▼
┌──────────────────────┐     ┌──────────────────────────────────────┐
│  HiveMQ Public Broker │────▶│  WordPress Dashboard (v4.1)          │
│  broker.hivemq.com    │     │  farcomindustrial.com/enviropi       │
│  Topic: farcom/enviro │     │  ├── 11 live gauge cards             │
└──────────────────────┘     │  ├── 24h history charts              │
                              │  ├── Environmental health alerts     │
                              │  ├── Noise event log + night watch   │
                              │  ├── Location map (OSM)              │
                              │  └── Day/Night auto theme            │
                              └──────────────────────────────────────┘
```

---

## 🔧 Hardware

| Component | Model | Interface | Notes |
|-----------|-------|-----------|-------|
| SBC | Raspberry Pi 4 Model B | — | Raspbian Bookworm |
| Sensor Hat | Pimoroni Enviro+ | I2C + SPI + UART | All-in-one environmental |
| Temp/Humidity/Pressure | BME280 | I2C | ±1°C, ±3% RH, ±1 hPa |
| Light/Proximity | LTR559 | I2C | 0.01–64k Lux, proximity for LCD switching |
| Gas (NO₂, CO, NH₃) | MICS-6814 | I2C (ADC) | Resistance-based, kΩ readings |
| Particulate Matter | PMS5003 | UART 9600 baud | PM1.0, PM2.5, PM10 (µg/m³) |
| Noise (SPL) | ICS-43432 MEMS Mic | I2S | ±1 dB, 50 Hz–80 kHz |
| LCD Display | ST7735 0.96" | SPI @ 32 MHz | 160×80 RGB, 14-screen rotation |
| LCD Backlight | — | GPIO 12 | PWM controllable |
| PMS5003 Enable | — | GPIO 22 | High = sensor on |

---

## 📡 Sensor Channels (11 total)

| # | Channel | Unit | Source | Refresh |
|---|---------|------|--------|---------|
| 1 | `noise` | dB SPL | ICS-43432 | ~5 Hz |
| 2 | `temperature` | °C | BME280 | Every loop (~6.7 Hz) |
| 3 | `pressure` | hPa | BME280 | Every loop |
| 4 | `humidity` | % RH | BME280 | Every loop |
| 5 | `light` | Lux | LTR559 | Every loop |
| 6 | `oxidised` | kΩ | MICS-6814 | Every loop |
| 7 | `reduced` | kΩ | MICS-6814 | Every loop |
| 8 | `nh3` | kΩ | MICS-6814 | Every loop |
| 9 | `pm1` | µg/m³ | PMS5003 | Every 2s (throttled) |
| 10 | `pm25` | µg/m³ | PMS5003 | Every 2s (throttled) |
| 11 | `pm10` | µg/m³ | PMS5003 | Every 2s (throttled) |

---

## 📺 LCD Screen Rotation (14 modes)

Cycle through screens by waving hand over the proximity sensor (LTR559).

| # | Mode | Description |
|---|------|-------------|
| 1 | `noise` | Noise level + color bars |
| 2 | `temperature` | Temperature + color bars |
| 3 | `pressure` | Barometric pressure + color bars |
| 4 | `humidity` | Relative humidity + color bars |
| 5 | `light` | Ambient light + color bars |
| 6 | `oxidised` | NO₂ resistance + color bars |
| 7 | `reduced` | CO/VOC resistance + color bars |
| 8 | `nh3` | NH₃ resistance + color bars |
| 9 | `pm1` | PM1.0 particles + color bars |
| 10 | `pm25` | PM2.5 particles + color bars |
| 11 | `pm10` | PM10 particles + color bars |
| 12 | `info` | QR code, date/time, WiFi/MQTT/SSH status |
| 13 | `logo` | Farcom Industrial brand + copyright |
| 14 | `health` | System health: IPs, CPU temp, RAM, Disk, WiFi |

**LCD Enhancements:**
- Half time scale (2px-wide bars) for vivid measurement changes
- Smart decimal formatting: `.1f` for analog sensors, `.0f` for PM (integer resolution)
- Boot splash screen (4 seconds) with QR code → farcomindustrial.com/enviropi
- Proximity threshold: 800, switching delay: 0.2s

---

## 🌐 MQTT Protocol

| Parameter | Value |
|-----------|-------|
| Broker | `broker.hivemq.com` |
| Port | `1883` (TCP) |
| Topic | `farcom/enviro` |
| Publish interval | 2 seconds |
| QoS | 1 |
| Payload | JSON with all 11 sensor values + metadata |
| History topic | `farcom/enviro/history` (15-min retained) |
| Auth | See `CREDENTIALS.md` (🔒 redacted) |

**MQTT JSON payload example:**
```json
{
  "temperature": 28.4,
  "humidity": 52.1,
  "pressure": 1013.2,
  "light": 340.5,
  "oxidised": 12.8,
  "reduced": 45.2,
  "nh3": 320.1,
  "pm1": 5,
  "pm25": 8,
  "pm10": 9,
  "noise": 42.3,
  "mqtt_connected": true,
  "uptime_start": 1739700000
}
```

---

## 🚀 Quick Start

### Prerequisites
```bash
# On Raspberry Pi (Raspbian Bookworm)
pip3 install --break-system-packages paho-mqtt qrcode[pil]
```

### Run
```bash
python3 farcom-mqtt-enviro.py \
  --broker broker.hivemq.com \
  --topic farcom/enviro \
  --interval 2
```

### Service (systemd)
```bash
sudo systemctl status farcom-enviro.service
sudo systemctl restart farcom-enviro.service
sudo journalctl -u farcom-enviro -f   # Live logs
```

---

## 📂 Repository Structure

```
enviroplus-python/
├── examples/
│   ├── farcom-mqtt-enviro.py          # Main production script (v4 + LCD v8)
│   ├── farcom-mqtt-enviro.py.bak-v4   # Pre-LCD-enhancement backup
│   ├── farcom-mqtt-enviro-v4.py       # Version 4 snapshot
│   └── farcom-mqtt-enviro-v3-backup.py# Version 3 archive
├── docs/
│   ├── SSH-DIAGNOSTICS.md             # Serial sensor diagnostic commands
│   ├── CHANGELOG.md                   # Version history
│   ├── CREDENTIALS.md                 # 🔒 Credential references (redacted)
│   └── README-FARCOM.md              # This file
└── README.md                          # Upstream Pimoroni README
```

---

## 🔐 Credentials

All sensitive credentials are **redacted** in this repository. References:

| Service | Reference Key | Location |
|---------|---------------|----------|
| GoDaddy (hosting) | `godaddyPw` | WordPress admin (farcomindustrial.com) |
| HiveMQ (MQTT broker) | `HiveEmail`, `HivePw` | MQTT auth config |

> ⚠️ **Never commit credentials.** See `docs/CREDENTIALS.md` for the credential reference map.

---

## 📋 Version History

| Version | Date | Changes |
|---------|------|---------|
| v4 + LCD v8 | 2026-02-16 | 14-screen LCD, health monitor, logo, info QR, system health |
| v4 + LCD v7 | 2026-02-16 | Info screen with QR code, WiFi/MQTT status, decimal formatting |
| v4 + LCD v6 | 2026-02-16 | Splash screen, proximity tuning, lcd_bars shortcode |
| v4 + LCD v5 | 2026-02-16 | SPI 32MHz, half time scale, PMS5003 throttled reads |
| v4 | 2026-02-15 | Noise sensor, SQLite storage, night watch, history |
| v3 | 2026-02-14 | MQTT publisher, 11 sensors, basic LCD |
| Dashboard v4.1 | 2026-02-16 | Noise threshold, health alerts, location map, copyright |
| Dashboard v4 | 2026-02-15 | 11 gauges, 24h charts, noise events, day/night theme |

---

## 📍 Deployment Location

**Carolco, Monterrey, Nuevo León, Mexico**
- Address: Flor Dalia, Fraccionamiento Carolco
- Coordinates: 25.644°N, 100.236°W
- Dashboard: [farcomindustrial.com/enviropi](https://farcomindustrial.com/enviropi)

---

## 📜 License

**© 2024–2026 Ing. Aaron Farias — Farcom Industrial. All Rights Reserved.**

This project is proprietary software. Unauthorized copying, distribution, or modification is prohibited.

---

*Powered by Raspberry Pi, Pimoroni Enviro+, and smart AI engineering.*
