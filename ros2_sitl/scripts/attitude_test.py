#!/usr/bin/env python3
"""Step 2 test: drive SITL through mavros2 the way uav_ros_control does.

GUIDED_NOGPS, arm, then AttitudeTarget on /mavros/setpoint_raw/attitude at 50 Hz with
the stack's type_mask (IGNORE_ROLL_RATE + IGNORE_PITCH_RATE = 3: attitude quaternion
plus body yaw rate) and the thrust field. Phases: climb, pitch forward, yaw rate,
hover, then LAND. Prints z, horizontal speed, yaw and mode every 0.5 s.

  ros2 run ... no: python3 attitude_test.py [--type-mask 3|7] [--thrust-climb 0.7]
"""
import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import AttitudeTarget, OverrideRCIn, State
from mavros_msgs.srv import CommandBool, SetMode


def quaternion_from_euler(roll, pitch, yaw):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def yaw_from_quaternion(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class AttitudeTest(Node):
    def __init__(self, args):
        super().__init__("attitude_test")
        self.args = args
        self.state = None
        self.pose = None
        self.vel = None
        sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                                history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(State, "/mavros/state", self._on_state, 10)
        self.create_subscription(PoseStamped, "/mavros/local_position/pose", self._on_pose, sensor_qos)
        self.create_subscription(TwistStamped, "/mavros/local_position/velocity_local", self._on_vel, sensor_qos)
        self.pub = self.create_publisher(AttitudeTarget, "/mavros/setpoint_raw/attitude", 10)
        self.rc_pub = self.create_publisher(OverrideRCIn, "/mavros/rc/override", 10)
        self.mode_cli = self.create_client(SetMode, "/mavros/set_mode")
        self.arm_cli = self.create_client(CommandBool, "/mavros/cmd/arming")

    def _on_state(self, m): self.state = m
    def _on_pose(self, m): self.pose = m
    def _on_vel(self, m): self.vel = m

    def wait(self, cond, timeout, what):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
            if cond():
                return True
        print(f"timeout waiting for {what}")
        return False

    def call(self, cli, req, what):
        if not cli.wait_for_service(timeout_sec=5.0):
            print(f"{what}: service not available"); return None
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=5.0)
        print(f"{what}: {fut.result()}")
        return fut.result()

    def yaw(self):
        q = self.pose.pose.orientation
        return yaw_from_quaternion(q.x, q.y, q.z, q.w)

    def status(self, t, phase):
        p = self.pose.pose.position
        v = self.vel.twist.linear if self.vel else None
        hs = math.hypot(v.x, v.y) if v else float("nan")
        print(f"t={t:5.1f}s {phase:14s} z={p.z:6.2f} hspd={hs:5.2f} yaw={math.degrees(self.yaw()):7.1f} "
              f"mode={self.state.mode} armed={self.state.armed}", flush=True)

    def run(self):
        a = self.args
        if not self.wait(lambda: self.state is not None and self.state.connected, 30, "FCU connection"): return 1
        if not self.wait(lambda: self.pose is not None, 30, "local_position/pose"): return 1
        if a.rc_throttle > 0:
            rc = OverrideRCIn(); rc.channels = [0] * 18; rc.channels[2] = a.rc_throttle
            for _ in range(20):
                self.rc_pub.publish(rc); rclpy.spin_once(self, timeout_sec=0.05)
            print(f"publishing RC override ch3={a.rc_throttle}")
        self.call(self.mode_cli, SetMode.Request(custom_mode="GUIDED_NOGPS"), "set_mode GUIDED_NOGPS")
        self.wait(lambda: self.state.mode == "GUIDED_NOGPS", 5, "mode GUIDED_NOGPS")
        self.call(self.arm_cli, CommandBool.Request(value=True), "arm")
        self.wait(lambda: self.state.armed, 5, "armed")

        yaw0 = self.yaw()
        phases = [  # (name, duration s, roll deg, pitch deg, yaw_rate rad/s, thrust)
            ("climb",   a.climb_s, 0.0, 0.0, 0.0, a.thrust_climb),
            ("pitch-5", 5.0,       0.0, -5.0, 0.0, a.thrust_hover),
            ("yawrate",  5.0,      0.0, 0.0, 0.5, a.thrust_hover),
            ("hover",    5.0,      0.0, 0.0, 0.0, a.thrust_hover),
        ]
        msg = AttitudeTarget()
        msg.type_mask = a.type_mask
        period = 1.0 / a.rate
        t_start = time.time()
        next_log = 0.0
        yaw_cmd = yaw0
        for name, dur, roll, pitch, yaw_rate, thrust in phases:
            t_phase = time.time()
            while time.time() - t_phase < dur:
                t = time.time() - t_start
                if a.type_mask == 7 and yaw_rate != 0.0:
                    yaw_cmd += yaw_rate * period  # yaw rate through the quaternion instead
                q = quaternion_from_euler(math.radians(roll), math.radians(pitch), yaw_cmd if a.type_mask == 7 else yaw0)
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w = q
                msg.body_rate.x = 0.0; msg.body_rate.y = 0.0; msg.body_rate.z = yaw_rate
                msg.thrust = thrust
                self.pub.publish(msg)
                if a.rc_throttle > 0:
                    self.rc_pub.publish(rc)
                rclpy.spin_once(self, timeout_sec=0.0)
                if t >= next_log:
                    self.status(t, name); next_log += 0.5
                time.sleep(period)
        self.call(self.mode_cli, SetMode.Request(custom_mode="LAND"), "set_mode LAND")
        t_land = time.time()
        while time.time() - t_land < 20 and self.state.armed:
            rclpy.spin_once(self, timeout_sec=0.1)
            t = time.time() - t_start
            if t >= next_log:
                self.status(t, "land"); next_log += 1.0
        self.status(time.time() - t_start, "end")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type-mask", type=int, default=3, help="3 = stack (att + yaw rate), 7 = attitude only")
    ap.add_argument("--rate", type=float, default=50.0)
    ap.add_argument("--climb-s", type=float, default=8.0)
    ap.add_argument("--thrust-climb", type=float, default=0.7)
    ap.add_argument("--thrust-hover", type=float, default=0.5)
    ap.add_argument("--rc-throttle", type=int, default=0, help="if >0, publish this PWM on RC ch3 via /mavros/rc/override")
    args = ap.parse_args()
    rclpy.init()
    node = AttitudeTest(args)
    try:
        rc = node.run()
    finally:
        node.destroy_node(); rclpy.shutdown()
    sys.exit(rc)


if __name__ == "__main__":
    main()
