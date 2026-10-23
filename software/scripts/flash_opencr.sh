#!/bin/bash
# Flash TurtleBot3 ROS 2 firmware to OpenCR from the Raspberry Pi (aarch64).
#
#   OPENCR_MODEL=burger OPENCR_PORT=/dev/ttyACM0 ./flash_opencr.sh
#
# Keep USB and battery connected during flashing. After flashing, wait a few
# seconds before bringup; launching immediately can fail with
# "Failed connection with Devices".
set -euxo pipefail

OPENCR_PORT="${OPENCR_PORT:-/dev/ttyACM0}"
OPENCR_MODEL="${OPENCR_MODEL:-burger}"

# The update tool is a 32-bit ARM binary.
sudo dpkg --add-architecture armhf
sudo apt-get -o DPkg::Lock::Timeout=600 update
sudo apt-get -o DPkg::Lock::Timeout=600 install -y libc6:armhf

cd /tmp
rm -rf opencr_update opencr_update.tar.bz2
wget https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2
tar -xf opencr_update.tar.bz2
cd opencr_update
./update.sh "$OPENCR_PORT" "$OPENCR_MODEL.opencr"
