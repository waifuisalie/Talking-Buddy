#!/bin/bash
# ESP32 Wake Word - Upload Script
# Uploads firmware and filesystem to ESP32-S3

set -e

echo "🔄 Uploading ESP32 firmware..."
pio run --target upload

echo ""
echo "📁 Uploading filesystem (SPIFFS)..."
pio run --target uploadfs

echo ""
echo "✅ Upload complete!"
echo ""
echo "To monitor serial output:"
echo "  pio device monitor"
echo ""
