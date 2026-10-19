#!/bin/bash
# TurtleBot3 SBC setup for Raspberry Pi 4 (Ubuntu 22.04 server, ROS 2 Humble).
# Run on the Pi as the normal user (e.g. ubuntu); sudo is used where needed.
#
#   TB3_MODEL=burger LDS_MODEL=LDS-01 ROS_DOMAIN_ID=30 ./setup_sbc.sh
#
# Follows the ROBOTIS e-Manual SBC setup, plus rosdep for missing runtime
# deps (xacro, robot_state_publisher, ...) that bringup needs.
set -euxo pipefail

TB3_MODEL="${TB3_MODEL:-burger}"
LDS_MODEL="${LDS_MODEL:-LDS-01}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
WS="${WS:-$HOME/turtlebot3_ws}"

export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
APT=(sudo -E apt-get -o DPkg::Lock::Timeout=600)

sudo -v

"${APT[@]}" update
"${APT[@]}" install -y locales software-properties-common curl git
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe
V=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F tag_name | awk -F'"' '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${V}/ros2-apt-source_${V}.jammy_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
"${APT[@]}" update
"${APT[@]}" upgrade -y
"${APT[@]}" install -y ros-humble-ros-base ros-dev-tools python3-argcomplete \
  python3-colcon-common-extensions libboost-system-dev build-essential libudev-dev \
  ros-humble-hls-lfcd-lds-driver ros-humble-turtlebot3-msgs ros-humble-dynamixel-sdk \
  ros-humble-xacro ros-humble-robot-state-publisher

mkdir -p "$WS/src" && cd "$WS/src"
[ -d turtlebot3 ] || git clone -b humble https://github.com/ROBOTIS-GIT/turtlebot3.git
[ -d ld08_driver ] || git clone -b humble https://github.com/ROBOTIS-GIT/ld08_driver.git
rm -rf turtlebot3/turtlebot3_cartographer turtlebot3/turtlebot3_navigation2

set +u; source /opt/ros/humble/setup.bash; set -u
[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || sudo rosdep init
rosdep update --rosdistro humble
cd "$WS"
rosdep install --from-paths src --ignore-src -r -y --rosdistro humble

MAKEFLAGS=-j2 colcon build --symlink-install --parallel-workers 1
set +u; source "$WS/install/setup.bash"; set -u

sudo cp "$(ros2 pkg prefix turtlebot3_bringup)/share/turtlebot3_bringup/script/99-turtlebot3-cdc.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

grep -q 'TURTLEBOT3_SETUP' ~/.bashrc || cat >> ~/.bashrc <<EOF
# TURTLEBOT3_SETUP
source /opt/ros/humble/setup.bash
source $WS/install/setup.bash
export ROS_DOMAIN_ID=$ROS_DOMAIN_ID #TURTLEBOT3
export LDS_MODEL=$LDS_MODEL
export TURTLEBOT3_MODEL=$TB3_MODEL
EOF

echo "SETUP_ALL_DONE (reboot if /var/run/reboot-required exists)"
