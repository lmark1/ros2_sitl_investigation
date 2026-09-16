"""Gazebo runway world (from ardupilot_gz_gazebo) with the kopterworx."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description():
    pkg = get_package_share_directory("kopterworx_gz")
    pkg_gz = get_package_share_directory("ardupilot_gz_gazebo")
    pkg_ros_gz_sim = get_package_share_directory("ros_gz_sim")
    gz_launch = f'{Path(pkg_ros_gz_sim) / "launch" / "gz_sim.launch.py"}'
    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless_rendering")
    # headless_rendering:=true adds --headless-rendering (EGL, no X needed for camera/lidar)
    server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gz_launch),
        launch_arguments={"gz_args": ["-v4 -s -r ", PythonExpression(["'--headless-rendering ' if '", headless, "' == 'true' else ''"]), world]}.items(),
        condition=IfCondition(LaunchConfiguration("use_gz_sim_server")),
    )
    gui = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gz_launch),
        launch_arguments={"gz_args": "-v4 -g"}.items(),
        condition=IfCondition(LaunchConfiguration("use_gz_sim_gui")),
    )
    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(f'{Path(pkg) / "launch" / "kopterworx.launch.py"}'),
        condition=IfCondition(LaunchConfiguration("spawn_robot")),
    )
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value=f'{Path(pkg_gz) / "worlds" / "runway.sdf"}'),
        DeclareLaunchArgument("use_gz_sim_server", default_value="true"),
        DeclareLaunchArgument("use_gz_sim_gui", default_value="true"),
        DeclareLaunchArgument("spawn_robot", default_value="true"),
        DeclareLaunchArgument("headless_rendering", default_value="false"),
        DeclareLaunchArgument("rviz", default_value="false", description="unused, kept for start_sim.sh"),
        server, gui, robot,
    ])
