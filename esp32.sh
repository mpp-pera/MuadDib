#!/usr/bin/env bash
set -e

ARDUINO_CLI="${HOME}/bin/arduino-cli"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SKETCH_DIR="$REPO_ROOT/tank/ESP32-WROVER-Camera/ESP32-WROVER-Camera/ESP32_CameraServer_AP_20210107"

FQBN_ESP32="esp32:esp32:esp32:PartitionScheme=huge_app"
FQBN_CAM="esp32:esp32:esp32wrover:PartitionScheme=huge_app"

usage() {
    echo "Usage:"
    echo "  $(basename "$0") compile <esp32|cam>"
    echo "  $(basename "$0") upload  <esp32|cam> <port>            e.g. /dev/ttyUSB0"
    echo "  $(basename "$0") monitor <port> [baudrate]             default baudrate: 9600"
    exit 1
}

get_fqbn() {
    case "$1" in
        esp32) echo "$FQBN_ESP32" ;;
        cam)   echo "$FQBN_CAM"   ;;
        *)
            echo "Error: unknown device type '$1' (use esp32 or cam)" >&2
            usage
            ;;
    esac
}

case "$1" in
    compile)
        [ $# -lt 2 ] && usage
        FQBN=$(get_fqbn "$2")
        echo "Compiling for $2 ($FQBN)..."
        "$ARDUINO_CLI" compile --fqbn "$FQBN" "$SKETCH_DIR"
        ;;
    upload)
        [ $# -lt 3 ] && usage
        FQBN=$(get_fqbn "$2")
        PORT="$3"
        echo "Compiling and uploading for $2 ($FQBN) on $PORT..."
        "$ARDUINO_CLI" compile --fqbn "$FQBN" "$SKETCH_DIR" --upload --port "$PORT"
        ;;
    monitor)
        [ $# -lt 2 ] && usage
        PORT="$2"
        BAUD="${3:-9600}"
        echo "Opening monitor on $PORT at ${BAUD} baud (Ctrl+C to exit)..."
        "$ARDUINO_CLI" monitor --port "$PORT" --config baudrate="$BAUD"
        ;;
    *)
        usage
        ;;
esac
