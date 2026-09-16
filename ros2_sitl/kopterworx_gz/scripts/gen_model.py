#!/usr/bin/env python3
"""Generate models/kopterworx/model.sdf.

Numbers come from uav_ros_simulation/ros_packages/ardupilot_gazebo/models/kopterworx/urdf/
kopterworx_base.urdf.xacro (rotors_simulator based classic model). Rotor plugin parameters are
the rotors gazebo_motor_model ones, taken over 1:1 by gz::sim::systems::MulticopterMotorModel.
Run from anywhere: python3 gen_model.py
"""
import argparse
import math
import os

ap = argparse.ArgumentParser()
ap.add_argument("--no-camera", action="store_true", help="drop the front RGB-D camera (classic default: on)")
ap.add_argument("--lidar", action="store_true", help="add the velodyne style gpu_lidar (classic default: off)")
ARGS = ap.parse_args()

# ---- body (kopterworx_base.urdf.xacro) ----
MASS = 9.0
BODY_INERTIA = dict(ixx=0.303755, ixy=0.0004484919, ixz=0.0010159727, iyy=0.27722, iyz=-0.001806885, izz=0.469164)
BODY_BOX = (0.3, 0.3, 0.6)          # collision box, body_width x body_width x body_height
MESH_SCALE = 0.1
ARM = 0.52
C45 = 0.7071068
RX, RY, RZ = ARM * C45, ARM * C45, 0.115
# ---- rotors ----
MASS_ROTOR = 0.01
RADIUS_ROTOR = 0.285
ROTOR_SLOWDOWN = 15
PROP_SCALE = 0.003
# box inertia of the rotor, mass_rotor * slowdown as in the xacro
_m = MASS_ROTOR * ROTOR_SLOWDOWN
ROTOR_INERTIA = dict(ixx=_m / 12 * (0.015 ** 2 + 0.003 ** 2), iyy=_m / 12 * (RADIUS_ROTOR ** 2 + 0.003 ** 2),
                     izz=_m / 12 * (RADIUS_ROTOR ** 2 + 0.015 ** 2))
MOTOR_CONSTANT = 2.440724623743665e-04
MOMENT_CONSTANT = 0.044148079282817
TIME_CONSTANT_UP = 0.0125
TIME_CONSTANT_DOWN = 0.0125
MAX_ROT_VELOCITY = 667.0
ROTOR_DRAG = 8.06428e-05
ROLLING_MOMENT = 0.000001
THRUST_MULTIPLIER = 667.0           # ArduPilotPlugin cmd [0,1] -> rad/s reference (Noetic: 667)
SERVO_MIN, SERVO_MAX = 1000, 2000   # kopterworx_v432.params: MOT_PWM_MIN 1000, MOT_PWM_MAX 2000

# rotors motor_number, name, direction, position, ArduPilot channel (X quad: 1 FR ccw, 2 RL ccw, 3 FL cw, 4 RR cw)
# ArduPilot channel -> rotors motor number follows the classic fork publish order [c0, c2, c1, c3].
ROTORS = [
    (0, "front_right", "ccw", ( RX, -RY, RZ), 0),
    (1, "front_left",  "cw",  ( RX,  RY, RZ), 2),
    (2, "back_left",   "ccw", (-RX,  RY, RZ), 1),
    (3, "back_right",  "cw",  (-RX, -RY, RZ), 3),
]

def inertia_xml(d):
    return "".join(f"<{k}>{v:.8g}</{k}>" for k, v in d.items())

def rotor_link(i, name, direction, pos, ch):
    x, y, z = pos
    color = "1 0 0 1" if direction == "cw" else "0 0 1 1"
    return f"""
    <!-- rotor {i}: {name}, {direction}, ArduPilot channel {ch} -->
    <link name="rotor_{i}">
      <pose>{x:.5f} {y:.5f} {z:.5f} 0 0 0</pose>
      <inertial>
        <mass>{MASS_ROTOR}</mass>
        <inertia>{inertia_xml(ROTOR_INERTIA)}<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia>
      </inertial>
      <collision name="rotor_{i}_collision">
        <geometry><cylinder><radius>{RADIUS_ROTOR}</radius><length>0.005</length></cylinder></geometry>
      </collision>
      <visual name="rotor_{i}_visual">
        <geometry><mesh><scale>{PROP_SCALE} {PROP_SCALE} {PROP_SCALE}</scale>
          <uri>package://kopterworx_gz/models/kopterworx/meshes/propeller_{direction}.dae</uri></mesh></geometry>
        <material><ambient>{color}</ambient><diffuse>{color}</diffuse></material>
      </visual>
    </link>
    <joint name="rotor_{i}_joint" type="revolute">
      <child>rotor_{i}</child>
      <parent>base_link</parent>
      <axis>
        <xyz>0 0 1</xyz>
        <limit><lower>-1e+16</lower><upper>1e+16</upper></limit>
        <dynamics><damping>0.004</damping></dynamics>
      </axis>
    </joint>
    <plugin filename="gz-sim-multicopter-motor-model-system" name="gz::sim::systems::MulticopterMotorModel">
      <robotNamespace>kopterworx</robotNamespace>
      <jointName>rotor_{i}_joint</jointName>
      <linkName>rotor_{i}</linkName>
      <turningDirection>{direction}</turningDirection>
      <timeConstantUp>{TIME_CONSTANT_UP}</timeConstantUp>
      <timeConstantDown>{TIME_CONSTANT_DOWN}</timeConstantDown>
      <maxRotVelocity>{MAX_ROT_VELOCITY}</maxRotVelocity>
      <motorConstant>{MOTOR_CONSTANT}</motorConstant>
      <momentConstant>{MOMENT_CONSTANT}</momentConstant>
      <commandSubTopic>command/motor_speed</commandSubTopic>
      <actuator_number>{ch}</actuator_number>
      <rotorDragCoefficient>{ROTOR_DRAG}</rotorDragCoefficient>
      <rollingMomentCoefficient>{ROLLING_MOMENT}</rollingMomentCoefficient>
      <motorSpeedPubTopic>motor_speed/{i}</motorSpeedPubTopic>
      <rotorVelocitySlowdownSim>{ROTOR_SLOWDOWN}</rotorVelocitySlowdownSim>
      <motorType>velocity</motorType>
    </plugin>"""

def control(ch, joint):
    return f"""
      <control channel="{ch}">
        <jointName>{joint}</jointName>
        <type>ACTUATOR</type>
        <multiplier>{THRUST_MULTIPLIER}</multiplier>
        <offset>0</offset>
        <servo_min>{SERVO_MIN}</servo_min>
        <servo_max>{SERVO_MAX}</servo_max>
      </control>"""

# ---- sensors (classic: cam macro, front_facing_camera origin 0.2 0 0.05, depth camera 640x480 30 Hz;
#      velodyne LiDAR-X: 440 samples, 16 lasers, 10 Hz, 1..50 m, origin 0.08 0 -0.1578 rpy -pi 0.1323 0) ----
CAMERA_XML = "" if ARGS.no_camera else """
    <link name="camera_link">
      <pose>0.2 0 0.05 0 0 0</pose>
      <inertial><mass>1e-5</mass><inertia><ixx>1e-12</ixx><ixy>0</ixy><ixz>0</ixz><iyy>1e-12</iyy><iyz>0</iyz><izz>1e-12</izz></inertia></inertial>
      <visual name="camera_visual"><geometry><box><size>0.05 0.05 0.05</size></box></geometry></visual>
      <sensor name="camera" type="rgbd_camera">
        <gz_frame_id>camera_link</gz_frame_id>
        <update_rate>30</update_rate>
        <always_on>1</always_on>
        <camera name="head">
          <horizontal_fov>1.3962634</horizontal_fov>
          <image><width>640</width><height>480</height></image>
          <clip><near>0.02</near><far>300</far></clip>
          <noise><type>gaussian</type><mean>0.0</mean><stddev>0.007</stddev></noise>
          <depth_camera><clip><near>0.1</near><far>10</far></clip></depth_camera>
        </camera>
      </sensor>
    </link>
    <joint name="camera_joint" type="fixed"><parent>base_link</parent><child>camera_link</child></joint>"""
LIDAR_XML = "" if not ARGS.lidar else """
    <link name="lidar_link">
      <pose>0.08 0 -0.1578 -3.141592653589793 0.1323284641020683 0</pose>
      <inertial><mass>1e-5</mass><inertia><ixx>1e-12</ixx><ixy>0</ixy><ixz>0</ixz><iyy>1e-12</iyy><iyz>0</iyz><izz>1e-12</izz></inertia></inertial>
      <sensor name="lidar" type="gpu_lidar">
        <gz_frame_id>lidar_link</gz_frame_id>
        <topic>lidar</topic>
        <update_rate>10</update_rate>
        <always_on>1</always_on>
        <lidar>
          <scan>
            <horizontal><samples>440</samples><resolution>1</resolution><min_angle>-3.141592653589793</min_angle><max_angle>3.141592653589793</max_angle></horizontal>
            <vertical><samples>16</samples><resolution>1</resolution><min_angle>-0.2617993877991494</min_angle><max_angle>0.2617993877991494</max_angle></vertical>
          </scan>
          <range><min>1.0</min><max>50.0</max><resolution>0.01</resolution></range>
          <noise><type>gaussian</type><mean>0.0</mean><stddev>0.008</stddev></noise>
        </lidar>
      </sensor>
    </link>
    <joint name="lidar_joint" type="fixed"><parent>base_link</parent><child>lidar_link</child></joint>"""

bx, by, bz = BODY_BOX
rotors_xml = "".join(rotor_link(*r) for r in ROTORS)
controls_xml = "".join(control(ch, f"rotor_{i}_joint") for i, _, _, _, ch in sorted(ROTORS, key=lambda r: r[4]))
sdf = f"""<?xml version="1.0"?>
<!-- GENERATED by scripts/gen_model.py, edit that file. Step 3.2/3.3 kopterworx on the motor model path. -->
<sdf version="1.9">
  <model name="kopterworx">
    <pose>0 0 0 0 0 0</pose>
    <link name="base_link">
      <inertial>
        <mass>{MASS}</mass>
        <inertia>{inertia_xml(BODY_INERTIA)}</inertia>
      </inertial>
      <collision name="base_collision">
        <geometry><box><size>{bx} {by} {bz}</size></box></geometry>
        <surface>
          <contact><ode><max_vel>100.0</max_vel><min_depth>0.001</min_depth></ode></contact>
          <friction><ode><mu>100000.0</mu><mu2>100000.0</mu2></ode></friction>
        </surface>
      </collision>
      <visual name="base_visual">
        <geometry><mesh><scale>{MESH_SCALE} {MESH_SCALE} {MESH_SCALE}</scale>
          <uri>package://kopterworx_gz/models/kopterworx/meshes/kopterworx_model_simple.dae</uri></mesh></geometry>
      </visual>
      <sensor name="air_pressure_sensor" type="air_pressure"><always_on>1</always_on><update_rate>30</update_rate></sensor>
      <sensor name="magnetometer_sensor" type="magnetometer"><always_on>1</always_on><update_rate>30</update_rate></sensor>
      <sensor name="navsat_sensor" type="navsat"><always_on>1</always_on><update_rate>30</update_rate></sensor>
    </link>
    <!-- IMU on its own link like the upstream iris (sensor rolled 180 deg, see plugin frame conversion) -->
    <link name="imu_link">
      <inertial>
        <mass>0.01</mass>
        <inertia><ixx>0.001</ixx><ixy>0</ixy><ixz>0</ixz><iyy>0.001</iyy><iyz>0</iyz><izz>0.001</izz></inertia>
      </inertial>
      <sensor name="imu_sensor" type="imu">
        <gz_frame_id>imu_link</gz_frame_id>
        <pose degrees="true">0 0 0 180 0 0</pose>
        <always_on>1</always_on>
        <update_rate>1000.0</update_rate>
      </sensor>
    </link>
    <joint name="imu_joint" type="revolute">
      <child>imu_link</child>
      <parent>base_link</parent>
      <axis><xyz>0 0 1</xyz><limit><lower>0</lower><upper>0</upper><effort>0</effort><velocity>0</velocity></limit>
        <dynamics><damping>1.0</damping></dynamics></axis>
    </joint>
{rotors_xml}
{CAMERA_XML}
{LIDAR_XML}

    <!-- ground truth odometry, bridged to /odometry (nav_msgs/Odometry) -->
    <plugin filename="gz-sim-odometry-publisher-system" name="gz::sim::systems::OdometryPublisher">
      <odom_frame>map</odom_frame>
      <robot_base_frame>base_link</robot_base_frame>
      <dimensions>3</dimensions>
      <odom_publish_frequency>50</odom_publish_frequency>
      <odom_topic>/model/kopterworx/odometry</odom_topic>
    </plugin>
    <plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher"/>

    <plugin name="ArduPilotPlugin" filename="ArduPilotPlugin">
      <fdm_addr>127.0.0.1</fdm_addr>
      <fdm_port_in>9002</fdm_port_in>
      <connectionTimeoutMaxCount>5</connectionTimeoutMaxCount>
      <lock_step>1</lock_step>
      <no_time_sync>1</no_time_sync>
      <have_32_channels>0</have_32_channels>
      <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
      <gazeboXYZToNED degrees="true">0 0 0 180 0 90</gazeboXYZToNED>
      <imuName>imu_link::imu_sensor</imuName>
      <!-- motor commands as one gz.msgs.Actuators, index = channel, for the MulticopterMotorModel systems -->
      <actuators_topic>/kopterworx/command/motor_speed</actuators_topic>{controls_xml}
    </plugin>
  </model>
</sdf>
"""
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "kopterworx", "model.sdf")
open(out, "w").write(sdf)
hover_w = math.sqrt(MASS * 9.81 / 4 / MOTOR_CONSTANT)
print(f"wrote {os.path.normpath(out)} (camera={'off' if ARGS.no_camera else 'on'}, lidar={'on' if ARGS.lidar else 'off'}); predicted hover rotor speed {hover_w:.0f} rad/s = cmd {hover_w / THRUST_MULTIPLIER:.3f}")
