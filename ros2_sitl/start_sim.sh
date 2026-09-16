#!/bin/bash
# Start the upstream iris sim inside the container in tmux session "sim":
#   window launch : ros2 launch ardupilot_gz_bringup iris_runway.launch.py (+ extra parms)
#   window mav    : MAVProxy console on udp 14550
#   window mavros : mavros2 on SITL SERIAL1 (tcp 5762), streams requested at 50 Hz
# Usage (inside container): /root/ros2_sitl/start_sim.sh [pkg launch_file] [extra launch args]
#   default: ardupilot_gz_bringup iris_runway.launch.py
#   e.g.   : /root/ros2_sitl/start_sim.sh kopterworx_gz kopterworx_runway.launch.py
source /root/ros2_sitl_env.sh
PKG=ardupilot_gz_bringup; LAUNCH=iris_runway.launch.py
if [ $# -ge 2 ] && [[ "$2" == *.launch.py ]]; then PKG=$1; LAUNCH=$2; shift 2; fi
/root/ros2_sitl/kill_sim.sh >/dev/null 2>&1
mkdir -p /root/ros2_sitl/logs
SITL=$(ros2 pkg prefix ardupilot_sitl)/share/ardupilot_sitl/config/default_params
GZ=$(ros2 pkg prefix ardupilot_gazebo)/share/ardupilot_gazebo/config
if [ "$PKG" == "kopterworx_gz" ]; then
  DEF="$SITL/copter.parm,$SITL/gazebo-iris.parm,$SITL/dds_udp.parm,/root/ros2_sitl/config/sitl_extra.parm${KW_PARMS:+,$KW_PARMS}"
else
  DEF="$SITL/copter.parm,$GZ/gazebo-iris-gimbal.parm,$SITL/dds_udp.parm,$SITL/dds_use_ns.parm,/root/ros2_sitl/config/sitl_extra.parm"
fi
tmux new-session -d -s sim -n launch "bash -c \"source /root/ros2_sitl_env.sh; ros2 launch $PKG $LAUNCH rviz:=false defaults:=$DEF $* 2>&1 | tee /root/ros2_sitl/logs/launch_iris.log; exec bash\""
timeout 150 bash -c "until ros2 topic list 2>/dev/null | grep -qE '/ap(/v1)?/pose/filtered'; do sleep 3; done" || { echo "sim did not come up"; exit 1; }
echo "sim up"
tmux new-window -t sim -n mav "bash -c \"source /root/ros2_sitl_env.sh; mavproxy.py --master udp:127.0.0.1:14550 --aircraft /root/ros2_sitl/logs/mav 2>&1 | tee /root/ros2_sitl/logs/mavproxy.log; exec bash\""
tmux new-window -t sim -n mavros "bash -c \"source /root/ros2_sitl_env.sh; ros2 launch mavros apm.launch fcu_url:=tcp://127.0.0.1:5762 2>&1 | tee /root/ros2_sitl/logs/mavros.log; exec bash\""
timeout 120 bash -c "until timeout 5 ros2 topic echo /mavros/state --once 2>/dev/null | grep -q 'connected: true'; do sleep 3; done" || { echo "mavros did not connect"; exit 1; }
echo "mavros connected"
ros2 service call /mavros/set_stream_rate mavros_msgs/srv/StreamRate "{stream_id: 0, message_rate: 50, on_off: true}" >/dev/null
echo "stream rate 50 requested"
# ros-jazzy-mavros 2.15.1: thrust_scaling from apm_config.yaml does not reach the
# setpoint_raw plugin (stays NaN -> thrust ignored). Set it explicitly.
ros2 param set /mavros/setpoint_raw thrust_scaling 1.0 >/dev/null
echo "setpoint_raw thrust_scaling set to 1.0"
