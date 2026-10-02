#!/bin/bash
# Stop every process of a running simulation session (run inside the container).
# Patterns are anchored to the start of the command line, so a shell or editor that
# only mentions one of these names is never hit.
tmux kill-server 2>/dev/null
PATTERNS=(
  '^[^ ]*python3 [^ ]*sim_vehicle\.py'      # SITL starter
  '^[^ ]*python3 [^ ]*mavproxy\.py'         # MAVProxy
  '^[^ ]*python3 [^ ]*/ros2 launch'         # any ros2 launch
  '^(ruby [^ ]*/)?gz sim'                   # Gazebo server and GUI
  '^[^ ]*/parameter_bridge'                 # ros_gz_bridge
  '^[^ ]*/ros_gz_sim/create'                # spawner
  '^[^ ]*/robot_state_publisher'
  '^[^ ]*/mavros_node'
  '^[^ ]*/micro_ros_agent'
  '^[^ ]*/topic_tools/relay'
)
for p in "${PATTERNS[@]}"; do pkill -f "$p" 2>/dev/null; done
pkill -x arducopter 2>/dev/null
sleep 2
pkill -9 -f '^(ruby [^ ]*/)?gz sim' 2>/dev/null
pkill -9 -x arducopter 2>/dev/null
left=$(pgrep -fl '^(ruby [^ ]*/)?gz sim|^[^ ]*python3 [^ ]*(sim_vehicle|mavproxy)\.py|^[^ ]*/mavros_node' ; pgrep -xl arducopter)
[ -z "$left" ] && echo "sim stopped" || echo "still running: $left"
