# syntax=docker/dockerfile:1
# ROS 2 SITL investigation image: Jazzy + Gazebo Harmonic + ArduPilot (upstream) + larics repos.
# Built in layers, see ros2_sitl_findings.md for what each layer needed.
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

CMD ["/bin/bash"]
