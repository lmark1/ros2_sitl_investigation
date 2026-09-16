#!/bin/bash
# Stop everything a ros2 launch of ardupilot_gz_bringup started (run inside the container).
tmux kill-server 2>/dev/null
for pat in "ros2 launch" "gz sim" "micro_ros_agent" "mavproxy.py" "parameter_bridge" "ros_gz_sim/create" "robot_state_publisher" "topic_tools"; do
  pkill -f "$pat" 2>/dev/null
done
pkill -x arducopter 2>/dev/null
sleep 2
pkill -9 -f "gz sim" 2>/dev/null
pkill -9 -x arducopter 2>/dev/null
pgrep -af "gz sim|arducopter|micro_ros_agent|mavproxy.py|ros2 launch" | grep -v kill_sim | cut -c1-100 || echo "sim stopped"
