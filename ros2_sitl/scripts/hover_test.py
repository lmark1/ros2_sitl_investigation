#!/usr/bin/env python3
"""Arm, take off in GUIDED through mavros, hover, report altitude and motor PWM.

Prints every second: z from /mavros/local_position/pose, z from Gazebo /odometry,
mean motor PWM from /mavros/rc/out (ch1-4) and its normalised value (pwm-1000)/1000,
which is the number to compare with the Noetic hover throttle. Then LAND.

  python3 hover_test.py [--alt 3] [--hover-s 15]
"""
import argparse, math, sys, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from mavros_msgs.msg import RCOut, State
from mavros_msgs.srv import CommandBool, CommandTOL, SetMode


class HoverTest(Node):
    def __init__(self, a):
        super().__init__("hover_test")
        self.a = a; self.state = None; self.pose = None; self.odom = None; self.rcout = None
        be = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(State, "/mavros/state", lambda m: setattr(self, "state", m), 10)
        self.create_subscription(PoseStamped, "/mavros/local_position/pose", lambda m: setattr(self, "pose", m), be)
        self.create_subscription(Odometry, "/odometry", lambda m: setattr(self, "odom", m), be)
        self.create_subscription(RCOut, "/mavros/rc/out", lambda m: setattr(self, "rcout", m), be)
        self.mode_cli = self.create_client(SetMode, "/mavros/set_mode")
        self.arm_cli = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.tol_cli = self.create_client(CommandTOL, "/mavros/cmd/takeoff")

    def spin(self, s):
        t0 = time.time()
        while time.time() - t0 < s:
            rclpy.spin_once(self, timeout_sec=0.05)

    def wait(self, cond, timeout, what):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
            if cond(): return True
        print(f"timeout waiting for {what}"); return False

    def call(self, cli, req, what):
        if not cli.wait_for_service(timeout_sec=5.0): print(f"{what}: no service"); return None
        f = cli.call_async(req); rclpy.spin_until_future_complete(self, f, timeout_sec=5.0)
        print(f"{what}: {f.result()}"); return f.result()

    def rpy(self):
        q = self.pose.pose.orientation
        r = math.atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x * q.x + q.y * q.y))
        p = math.asin(max(-1.0, min(1.0, 2 * (q.w * q.y - q.z * q.x))))
        y = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        return tuple(math.degrees(v) for v in (r, p, y))

    def status(self, t, tag):
        x = self.pose.pose.position.x if self.pose else float("nan")
        y = self.pose.pose.position.y if self.pose else float("nan")
        r, pch, yw = self.rpy() if self.pose else (float("nan"),) * 3
        z = self.pose.pose.position.z if self.pose else float("nan")
        zg = self.odom.pose.pose.position.z if self.odom else float("nan")
        if self.odom:
            q = self.odom.pose.pose.orientation
            rg = math.degrees(math.atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x * q.x + q.y * q.y)))
            gt = f"gt=({self.odom.pose.pose.position.x:5.2f},{self.odom.pose.pose.position.y:5.2f},{zg:5.2f} r={rg:5.1f})"
        else:
            gt = "gt=n/a"
        if self.rcout and len(self.rcout.channels) >= 4:
            pw = self.rcout.channels[:4]; mean = sum(pw) / 4.0
            pwm = f"pwm={list(pw)} mean={mean:.0f} norm={(mean-1000)/1000:.3f}"
        else:
            pwm = "pwm=n/a"
        print(f"t={t:5.1f}s {tag:6s} xyz=({x:5.2f},{y:5.2f},{z:5.2f}) {gt} rpy=({r:5.1f},{pch:5.1f},{yw:6.1f}) {pwm} {self.state.mode} armed={self.state.armed}", flush=True)

    def run(self):
        a = self.a
        if not self.wait(lambda: self.state and self.state.connected, 30, "FCU"): return 1
        self.wait(lambda: self.pose is not None, 30, "pose")
        self.call(self.mode_cli, SetMode.Request(custom_mode="GUIDED"), "set_mode GUIDED")
        self.wait(lambda: self.state.mode == "GUIDED", 5, "GUIDED")
        self.call(self.arm_cli, CommandBool.Request(value=True), "arm")
        if not self.wait(lambda: self.state.armed, 5, "armed"): return 1
        self.spin(2.0)
        self.call(self.tol_cli, CommandTOL.Request(altitude=float(a.alt)), f"takeoff {a.alt}")
        t0 = time.time(); nxt = 0.0; hover_norm = []
        while time.time() - t0 < a.climb_s + a.hover_s:
            rclpy.spin_once(self, timeout_sec=0.05)
            t = time.time() - t0
            if t >= nxt:
                self.status(t, "climb" if t < a.climb_s else "hover"); nxt += 1.0
                if t >= a.climb_s and self.rcout and len(self.rcout.channels) >= 4:
                    hover_norm.append((sum(self.rcout.channels[:4]) / 4.0 - 1000) / 1000)
        if hover_norm:
            print(f"HOVER mean normalised motor output: {sum(hover_norm)/len(hover_norm):.3f} over {len(hover_norm)} samples", flush=True)
        self.call(self.mode_cli, SetMode.Request(custom_mode="LAND"), "set_mode LAND")
        tl = time.time()
        while time.time() - tl < 30 and self.state.armed:
            rclpy.spin_once(self, timeout_sec=0.1)
        self.status(time.time() - t0, "end")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt", type=float, default=3.0)
    ap.add_argument("--climb-s", type=float, default=10.0)
    ap.add_argument("--hover-s", type=float, default=15.0)
    a = ap.parse_args()
    rclpy.init(); n = HoverTest(a)
    try: rc = n.run()
    finally: n.destroy_node(); rclpy.shutdown()
    sys.exit(rc)

if __name__ == "__main__":
    main()
