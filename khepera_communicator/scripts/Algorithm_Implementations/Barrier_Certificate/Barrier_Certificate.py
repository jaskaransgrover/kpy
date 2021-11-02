#!/usr/bin/env python
# license removed for brevity

import rospy
import math
import time
import rosnode
# Import message file
from std_msgs.msg import String
from khepera_communicator.msg import K4_controls, SensorReadings
from geometry_msgs.msg import TransformStamped
import numpy as np
from qpsolvers import solve_qp

start = time.time()

rospy.init_node('Central_Algorithm', anonymous=True)

# Get all the node names for all the currently running K4_Send_Cmd nodes (all running Kheperas)
# Get the node names of all the current running nodes
node_list = rosnode.get_node_names()

# Find the nodes that contains the "K4_Send_Cmd_" title
khep_node_list = [s for s in node_list if "K4_Send_Cmd_" in s]
ip_num_list = [x[13:16] for x in khep_node_list]
khep_node_cnt = len(khep_node_list)

# Establish all the publishers to each "K4_controls_" topic, corresponding to each K4_Send_Cmd node, which corresponds to each Khepera robot
pub = []
for i in range(khep_node_cnt):
	pub.append(rospy.Publisher('K4_controls_' + str(ip_num_list[i]), K4_controls, queue_size = 10))

def quaternion_to_euler(x, y, z, w):

    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(t0, t1)
    t2 = +2.0 * (w * y - z * x)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    pitch = math.asin(t2)
    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(t3, t4)
    return yaw


def control_for_one_robot(x, y, theta):
	# Written by Jaskaran Singh Grover
	d    	= 0.06 											# Radius of robot
	z1 		= x + (d * np.cos(theta)) 						# x cooordinate of a point on robots xb axis at a distance d units away
	z2 		= y + (d * np.sin(theta)) 						# y coordinate of a point on robots xb axis at a distnace d units away
	xo 		= 0.5 											# x coordinate of center of circulate obstacle
	yo 		= 0 											# y coordinate of center of circular obstacle
	xd 		= -0.5 											# x coordinate of desired goal position
	yd 		= 0 											# y coordinate of desired goal position
	kp 		= 1 											# Proportional gain
	gamma 	= 3 											# Factor
	hval  	= ((z1 - xo) ** 2 + (z2 - yo) ** 2) - 0.25 		# 1 is the radius of circular obstacle, h represents square of distance of (z1,z2) from obstacle's center
	A  		= np.array([-2 * (z1 - xo), -2 * (z2 - yo)]) 	# Supposed to be a row vector, np array
	b  		= gamma * hval**3 								# Right hand side of barrier equation
	u1cap 	= -kp * (z1 - xd) 								# Proportional controller for z1 coordinate to make z1 stabilize to xd, should be a scalar, this is control without regarding obstacles
	u2cap 	= -kp * (z2 - yd) 								# Proportional controller for z2 coordinate to make z2 stabilize to yd, should be a scalar, this is control without regarding obstacles
	P 		= np.array([[2.0, 0.0],[0.0, 2.0]]) 			# Identity matrix of size 2 by 2 because we have two controls
	q       = np.array([-2.0*u1cap,-2.0*u2cap])				# -2*ucap
	r1      = np.array([[1.0,0.0],[0.0,1.0],[-1.0,0.0],[0.0,-1.0]])
	G       = np.vstack([A,r1])								# A is for collision avoidance constraint, r1 is for explicit constraint on bounds
	ub      = np.array([1.0,1.0])							# Maximum allowable speed
	h 		= np.array([b, ub[0], ub[1], ub[0], ub[1]])		# Second thing is also ub because we want the lower bound to be negative of upper bound
	R  		= np.array([[np.cos(theta), -np.sin(theta)],[np.sin(theta), np.cos(theta)]]) # rotation matrix of size 2 by 2
	D  		= np.array([[1.0, 0.0], [0.0, d]]) 				# Diagonal matrix of size 2 by 2
	J  		= np.matmul(R,D)
	M       = np.linalg.inv(J)

	ustar 	= solve_qp(P,q,G,h) 							# Quadratic programming solver
	urobot 	= np.matmul(M,ustar)
	
	V = urobot[0]
	W = urobot[1]


	#######################
	print(A)
	print(b)
	print(G)
	print(h)
	print(np.size(A))
	print(np.size(b))


	return V, W



# This callback function is where the centralized swarm algorithm, or any algorithm should be
# data is the info subscribed from the vicon node, contains the global position, velocity, etc
# the algorithm placed inside this callback should be published to the K4_controls topics
# which should have the K4_controls message type:
# Angular velocity: ctrl_W
# Linear velocity: ctrl_V
def callback(data, args):
	control_msgs = K4_controls()

	theta = quaternion_to_euler(data.transform.rotation.x, data.transform.rotation.y, data.transform.rotation.z, data.transform.rotation.w)
	V, W = control_for_one_robot(data.transform.translation.x, data.transform.translation.y, theta)

	# Convert to mm per sec for the khepera	
	control_msgs.ctrl_V = V * 1000
	control_msgs.ctrl_W = W
	
	# Publishing
	#rospy.loginfo(control_msgs)
	pub[i].publish(control_msgs)

def central():
	# Set up the Subscribers
	sub = []
	for i in range(khep_node_cnt):
		# Automatically subscribes to existing vicon topics corresponding to each khepera
		sub.append(rospy.Subscriber('vicon/k' + ip_num_list[i] + '/k' + ip_num_list[i], TransformStamped, callback, i ))

	# Spin to loop all callback functions
	rospy.spin()

if __name__ == '__main__':
	try:
		central()
	except rospy.ROSInterruptException:
		pass