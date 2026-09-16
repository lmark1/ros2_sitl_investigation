"""Spawn the kopterworx in a running Gazebo world and start ArduPilot SITL + DDS agent.

Thin wrapper around ardupilot_gz_bringup/launch/robots/robot.launch.py with the
kopterworx SDF, bridge config and parameter defaults.
"""
import os
import tempfile
from typing import List

from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def launch_robot(context: LaunchContext, *args, **kwargs):
    pkg = get_package_share_directory("kopterworx_gz")
    pkg_bringup = get_package_share_directory("ardupilot_gz_bringup")
    sdf_file = os.path.join(pkg, "models", "kopterworx", "model.sdf")
    with open(sdf_file, "r") as f:
        robot_desc = f.read()
    sim_address = LaunchConfiguration("sim_address").perform(context)
    robot_desc = robot_desc.replace("<fdm_addr>127.0.0.1</fdm_addr>", f"<fdm_addr>{sim_address}</fdm_addr>")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sdf")
    with open(tmp.name, "w") as f:
        f.write(robot_desc)
    bridge_config = os.path.join(pkg, "config", "kopterworx_bridge.yaml")
    pass_through = ["namespace", "use_gz_tf", "robot_name", "world_name", "model", "defaults",
                    "synthetic_clock", "sim_address", "x", "y", "z", "R", "P", "Y",
                    "instance", "sysid", "use_instance_dir", "use_dds_agent"]
    launch_args = {k: LaunchConfiguration(k) for k in pass_through}
    launch_args.update({"sdf_file": tmp.name, "bridge_config_file": bridge_config, "command": "arducopter"})
    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [PathJoinSubstitution([pkg_bringup, "launch", "robots", "robot.launch.py"])]),
        launch_arguments=launch_args.items(),
    )
    return [robot]


def generate_launch_description():
    pkg = get_package_share_directory("kopterworx_gz")
    pkg_sitl = get_package_share_directory("ardupilot_sitl")
    dp = os.path.join(pkg_sitl, "config", "default_params")
    defaults = ",".join([
        os.path.join(dp, "copter.parm"),
        os.path.join(dp, "gazebo-iris.parm"),
        os.path.join(dp, "dds_udp.parm"),
    ])
    args: List[DeclareLaunchArgument] = [
        DeclareLaunchArgument("namespace", default_value=""),
        DeclareLaunchArgument("use_gz_tf", default_value="true"),
        DeclareLaunchArgument("robot_name", default_value="kopterworx"),
        DeclareLaunchArgument("world_name", default_value="runway"),
        DeclareLaunchArgument("model", default_value="json"),
        DeclareLaunchArgument("defaults", default_value=defaults,
                              description="Comma separated SITL parameter files."),
        DeclareLaunchArgument("synthetic_clock", default_value="True"),
        DeclareLaunchArgument("sim_address", default_value="127.0.0.1"),
        DeclareLaunchArgument("x", default_value="0.0"),
        DeclareLaunchArgument("y", default_value="0.0"),
        DeclareLaunchArgument("z", default_value="0.35"),
        DeclareLaunchArgument("R", default_value="0.0"),
        DeclareLaunchArgument("P", default_value="0.0"),
        DeclareLaunchArgument("Y", default_value="0.0"),
        DeclareLaunchArgument("instance", default_value="0"),
        DeclareLaunchArgument("sysid", default_value=""),
        DeclareLaunchArgument("use_instance_dir", default_value="False"),
        DeclareLaunchArgument("use_dds_agent", default_value="True"),
    ]
    return LaunchDescription(args + [OpaqueFunction(function=launch_robot)])
