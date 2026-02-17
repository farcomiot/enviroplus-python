#!/usr/bin/env python3
"""
farcom-mqtt-enviro.py — Farcom Industrial Enviro+ IoT Monitoring System
Raspberry Pi + Pimoroni Enviro+ HAT | 11 Sensors | 14 LCD Screens | MQTT | SQLite

Publishes environmental data every 2 seconds to HiveMQ public broker.
Cycles through 14 LCD screens via proximity sensor (wave hand to switch).
Stores 24-hour rolling history in SQLite. Detects noise events with night watch mode.

Version:   4 + LCD v8
Author:    Ing. Aaron Farias — Farcom Industrial
Copyright: (c) 2024-2026 All Rights Reserved
Dashboard: https://farcomindustrial.com/enviropi
Repository: https://github.com/farcomiot/enviroplus-python
"""
# =============================================================================
# SECTION 2: IMPORTS
# =============================================================================
import colorsys
import json
import logging
import math
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import ST7735
from bme280 import BME280
from enviroplus import gas
from enviroplus.noise import Noise
from fonts.ttf import RobotoMedium as UserFont
from PIL import Image, ImageDraw, ImageFont
from pms5003 import PMS5003
from pms5003 import ReadTimeoutError as pmsReadTimeoutError
from pms5003 import SerialTimeoutError as pmsSerialTimeoutError
try:
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559
try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus
try:
    import qrcode
except ImportError:
    qrcode = None
# =============================================================================
# SECTION 3: LOGGING
# =============================================================================
logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("farcom")
# =============================================================================
# SECTION 4: CONSTANTS
# =============================================================================
# MQTT
BROKER           = "broker.hivemq.com"
PORT             = 1883
TOPIC            = "farcom/enviro"
TOPIC_HISTORY    = "farcom/enviro/history"
PUBLISH_INTERVAL = 2       # seconds between MQTT publishes
HISTORY_INTERVAL = 900     # 15 minutes between history publishes
MQTT_QOS         = 1
# LCD
SPI_SPEED_HZ     = 32_000_000
ROTATION         = 270
LCD_WIDTH        = 160
LCD_HEIGHT       = 80
TOP_POS          = 25      # y-offset where bars start (label text above)
NUM_BARS         = LCD_WIDTH // 2  # 80 samples, 2px-wide each
PROX_THRESHOLD   = 800
PROX_DELAY       = 0.2     # debounce seconds
LOOP_SLEEP       = 0.15    # ~6.7 FPS
# Sensor
TEMP_COMP_FACTOR = 2.25
CPU_TEMP_SAMPLES = 5
# SQLite
DB_PATH          = "/home/enviropi/enviroplus-python/examples/enviro_data.db"
DB_RETENTION_H   = 24
# Noise
NOISE_THRESHOLD  = 65.0    # dB SPL
NIGHT_START      = 22      # 10 PM
NIGHT_END        = 7       # 7 AM
NIGHT_REDUCTION  = 10.0    # dB lower threshold at night
# Branding
DASHBOARD_URL    = "https://farcomindustrial.com/enviropi"
SPLASH_SECONDS   = 4
# LCD modes
NUM_SENSOR_MODES = 11
MODE_INFO        = 11
MODE_LOGO        = 12
MODE_HEALTH      = 13
NUM_MODES        = 14
def get_serial_number():
    """Read Pi serial from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "unknown"
SERIAL       = get_serial_number()
DEVICE_ID    = "raspi-" + SERIAL
UPTIME_START = int(time.time())
# =============================================================================
# SECTION 5: HARDWARE INITIALIZATION
# =============================================================================
log.info("Initializing hardware...")
# I2C bus
bus = SMBus(1)
# BME280 (temperature, pressure, humidity)
bme280 = BME280(i2c_dev=bus)
# Noise sensor (ICS-43432 I2S MEMS microphone)
noise_sensor = Noise()
# PMS5003 particulate matter sensor (UART)
pms5003 = PMS5003()
time.sleep(1.0)  # warm-up
pm1_cached  = 0.0
pm25_cached = 0.0
pm10_cached = 0.0
last_pms_read = 0.0
try:
    _pm = pms5003.read()
    pm1_cached  = float(_pm.pm_ug_per_m3(1.0))
    pm25_cached = float(_pm.pm_ug_per_m3(2.5))
    pm10_cached = float(_pm.pm_ug_per_m3(10))
    last_pms_read = time.time()
    log.info("PMS5003 initial read OK: PM2.5=%s", pm25_cached)
except Exception as e:
    log.warning("PMS5003 initial read failed: %s", e)
# ST7735 LCD display
disp = ST7735.ST7735(
    port=0, cs=1, dc=9, backlight=12,
    rotation=ROTATION, spi_speed_hz=SPI_SPEED_HZ,
)
disp.begin()
# PIL canvas (shared across all LCD functions — never re-allocated)
img  = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
# Fonts
font_large = ImageFont.truetype(UserFont, 20)
font_med   = ImageFont.truetype(UserFont, 12)
font_small = ImageFont.truetype(UserFont, 10)
font_tiny  = ImageFont.truetype(UserFont, 8)
log.info("Hardware initialization complete")
# =============================================================================
# SECTION 6: STATE VARIABLES
# =============================================================================
# LCD mode
lcd_mode        = 0
lcd_last_switch = 0.0
# Sensor variable names (ORDER = LCD mode index 0-10)
variables = [
    "noise", "temperature", "pressure", "humidity", "light",
    "oxidised", "reduced", "nh3", "pm1", "pm25", "pm10",
]
units = ["dB", "C", "hPa", "%", "Lux", "kO", "kO", "kO", "ug/m3", "ug/m3", "ug/m3"]
# Set of PM variables (use integer display format)
pm_vars = {"pm1", "pm25", "pm10"}
# Safety limit thresholds: [dangerously_low, low, high, dangerously_high]
limits = [
    [40, 55, 70, 85],            # noise dB
    [4, 18, 28, 35],             # temperature C
    [250, 650, 1013.25, 1015],   # pressure hPa
    [20, 30, 60, 70],            # humidity %
    [-1, -1, 30000, 100000],     # light Lux
    [-1, -1, 40, 50],            # oxidised kOhm
    [-1, -1, 450, 550],          # reduced kOhm
    [-1, -1, 200, 300],          # nh3 kOhm
    [-1, -1, 50, 100],           # pm1
    [-1, -1, 50, 100],           # pm25
    [-1, -1, 50, 100],           # pm10
]
# 5-color palette for safety thresholds
palette = [
    (0, 0, 255),     # Dangerously Low
    (0, 255, 255),   # Low
    (0, 255, 0),     # Normal
    (255, 255, 0),   # High
    (255, 0, 0),     # Dangerously High
]
# Rolling history buffers (NUM_BARS=80 samples per variable)
values = {v: [1.0] * NUM_BARS for v in variables}
# CPU temperature rolling average
cpu_temps = [25.0] * CPU_TEMP_SAMPLES
# MQTT connection flag (updated by callbacks)
mqtt_connected = False
# Noise events log (in-memory, last 100)
noise_events = []
# QR code image cache (generated once on first use)
qr_image_cache = None
# External IP cache (updated by background thread)
ext_ip_cache = "..."
# History publish timer
last_history_publish = 0.0
# WiFi SSID cache (updated periodically)
wifi_ssid_cache = "..."
wifi_ssid_last  = 0.0
# =============================================================================
# SECTION 7: HELPER / UTILITY FUNCTIONS
# =============================================================================
def get_cpu_temperature():
    """Read CPU temperature via sysfs (no subprocess, fast)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0
def get_local_ip():
    """Get local IP via UDP socket trick (no shell commands)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "?.?.?.?"
def get_wifi_ssid():
    """Get current WiFi SSID via nmcli (Bookworm NetworkManager)."""
    global wifi_ssid_cache, wifi_ssid_last
    now = time.time()
    if now - wifi_ssid_last < 30:
        return wifi_ssid_cache
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                wifi_ssid_cache = line.split(":", 1)[1].strip()
                wifi_ssid_last = now
                return wifi_ssid_cache
    except Exception:
        pass
    wifi_ssid_cache = "N/A"
    wifi_ssid_last = now
    return wifi_ssid_cache
def get_external_ip():
    """Fetch external IP from ipify (blocking — use in background thread)."""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "5", "https://api.ipify.org"],
            capture_output=True, text=True, timeout=8,
        )
        return result.stdout.strip() if result.stdout.strip() else "?.?.?.?"
    except Exception:
        return "?.?.?.?"
def _ext_ip_thread_fn():
    """Background daemon thread: refresh external IP every 10 minutes."""
    global ext_ip_cache
    while True:
        ext_ip_cache = get_external_ip()
        time.sleep(600)
def amp_to_db(amp):
    """Convert ICS-43432 noise amplitude to approximate dB SPL."""
    if amp <= 0:
        return 0.0
    return max(0.0, 20.0 * math.log10(amp * 64.0 + 1.0))
def is_night_watch():
    """Return True if current hour is within night watch window."""
    hour = datetime.now().hour
    return hour >= NIGHT_START or hour < NIGHT_END
def format_uptime(start_ts):
    """Return human-readable uptime from Unix timestamp."""
    secs = int(time.time() - start_ts)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return "{}h {}m {}s".format(h, m, s)
def check_ssh_listening():
    """Return True if SSH port 22 is open locally."""
    try:
        s = socket.socket()
        s.settimeout(0.3)
        s.connect(("127.0.0.1", 22))
        s.close()
        return True
    except Exception:
        return False
def get_ram_info():
    """Return (used_mb, total_mb) from /proc/meminfo."""
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                mem[parts[0].rstrip(":")] = int(parts[1])
        total = mem.get("MemTotal", 1)
        avail = mem.get("MemAvailable", 0)
        used = total - avail
        return (used // 1024, total // 1024)
    except Exception:
        return (0, 1)
def get_disk_percent():
    """Return disk usage percentage for /."""
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        if total == 0:
            return 0
        return int(100 * used / total)
    except Exception:
        return 0
# =============================================================================
# SECTION 8: SQLITE FUNCTIONS
# =============================================================================
def db_init():
    """Create sensor_data table if it does not exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                noise       REAL,
                temperature REAL,
                pressure    REAL,
                humidity    REAL,
                light       REAL,
                oxidised    REAL,
                reduced     REAL,
                nh3         REAL,
                pm1         REAL,
                pm25        REAL,
                pm10        REAL
            )
        """)
        conn.commit()
        conn.close()
        log.info("SQLite initialized: %s", DB_PATH)
    except Exception as e:
        log.error("SQLite init error: %s", e)
def db_insert(reading):
    """Insert one sensor reading and prune rows older than 24 hours."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO sensor_data
               (timestamp, noise, temperature, pressure, humidity,
                light, oxidised, reduced, nh3, pm1, pm25, pm10)
               VALUES (datetime('now','localtime'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reading.get("noise"),       reading.get("temperature"),
                reading.get("pressure"),    reading.get("humidity"),
                reading.get("light"),       reading.get("oxidised"),
                reading.get("reduced"),     reading.get("nh3"),
                reading.get("pm1"),         reading.get("pm25"),
                reading.get("pm10"),
            ),
        )
        conn.execute(
            "DELETE FROM sensor_data WHERE timestamp < datetime('now','localtime',?)",
            ("-{} hours".format(DB_RETENTION_H),),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("SQLite insert error: %s", e)
def db_row_count():
    """Return current number of rows in sensor_data."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT COUNT(*) FROM sensor_data")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
# =============================================================================
# SECTION 9: MQTT FUNCTIONS
# =============================================================================
def on_connect(client, userdata, flags, reason_code, properties):
    """paho-mqtt v2 callback: connection established."""
    global mqtt_connected
    if reason_code == 0:
        mqtt_connected = True
        log.info("MQTT connected to %s", BROKER)
    else:
        mqtt_connected = False
        log.warning("MQTT connect failed: reason=%s", reason_code)
def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    """paho-mqtt v2 callback: disconnected."""
    global mqtt_connected
    mqtt_connected = False
    log.warning("MQTT disconnected: reason=%s", reason_code)
def on_publish(client, userdata, mid, reason_code, properties):
    """paho-mqtt v2 callback: message published."""
    pass  # silent — logged elsewhere
def mqtt_init():
    """Create MQTT client with v2 API, connect, start network loop."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=DEVICE_ID,
    )
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish    = on_publish
    try:
        client.connect(BROKER, PORT, keepalive=60)
    except Exception as e:
        log.error("MQTT initial connect failed: %s", e)
    client.loop_start()
    return client
def mqtt_publish_data(client, payload_dict):
    """Publish sensor JSON to farcom/enviro at QoS 1."""
    try:
        client.publish(TOPIC, json.dumps(payload_dict), qos=MQTT_QOS)
    except Exception as e:
        log.warning("MQTT publish error: %s", e)
def mqtt_publish_history(client, payload_dict):
    """Publish retained snapshot to farcom/enviro/history."""
    try:
        history = {
            "timestamp": datetime.now().isoformat(),
            "snapshot": payload_dict,
            "rows": db_row_count(),
        }
        client.publish(TOPIC_HISTORY, json.dumps(history), qos=MQTT_QOS, retain=True)
        log.info("History published (%d rows in DB)", history["rows"])
    except Exception as e:
        log.warning("MQTT history publish error: %s", e)
# =============================================================================
# SECTION 10: SENSOR READING FUNCTIONS
# =============================================================================
def read_temperature():
    """BME280 temperature with CPU heat compensation (5-sample rolling avg)."""
    global cpu_temps
    cpu_t = get_cpu_temperature()
    cpu_temps = cpu_temps[1:] + [cpu_t]
    avg_cpu = sum(cpu_temps) / len(cpu_temps)
    raw = bme280.get_temperature()
    return raw - ((avg_cpu - raw) / TEMP_COMP_FACTOR)
def read_pressure():
    """BME280 barometric pressure in hPa."""
    return bme280.get_pressure()
def read_humidity():
    """BME280 relative humidity %."""
    return bme280.get_humidity()
def read_light():
    """LTR559 ambient light in Lux (blocked when proximity sensor triggered)."""
    prox = ltr559.get_proximity()
    if prox < 10:
        return ltr559.get_lux()
    return 1.0
def read_gas():
    """MICS-6814 gas resistances in kOhm: (oxidised, reduced, nh3)."""
    data = gas.read_all()
    return (
        data.oxidising / 1000.0,
        data.reducing  / 1000.0,
        data.nh3       / 1000.0,
    )
def read_pms5003():
    """PMS5003 particulate matter — throttled reads every 2s, cached between."""
    global pm1_cached, pm25_cached, pm10_cached, last_pms_read
    now = time.time()
    if now - last_pms_read < PUBLISH_INTERVAL:
        return pm1_cached, pm25_cached, pm10_cached
    try:
        pm = pms5003.read()
        pm1_cached  = float(pm.pm_ug_per_m3(1.0))
        pm25_cached = float(pm.pm_ug_per_m3(2.5))
        pm10_cached = float(pm.pm_ug_per_m3(10))
        last_pms_read = now
    except (pmsReadTimeoutError, pmsSerialTimeoutError) as e:
        log.warning("PMS5003 read error: %s", e)
        try:
            pms5003.reset()
        except Exception:
            pass
    return pm1_cached, pm25_cached, pm10_cached
def read_noise():
    """ICS-43432 noise level in approximate dB SPL."""
    try:
        _low, _mid, _high, amp = noise_sensor.get_noise_profile()
        return amp_to_db(amp)
    except Exception as e:
        log.warning("Noise read error: %s", e)
        return 0.0
def read_all_sensors():
    """Read all 11 channels. Returns dict matching dashboard MQTT JSON schema."""
    temp = read_temperature()
    pres = read_pressure()
    humi = read_humidity()
    lux  = read_light()
    ox, red, nh3 = read_gas()
    p1, p25, p10 = read_pms5003()
    db = read_noise()
    return {
        "noise":       round(db, 1),
        "temperature": round(temp, 1),
        "pressure":    round(pres, 1),
        "humidity":    round(humi, 1),
        "light":       round(lux, 1),
        "oxidised":    round(ox, 1),
        "reduced":     round(red, 1),
        "nh3":         round(nh3, 1),
        "pm1":         int(p1),
        "pm25":        int(p25),
        "pm10":        int(p10),
    }
# =============================================================================
# SECTION 11: NOISE EVENT DETECTION
# =============================================================================
def check_noise_event(db_value):
    """Check if noise exceeds threshold; lower threshold during night watch."""
    global noise_events
    threshold = NOISE_THRESHOLD
    if is_night_watch():
        threshold = NOISE_THRESHOLD - NIGHT_REDUCTION
    if db_value < threshold:
        return None
    event = {
        "timestamp": datetime.now().isoformat(),
        "db": round(db_value, 1),
        "type": "night_watch" if is_night_watch() else "daytime",
    }
    noise_events.append(event)
    if len(noise_events) > 100:
        noise_events = noise_events[-100:]
    log.info("NOISE EVENT: %.1f dB [%s]", db_value, event["type"])
    return event
# =============================================================================
# SECTION 12: LCD DISPLAY FUNCTIONS
# =============================================================================
def lcd_generate_qr():
    """Generate QR code image once and cache it. Returns PIL Image or None."""
    global qr_image_cache
    if qr_image_cache is not None:
        return qr_image_cache
    if qrcode is None:
        return None
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.ERROR_CORRECT_L,
        box_size=2,
        border=1,
    )
    qr.add_data(DASHBOARD_URL)
    qr.make(fit=True)
    qr_image_cache = qr.make_image(
        fill_color="white", back_color="black"
    ).convert("RGB")
    return qr_image_cache
# --- Modes 0-10: Sensor bar graph with HSV color gradient ---
def lcd_bars(variable, data, unit):
    """
    Rolling history bar graph with HSV color gradient.
    2px-wide bars (80 samples = full 160px width).
    White background, black label text, black cursor line.
    """
    # Update rolling buffer
    values[variable] = values[variable][1:] + [data]
    buf = values[variable]
    vmin = min(buf)
    vmax = max(buf)
    spread = vmax - vmin + 1
    colours = [(v - vmin + 1) / spread for v in buf]
    # Format message
    if variable in pm_vars:
        message = "{}: {:.0f} {}".format(variable[:4], data, unit)
    else:
        message = "{}: {:.1f} {}".format(variable[:4], data, unit)
    # White background
    draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (255, 255, 255))
    # Draw 2px-wide HSV color bars
    bar_height = LCD_HEIGHT - TOP_POS
    for i in range(len(colours)):
        hue = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
        x0 = i * 2
        x1 = x0 + 2
        draw.rectangle((x0, TOP_POS, x1, LCD_HEIGHT), (r, g, b))
        # Black cursor line (value position)
        line_y = LCD_HEIGHT - (TOP_POS + (colours[i] * bar_height)) + TOP_POS
        draw.rectangle((x0, line_y, x1, line_y + 1), (0, 0, 0))
    # Label text at top
    draw.text((0, 0), message, font=font_large, fill=(0, 0, 0))
    disp.display(img)
def lcd_sensor_screen(mode_idx, value):
    """Render sensor bar screen for modes 0-10."""
    lcd_bars(variables[mode_idx], value, units[mode_idx])
# --- Mode 11: Info screen (QR + date/time + WiFi/MQTT/SSH) ---
def lcd_info_screen():
    """QR code on left, date/time/status on right."""
    draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
    # QR code (left side, 80x80)
    qr_img = lcd_generate_qr()
    if qr_img is not None:
        qr_resized = qr_img.resize((LCD_HEIGHT, LCD_HEIGHT))
        img.paste(qr_resized, (0, 0))
    # Right panel
    x = 84
    now = datetime.now()
    draw.text((x, 0),  now.strftime("%d/%m/%y"), font=font_small, fill=(255, 255, 0))
    draw.text((x, 11), now.strftime("%H:%M:%S"), font=font_small, fill=(255, 255, 255))
    # Status indicators
    wifi_ok = get_local_ip() != "?.?.?.?"
    mqtt_ok = mqtt_connected
    ssh_ok  = check_ssh_listening()
    y = 25
    for label, ok in [("WiFi", wifi_ok), ("MQTT", mqtt_ok), ("SSH", ssh_ok)]:
        colour = (0, 255, 0) if ok else (255, 0, 0)
        # Status dot
        draw.rectangle((x, y, x + 6, y + 6), colour)
        draw.text((x + 9, y - 1), label, font=font_small, fill=(200, 200, 200))
        y += 12
    # Uptime and version
    draw.text((x, 61), format_uptime(UPTIME_START), font=font_tiny, fill=(150, 150, 150))
    draw.text((x, 71), "v4+LCD v8", font=font_tiny, fill=(100, 100, 100))
    disp.display(img)
# --- Mode 12: Logo screen (Farcom Industrial brand) ---
def lcd_logo_screen():
    """Farcom Industrial branding with gear icon."""
    draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (10, 10, 20))
    # Gear icon (top-right)
    cx, cy = 140, 22
    for angle_deg in range(0, 360, 45):
        a = math.radians(angle_deg)
        x1 = cx + int(8 * math.cos(a))
        y1 = cy + int(8 * math.sin(a))
        x2 = cx + int(16 * math.cos(a))
        y2 = cy + int(16 * math.sin(a))
        draw.line((x1, y1, x2, y2), fill=(0, 200, 255), width=2)
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=(0, 200, 255))
    # Brand text
    draw.text((4, 2),  "FARCOM",      font=font_large, fill=(0, 200, 255))
    draw.text((4, 28), "Industrial",  font=font_large, fill=(255, 255, 255))
    draw.text((4, 52), "Enviro+ Monitor", font=font_small, fill=(150, 150, 150))
    draw.text((4, 64), "farcomindustrial.com", font=font_tiny, fill=(100, 100, 100))
    disp.display(img)
# --- Mode 13: Health screen (system stats) ---
def lcd_health_screen():
    """System health: IPs, WiFi, CPU temp, RAM, Disk, uptime."""
    draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
    local_ip = get_local_ip()
    cpu_t = get_cpu_temperature()
    # CPU temp color coding
    if cpu_t < 60:
        cpu_col = (0, 255, 0)
    elif cpu_t < 75:
        cpu_col = (255, 165, 0)
    else:
        cpu_col = (255, 0, 0)
    ram_used, ram_total = get_ram_info()
    disk_pct = get_disk_percent()
    ssid = get_wifi_ssid()
    y = 1
    draw.text((0, y), "LAN: {}".format(local_ip), font=font_tiny, fill=(0, 200, 255))
    y += 9
    draw.text((0, y), "WAN: {}".format(ext_ip_cache), font=font_tiny, fill=(150, 150, 255))
    y += 9
    draw.text((0, y), "WiFi: {}".format(ssid[:14]), font=font_tiny, fill=(100, 200, 100))
    y += 9
    draw.text((0, y), "CPU: {:.1f}C".format(cpu_t), font=font_tiny, fill=cpu_col)
    y += 9
    # RAM bar
    ram_pct = ram_used / max(ram_total, 1)
    draw.text((0, y), "RAM {}/{}MB".format(ram_used, ram_total), font=font_tiny, fill=(200, 200, 200))
    y += 8
    bar_w = int(ram_pct * 100)
    draw.rectangle((0, y, max(bar_w, 1), y + 4), (0, 200, 0))
    draw.rectangle((bar_w, y, 100, y + 4), (60, 60, 60))
    y += 7
    draw.text((0, y), "Disk: {}%".format(disk_pct), font=font_tiny, fill=(200, 200, 100))
    y += 9
    draw.text((0, y), "Up: {}".format(format_uptime(UPTIME_START)), font=font_tiny, fill=(150, 150, 150))
    disp.display(img)
# --- Boot splash (shown once at startup) ---
def lcd_splash():
    """4-second boot splash: QR code + Farcom branding."""
    draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (10, 10, 20))
    # QR code left side
    qr_img = lcd_generate_qr()
    if qr_img is not None:
        qr_resized = qr_img.resize((LCD_HEIGHT, LCD_HEIGHT))
        img.paste(qr_resized, (0, 0))
    # Brand text right side
    x = 84
    draw.text((x, 4),  "FARCOM",      font=font_small, fill=(0, 200, 255))
    draw.text((x, 16), "Industrial",  font=font_small, fill=(255, 255, 255))
    draw.text((x, 30), "Enviro+",     font=font_small, fill=(200, 200, 200))
    draw.text((x, 42), "Monitor",     font=font_small, fill=(200, 200, 200))
    draw.text((x, 56), "Starting...", font=font_tiny, fill=(100, 200, 100))
    draw.text((x, 66), "v4+LCD v8",   font=font_tiny, fill=(80, 80, 80))
    disp.display(img)
    log.info("Boot splash displayed for %ds", SPLASH_SECONDS)
    time.sleep(SPLASH_SECONDS)
# =============================================================================
# SECTION 13: LCD DISPATCH
# =============================================================================
def lcd_update(mode, sensor_data):
    """Route to the correct LCD screen function for the current mode."""
    try:
        if 0 <= mode < NUM_SENSOR_MODES:
            var = variables[mode]
            lcd_sensor_screen(mode, sensor_data.get(var, 0))
        elif mode == MODE_INFO:
            lcd_info_screen()
        elif mode == MODE_LOGO:
            lcd_logo_screen()
        elif mode == MODE_HEALTH:
            lcd_health_screen()
    except Exception as e:
        log.warning("LCD update error (mode %d): %s", mode, e)
# =============================================================================
# SECTION 14: MAIN LOOP
# =============================================================================
def main():
    """Entry point: init systems, run sensor/LCD/MQTT loop."""
    global lcd_mode, lcd_last_switch, last_history_publish
    global mqtt_connected, ext_ip_cache
    log.info("=" * 60)
    log.info("farcom-mqtt-enviro.py starting")
    log.info("Device: %s", DEVICE_ID)
    log.info("Broker: %s:%d  Topic: %s", BROKER, PORT, TOPIC)
    log.info("=" * 60)
    # 1. SQLite init
    db_init()
    # 2. MQTT init
    mqtt_client = mqtt_init()
    # 3. Boot splash (4 seconds)
    lcd_splash()
    # 4. External IP — fetch once (blocking), then background thread
    log.info("Fetching external IP...")
    ext_ip_cache = get_external_ip()
    log.info("External IP: %s", ext_ip_cache)
    ip_thread = threading.Thread(target=_ext_ip_thread_fn, daemon=True)
    ip_thread.start()
    # 5. Main loop timing
    last_publish = 0.0
    loop_count   = 0
    log.info("Entering main loop. Ctrl+C to exit.")
    try:
        while True:
            loop_start = time.time()
            # --- Proximity check (LCD mode switching) ---
            try:
                prox = ltr559.get_proximity()
            except Exception:
                prox = 0
            if prox > PROX_THRESHOLD:
                if (loop_start - lcd_last_switch) > PROX_DELAY:
                    lcd_mode = (lcd_mode + 1) % NUM_MODES
                    lcd_last_switch = loop_start
                    if lcd_mode < NUM_SENSOR_MODES:
                        mode_name = variables[lcd_mode]
                    else:
                        mode_name = ["info", "logo", "health"][lcd_mode - NUM_SENSOR_MODES]
                    log.info("LCD mode -> %d (%s)", lcd_mode, mode_name)
            # --- Read all sensors ---
            try:
                sensor_data = read_all_sensors()
            except Exception as e:
                log.error("Sensor read error: %s", e)
                time.sleep(LOOP_SLEEP)
                continue
            # --- LCD update (every loop for smooth display) ---
            lcd_update(lcd_mode, sensor_data)
            # --- Noise event detection ---
            check_noise_event(sensor_data.get("noise", 0))
            # --- MQTT publish + SQLite insert (every PUBLISH_INTERVAL) ---
            if loop_start - last_publish >= PUBLISH_INTERVAL:
                # Build full MQTT payload (sensor data + metadata)
                payload = dict(sensor_data)
                payload["mqtt_connected"] = mqtt_connected
                payload["uptime_start"]   = UPTIME_START
                # MQTT publish
                mqtt_publish_data(mqtt_client, payload)
                # SQLite insert
                db_insert(sensor_data)
                # History publish (every 15 minutes, retained)
                if loop_start - last_history_publish >= HISTORY_INTERVAL:
                    mqtt_publish_history(mqtt_client, payload)
                    last_history_publish = loop_start
                last_publish = loop_start
                loop_count += 1
                if loop_count % 30 == 0:  # log every ~60 seconds
                    log.info(
                        "Status: mode=%d mqtt=%s noise=%.1f temp=%.1f pm25=%d loops=%d",
                        lcd_mode, mqtt_connected,
                        sensor_data.get("noise", 0),
                        sensor_data.get("temperature", 0),
                        sensor_data.get("pm25", 0),
                        loop_count,
                    )
            # --- Loop timing ---
            elapsed = time.time() - loop_start
            sleep_t = max(0.0, LOOP_SLEEP - elapsed)
            time.sleep(sleep_t)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received")
    except Exception as e:
        log.error("Fatal error in main loop: %s", e)
        import traceback
        traceback.print_exc()
    finally:
        log.info("Shutting down...")
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        except Exception:
            pass
        # Show stopped on LCD
        try:
            draw.rectangle((0, 0, LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
            draw.text((4, 30), "Stopped", font=font_med, fill=(255, 0, 0))
            disp.display(img)
        except Exception:
            pass
        log.info("farcom-mqtt-enviro.py stopped cleanly")
if __name__ == "__main__":
    main()

