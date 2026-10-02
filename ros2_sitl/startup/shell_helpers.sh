# Sourced by every pane of the sessions in this folder (pre_window in session.yml).
# ROS 2 versions of the wait helpers in uav_ros_stack/miscellaneous/shell_additions.
source /root/ros2_sitl_env.sh

# Gazebo server is up and stepping: it publishes /clock on gz transport.
waitForSimulation() {
  until gz topic -l 2>/dev/null | grep -q '^/clock$'; do sleep 1; done
}

# A model with the given name exists in the world.   waitForModel kopterworx
waitForModel() {
  until gz model --list 2>/dev/null | grep -qw "$1"; do sleep 1; done
}

# ROS 2 graph answers and the gz -> ROS bridge delivers /clock.
waitForRos() {
  until ros2 topic list 2>/dev/null | grep -q '^/clock$'; do sleep 1; done
}

# mavros has a heartbeat from the autopilot.
waitForMavros() {
  until timeout 5 ros2 topic echo /mavros/state --once 2>/dev/null | grep -q 'connected: true'; do sleep 2; done
}

# The EKF has a position: mavros publishes local odometry.
waitForOdometry() {
  until timeout 5 ros2 topic echo /mavros/local_position/odom --once >/dev/null 2>&1; do sleep 2; done
}

# Print a topic rate in one line.   rate /mavros/local_position/pose
rate() {
  echo "$1: $(timeout 8 ros2 topic hz "$1" --window 100 2>&1 | grep -oE 'average rate: [0-9.]+' | tail -1)"
}
