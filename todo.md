# TODO

## Battery telemetry debugging (paused)

Status as of pausing:

- **Arduino firmware** (`tank/ConquerorCar_Driver_20210104`): reflashed successfully with the
  battery-report + flash-size fixes (case-sensitivity includes, `sprintf` instead of `dtostrf`
  so it fits — 99% flash used). Not yet committed/pushed.
- **ESP32 firmware** (`tank/ESP32-WROVER-Camera`): reflashed with the matching integer-centivolts
  parser (`toInt() / 100.0` instead of `toFloat()`). Confirmed alive and healthy — heartbeats
  advancing normally every ~60s (proves STA mode + main loop are running fine). Not yet committed/pushed.
- **`arduino.sh`**: new build/upload/monitor script for the main Arduino board (mirrors
  `esp32.sh`). Requires `arduino:avr` core + `Servo` library installed via arduino-cli, FastLED
  bundled in `addLibrary/`. Not yet committed/pushed.

**Unresolved**: battery telemetry (`{"V":...}` frames) still isn't reaching the hub
(`battery_v` never appears in `/api/devices/tank-01` meta), even though:
- The Arduino board was reflashed and its USB/BLE switch was flipped back to run mode.
- The ESP32 was reflashed and is confirmed looping normally.

Next diagnostic step: check the Arduino's own serial output directly (flip the switch to
USB/PROG mode, open a monitor at 9600 baud — e.g.
`arduino-cli monitor --port /dev/ttyACM0 --config baudrate=9600` — and watch for `{"V":...}`
frames appearing roughly once a minute). This will tell us whether the problem is on the
Arduino send-side or the Serial2 link/wiring to the ESP32.

Note: don't use `cat`/`stty` directly on the ESP32's `/dev/ttyUSB0` for debugging — opening the
port that way can assert DTR and hold the ESP32 in reset via its auto-reset circuit. Use
`arduino-cli monitor` or `esp32.sh monitor` instead.

## Uncommitted changes to review/commit

- `tank/ConquerorCar_Driver_20210104/ConquerorCar_Driver_20210104/ApplicationFunctionSet_xxx0.cpp`
  (case-sensitivity include fixes, sprintf-based battery report)
- `tank/ConquerorCar_Driver_20210104/ConquerorCar_Driver_20210104/ApplicationFunctionSet_xxx0.h`
  (case-sensitivity include fix)
- `tank/ESP32-WROVER-Camera/ESP32-WROVER-Camera/ESP32_CameraServer_AP_20210107/ESP32_CameraServer_AP_20210107.ino`
  (integer centivolts parsing)
- `arduino.sh` (new)
