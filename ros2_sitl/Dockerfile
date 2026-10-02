# syntax=docker/dockerfile:1
# ROS 2 SITL investigation image: Jazzy + Gazebo Harmonic + ArduPilot (upstream) + larics repos.
# Built in layers, see ros2_sitl_findings.md for what each layer needed.

# Builder stage: Micro-XRCE-DDS-Gen, needed by the ardupilot_sitl colcon package
# (waf --enable-DDS). Same approach as ardupilot_dev_docker/Dockerfile_dev-ros.
FROM eclipse-temurin:17-jdk-noble AS dds-gen-builder
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
# Pinned to the commit of the 2026-09-16 baseline (master at the time).
RUN git clone https://github.com/ArduPilot/Micro-XRCE-DDS-Gen.git /dds-gen \
    && cd /dds-gen && git checkout 4bc7ec2c7f77ae89cd216432f05470ad99f7faa1 \
    && git submodule update --init --recursive \
    && ./gradlew assemble \
    && git -C /dds-gen log -1 --format='%H' > /dds-gen/COMMIT

FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Layer 1: tools from the plan + ArduPilot SITL build prerequisites
# (list taken from ardupilot_dev_docker/docker/Dockerfile_dev-ros).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client python3-vcstool python3-colcon-common-extensions \
    python3-pip default-jre tmux tmuxinator vim less \
    build-essential ccache cmake g++ gawk gdb libtool libtool-bin \
    libxml2-dev libxml2-utils libxslt1-dev lsb-release make ninja-build \
    python-is-python3 python3-dev python3-numpy python3-pyparsing python3-serial \
    python3-future python3-lxml python3-pexpect python3-empy python3-pyelftools \
    ros-jazzy-launch-pytest ros-dev-tools socat wget zip iproute2 iputils-ping net-tools \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: python tools. gitman for the larics simulation deps, MAVProxy for sim_vehicle.py.
RUN pip3 install --no-cache-dir gitman MAVProxy pymavlink dronecan ptyprocess fastcrc tabulate

# Layer 3: SSH at build time. The key comes from the host agent through --ssh default,
# only the GitHub host key is written into the image.
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts

WORKDIR /root
# Layer 4: private larics repos (SSH agent forwarded, nothing copied in).
RUN --mount=type=ssh git clone git@github.com:larics/uav_ros_simulation.git
RUN --mount=type=ssh git clone git@github.com:larics/uav_ros_stack.git

# Layer 5: gitman for the simulation dependencies (default group "simulation":
# larics ardupilot Larics-4.4.3 + submodules, ardupilot_gazebo fork, rotors_simulator,
# mav_comm, larics_gazebo_worlds). Reference only, nothing here is built for ROS 1.
RUN --mount=type=ssh cd /root/uav_ros_simulation && gitman install

# Layer 6: Micro-XRCE-DDS-Gen from the builder stage (runs on the default-jre above).
COPY --from=dds-gen-builder /dds-gen/scripts /dds-gen/scripts
COPY --from=dds-gen-builder /dds-gen/share /dds-gen/share
COPY --from=dds-gen-builder /dds-gen/COMMIT /dds-gen/COMMIT
ENV PATH="/dds-gen/scripts:${PATH}"

# Layer 7: ROS 2 workspace sources. Local repos file, see comments in it for why
# it differs from upstream ros2_gz.repos.
ENV GZ_VERSION=harmonic
COPY ros2_gz.jazzy.repos /root/ros2_gz.jazzy.repos
RUN mkdir -p /root/ros2_ws/src && cd /root/ros2_ws \
    && vcs import --recursive --input /root/ros2_gz.jazzy.repos src \
    && vcs export --exact src > /root/ros2_ws/imported_commits.repos

# Layer 8: rosdep. gz-* keys skipped: no Ubuntu definition without the osrf gazebo
# list, and that list would install a second (non vendored) Harmonic. The vendored
# packages in the base satisfy find_package(gz-sim8) once ROS is sourced.
# microxrcedds_agent is fetched by micro_ros_agent's CMake at build time.
RUN cd /root/ros2_ws && apt-get update && rosdep update \
    && . /opt/ros/jazzy/setup.sh \
    && rosdep install --rosdistro jazzy --from-paths src --ignore-src -r -y \
       --skip-keys "microxrcedds_agent gz-cmake3 gz-sim8 gz-plugin2 gz-common5 gz-cmake4 gz-sim9 gz-plugin3 gz-common6 gz-cmake gz-sim gz-plugin gz-common gz-sim7" \
    && rm -rf /var/lib/apt/lists/*

# Layer 9: build. ardupilot_sitl (waf, SITL with DDS), micro_ros_agent (fetches
# Micro-XRCE-DDS-Agent), ardupilot_gazebo (gz plugin), ardupilot_gz_*.
RUN cd /root/ros2_ws && . /opt/ros/jazzy/setup.sh \
    && colcon build --packages-up-to ardupilot_gz_bringup \
       --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    2>&1 | tail -n 200

# Layer 9b: mavros2 for step 2 (interface decision), GeographicLib datasets for it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-mavros ros-jazzy-mavros-extras ros-jazzy-mavros-msgs \
    && rm -rf /var/lib/apt/lists/* \
    && /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh

# Layer 9c: step 3. ArduPilotPlugin patch (gz.msgs.Actuators output for ACTUATOR
# channels -> MulticopterMotorModel) and the kopterworx_gz package.
COPY patches/ardupilot_gazebo_actuators.patch /root/patches/
RUN cd /root/ros2_ws/src/ardupilot_gazebo && git apply /root/patches/ardupilot_gazebo_actuators.patch
COPY kopterworx_gz /root/ros2_ws/src/kopterworx_gz
RUN cd /root/ros2_ws && . /opt/ros/jazzy/setup.sh \
    && colcon build --packages-select ardupilot_gazebo kopterworx_gz \
       --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo 2>&1 | tail -n 20

# Layer 10: environment. ros2_sitl_env.sh also adds <prefix>/share of ardupilot_gazebo
# to GZ_SIM_RESOURCE_PATH and SDF_PATH, without it the package:// includes in the
# upstream iris model do not resolve on Jazzy (ArduPilot/ardupilot_gazebo#109).
COPY ros2_sitl_env.sh /root/ros2_sitl_env.sh
RUN echo "source /root/ros2_sitl_env.sh" >> /root/.bashrc
WORKDIR /root/ros2_ws
CMD ["/bin/bash"]
