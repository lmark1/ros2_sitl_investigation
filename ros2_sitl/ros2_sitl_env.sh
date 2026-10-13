# Sourced by ~/.bashrc in the container and by helper scripts.
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
export GZ_VERSION=harmonic
export PATH=$PATH:/root/ros2_ws/src/ardupilot/Tools/autotest
# package://ardupilot_gazebo/... URIs in the upstream models need <prefix>/share on
# both paths: GZ_SIM_RESOURCE_PATH for the gz server, SDF_PATH for sdformat_urdf in
# robot_state_publisher. The ardupilot_gazebo env hooks only add share/<pkg>/models.
# See ArduPilot/ardupilot_gazebo#109 and ArduPilot/ardupilot_gz#96.
export GZ_SIM_RESOURCE_PATH=${GZ_SIM_RESOURCE_PATH}:/root/ros2_ws/install/ardupilot_gazebo/share
export SDF_PATH=${SDF_PATH}:/root/ros2_ws/install/ardupilot_gazebo/share
# The container is on the host network. Jazzy discovers ROS 2 nodes on the whole subnet
# by default, so another machine's simulation lands on the same topics. Localhost only.
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
