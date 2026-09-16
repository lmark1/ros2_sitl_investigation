#!/bin/bash
# Stop everything a ros2 launch of ardupilot_gz_bringup started (run inside the container).
# Patterns use a [b]racket so this script's own command line and its caller never match.
tmux kill-server 2>/dev/null
for pat in "ros2 launc[h]" "gz si[m]" "micro_ros_agen[t]" "mavproxy.p[y]" "parameter_bridg[e]" "ros_gz_sim/creat[e]" "robot_state_publishe[r]" "topic_tool[s]" "mavros_nod[e]"; do
  pkill -f "$pat" 2>/dev/null
done
pkill -x arducopter 2>/dev/null
sleep 2
pkill -9 -f "gz si[m]" 2>/dev/null
pkill -9 -x arducopter 2>/dev/null
pgrep -af "gz si[m]|arducopte[r]|micro_ros_agen[t]|mavproxy.p[y]|ros2 launc[h]" | cut -c1-100 || echo "sim stopped"
