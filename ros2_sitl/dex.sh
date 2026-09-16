#!/bin/bash
# Run a command inside the ros2_sitl container with the ROS 2 environment sourced.
# Usage: ./dex.sh 'ros2 topic list'
docker exec ${DEX_OPTS} ros2_sitl bash -c 'source /root/ros2_sitl_env.sh; '"$*"
