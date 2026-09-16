# ROS 2 SITL findings

Working notes for the plan in `ros2_sitl_investigation.md`. Dates are absolute.
Sections follow "What to write down" in the plan.

## Host (2026-09-16)

- Docker 29.8.0 with buildx v0.37.0, nvidia-container-toolkit hook present
  (`/usr/bin/nvidia-container-runtime-hook`), `docker run --gpus all` verified on
  RTX 4070 Laptop, driver 580.126.09. No `nvidia` runtime registered in
  `docker info`, not needed: `--gpus` goes through the hook.
- ssh-agent has two keys loaded, `ssh -T git@github.com` authenticates as lmark1.
- Noetic container `pcl_ris` (image `pcl_ris:focal`, host network) is running and
  is left alone. None of the SITL ports (5760, 9002/9003, 14550, 2019) are in use.

## Deviations from the plan doc (checked against ArduPilot docs, 2026-09-16)

- ArduPilot wiki `ros2-install.html` still says "ROS 2 Humble is the only version
  supported". The ardupilot repo itself ships `Tools/ros2/ros2.jazzy.repos` and its
  `Tools/ros2/README.md` says Humble or Jazzy. Staying on Jazzy as the plan says.
- `ardupilot_gz/ros2_gz.repos` pins `ros_gz`, `sdformat_urdf` and `micro_ros_agent`
  to `humble` branches. On Jazzy those would not build against the Jazzy base. Using
  a local repos file instead (`ros2_sitl/ros2_gz.jazzy.repos`): `ros_gz` and
  `sdformat_urdf` from the Jazzy apt binaries already in `osrf/ros:jazzy-desktop-full`
  (ros_gz 1.0.22, gz-sim 8.11.0 vendor packages), `micro_ros_agent` from its `jazzy`
  branch (same as ardupilot's `ros2.jazzy.repos`). ardupilot_gz has no CI, so there is
  no upstream tested combination to copy.
- The plan's Dockerfile omits Micro-XRCE-DDS-Gen (needed by the `ardupilot_sitl`
  colcon package to build SITL with `--enable-DDS`) and the ArduPilot build
  prerequisites (empy, pexpect, future, ...). Added, following
  `ardupilot_dev_docker/docker/Dockerfile_dev-ros`.
- rosdep keys `gz-cmake3`, `gz-sim8`, `gz-plugin2`, `gz-common5` have no Ubuntu
  definition on the Jazzy base. Adding the osrf `00-gazebo.list` would map them to the
  non-vendor Harmonic debs and mix two Gazebo installs. They are skipped in rosdep,
  the vendored packages satisfy CMake once `/opt/ros/jazzy` is sourced.
- `ros2_ws` is not bind mounted (plan asked to pick one): the workspace built into
  the image is what runs. `ros2_sitl/` is mounted at `/root/ros2_sitl` for scripts
  and logs.

## Baseline (image, commits, apt versions)

TODO

## Step 1: upstream iris

TODO

## Step 2: mavros2 vs AP_DDS

TODO

## ArduPilot version and the fork

TODO

## Step 3: kopterworx port

Not started.

## Step 4: headless timing

Not started.

## Patches and failures

(none yet)
