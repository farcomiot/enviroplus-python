# SSH Diagnostic Commands — Serial Sensor Communications

> Reference guide for remote diagnostics of sensor hardware via SSH.
> Target: Raspberry Pi running farcom-mqtt-enviro.py with Pimoroni Enviro+.

---

## SSH Access

```bash
# Connect to EnviroPi
ssh enviropi@enviropi
# Password: (see Pi credentials — not stored in this repo)

# Or with sshpass for automation
sshpass -p '<password>' ssh -o StrictHostKeyChecking=no enviropi@enviropi
```

---

## PMS5003 Particulate Matter Sensor (UART)

The PMS5003 communicates over serial UART at 9600 baud on /dev/ttyAMA0.

### Check if serial port exists
```bash
ls -la /dev/ttyAMA0
# Should show: crw-rw---- 1 root dialout ... /dev/ttyAMA0
```

### Check serial port permissions
```bash
groups enviropi
# Must include: dialout
```

### Monitor raw serial frames (hex dump)
```bash
# View first 128 bytes from PMS5003 (live)
sudo timeout 5 xxd -l 128 /dev/ttyAMA0
```

**Expected output:** Frames start with 0x42 0x4d (ASCII "BM").
```
00000000: 424d 001c 0005 0008 0009 0005 0008 0009  BM..............
```

### Frame structure (32 bytes)
| Offset | Bytes | Field | Notes |
|--------|-------|-------|-------|
| 0-1 | 2 | Start chars | Always 0x42 0x4D ("BM") |
| 2-3 | 2 | Frame length | Always 0x001C (28) |
| 4-5 | 2 | PM1.0 (CF=1) | Standard particles ug/m3 |
| 6-7 | 2 | PM2.5 (CF=1) | Standard particles ug/m3 |
| 8-9 | 2 | PM10 (CF=1) | Standard particles ug/m3 |
| 10-11 | 2 | PM1.0 (atm) | Atmospheric environment |
| 12-13 | 2 | PM2.5 (atm) | Atmospheric environment |
| 14-15 | 2 | PM10 (atm) | Atmospheric environment |
| 28 | 1 | Version | Firmware version |
| 29 | 1 | Error code | 0x00 = OK |
| 30-31 | 2 | Checksum | Sum of bytes 0-29 |

### Python one-liner to read PMS5003
```bash
python3 -c "
from pms5003 import PMS5003
p = PMS5003()
d = p.read()
print('PM1.0:', d.pm_ug_per_m3(1.0))
print('PM2.5:', d.pm_ug_per_m3(2.5))
print('PM10:', d.pm_ug_per_m3(10))
"
```

### Power-cycle PMS5003 via GPIO22
```bash
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(22, GPIO.OUT)
GPIO.output(22, GPIO.LOW)   # OFF
time.sleep(3)
GPIO.output(22, GPIO.HIGH)  # ON
time.sleep(30)               # 30s warm-up required
print('PMS5003 power-cycled')
GPIO.cleanup()
"
```

### Common PMS5003 issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| All-zero PM values, nonzero particle counts | Ribbon cable inverted | Reseat cable correctly (not keyed) |
| SerialTimeoutError | Cable disconnected or sensor dead | Check cable, power-cycle GPIO22 |
| ChecksumMismatchError | Electrical noise or loose cable | Reseat cable, check for interference |
| Slow/blocked LCD updates | Blocking serial read in main loop | Use throttled reads (2s interval) |

---

## BME280 Temperature/Humidity/Pressure (I2C)

```bash
# Detect I2C devices
i2cdetect -y 1
# BME280 should appear at address 0x76

# Python one-liner
python3 -c "
from bme280 import BME280
from smbus2 import SMBus
bus = SMBus(1)
bme = BME280(i2c_dev=bus)
print('Temp:', bme.get_temperature(), 'C')
print('Pres:', bme.get_pressure(), 'hPa')
print('Humi:', bme.get_humidity(), '%')
"
```

---

## LTR559 Light/Proximity (I2C)

```bash
# Should appear at 0x23 on i2cdetect
python3 -c "
from ltr559 import LTR559
ltr = LTR559()
print('Light:', ltr.get_lux(), 'Lux')
print('Prox:', ltr.get_proximity())
"
```

---

## MICS-6814 Gas Sensor (I2C via ADC)

```bash
python3 -c "
from enviroplus import gas
readings = gas.read_all()
print('Oxidising (NO2):', readings.oxidising / 1000, 'kOhm')
print('Reducing (CO):', readings.reducing / 1000, 'kOhm')
print('NH3:', readings.nh3 / 1000, 'kOhm')
"
```

> Note: MICS-6814 readings are in resistance (kOhm). Higher oxidising = more NO2. Lower reducing = more CO/VOC.

---

## ICS-43432 Noise Sensor (I2S)

```bash
python3 -c "
from enviroplus.noise import Noise
n = Noise()
low, mid, high, amp = n.get_noise_profile()
print('Low:', low, 'Mid:', mid, 'High:', high)
print('Amplitude (dB):', amp)
"
```

---

## ST7735 LCD Display (SPI)

```bash
# Check SPI is enabled
ls /dev/spidev*
# Should show: /dev/spidev0.0  /dev/spidev0.1

# Display test
python3 -c "
import st7735 as ST7735
from PIL import Image, ImageDraw
disp = ST7735.ST7735(port=0, cs=1, dc=9, backlight=12, rotation=270,
                      spi_speed_hz=32000000)
disp.begin()
img = Image.new('RGB', (disp.width, disp.height), (0,255,0))
disp.display(img)
print('LCD: green screen displayed')
"
```

---

## WiFi / Network Diagnostics

```bash
# Current WiFi connection
iwgetid -r                    # SSID
hostname -I                   # Local IP

# NetworkManager (Bookworm)
nmcli connection show         # All saved connections
nmcli device wifi list        # Available networks
nmcli general status          # Overall status

# External IP
curl -s https://api.ipify.org
```

---

## System Health

```bash
# CPU temperature
cat /sys/class/thermal/thermal_zone0/temp
# Divide by 1000 for C (e.g., 52000 = 52.0C)

# Memory
free -h

# Disk
df -h /

# Uptime
uptime

# Service status
sudo systemctl status farcom-enviro.service

# Live service logs
sudo journalctl -u farcom-enviro -f --no-pager

# Check if process is running
pgrep -a farcom
```

---

## Service Management

```bash
# Restart the monitoring service
sudo systemctl restart farcom-enviro.service

# Stop (maintenance)
sudo systemctl stop farcom-enviro.service

# Start
sudo systemctl start farcom-enviro.service

# View service file
sudo systemctl cat farcom-enviro.service

# Enable on boot
sudo systemctl enable farcom-enviro.service
```

---

## SQLite Database

```bash
# Check database exists and size
ls -lh /home/enviropi/enviroplus-python/examples/enviro_data.db

# Query recent readings
sqlite3 /home/enviropi/enviroplus-python/examples/enviro_data.db \
  "SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 5;"

# Check 24h data count
sqlite3 /home/enviropi/enviroplus-python/examples/enviro_data.db \
  "SELECT COUNT(*) FROM sensor_data WHERE timestamp > datetime('now', '-24 hours');"

# Average PM2.5 last hour
sqlite3 /home/enviropi/enviroplus-python/examples/enviro_data.db \
  "SELECT AVG(pm25) FROM sensor_data WHERE timestamp > datetime('now', '-1 hour');"
```

---

## Troubleshooting Quick Reference

| Issue | Diagnostic | Resolution |
|-------|-----------|------------|
| No LCD display | Check SPI: ls /dev/spidev* | Enable SPI in raspi-config |
| PM all zeros | xxd /dev/ttyAMA0 check frame | Reseat PMS5003 ribbon cable |
| No MQTT publish | Check broker connectivity | mosquitto_pub test |
| Service wont start | journalctl -u farcom-enviro -e | Check Python deps, permissions |
| High CPU temp (>70C) | cat thermal_zone0/temp | Improve ventilation, add heatsink |
| WiFi disconnects | nmcli device wifi list | Check signal strength, add backup WiFi |
| I2C errors | i2cdetect -y 1 | Check hat seated correctly |
| pip install fails | Bookworm PEP 668 | Add --break-system-packages |

---

2024-2026 Ing. Aaron Farias — Farcom Industrial. All Rights Reserved.
