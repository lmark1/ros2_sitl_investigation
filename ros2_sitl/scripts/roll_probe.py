#!/usr/bin/env python3
"""Sample ground-truth roll (Gazebo /odometry) and motor PWM (/mavros/rc/out) at 5 Hz."""
import math, sys, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from mavros_msgs.msg import RCOut
from geometry_msgs.msg import TwistStamped

class P(Node):
    def __init__(self):
        super().__init__("roll_probe"); self.o=None; self.r=None; self.v=None
        be=QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(Odometry,"/odometry",lambda m:setattr(self,"o",m),be)
        self.create_subscription(RCOut,"/mavros/rc/out",lambda m:setattr(self,"r",m),be)
def main():
    rclpy.init(); n=P(); t0=time.time(); nxt=0.0; dur=float(sys.argv[1]) if len(sys.argv)>1 else 12
    while time.time()-t0<dur:
        rclpy.spin_once(n,timeout_sec=0.02); t=time.time()-t0
        if t>=nxt and n.o and n.r:
            q=n.o.pose.pose.orientation; p=n.o.pose.pose.position; w=n.o.twist.twist
            roll=math.degrees(math.atan2(2*(q.w*q.x+q.y*q.z),1-2*(q.x*q.x+q.y*q.y)))
            pw=n.r.channels[:4]
            print(f"t={t:5.2f} roll_gt={roll:6.2f} p_gt={math.degrees(w.angular.x):7.2f}deg/s vy_gt={w.linear.y:6.3f} y_gt={p.y:6.3f} right(1,4)={pw[0]},{pw[3]} left(2,3)={pw[1]},{pw[2]} diffR-L={(pw[0]+pw[3]-pw[1]-pw[2])//2}",flush=True)
            nxt+=0.2
    rclpy.shutdown()
main()
