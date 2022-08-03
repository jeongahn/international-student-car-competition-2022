#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import math 
import rospy
import rospkg
import sys
import os
import signal
from nav_msgs.msg import Path,Odometry
from std_msgs.msg import Bool
from geometry_msgs.msg import PoseStamped,Point
import tf
from morai_msgs.msg import EgoVehicleStatus, CtrlCmd

def signal_handler(sig, frame):
    os.system('killall -9 python rosout')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Parameters
k = 0.15  # look forward gain
Lfc = 3.0 # [m] look-ahead distance
Kp = 1.0  # speed proportional gain
WB = 0.78  # [m] wheel base of vehicle

target_speed = 10
current_v = 6

present_x = 0
present_y = 0
present_yaw = 0

path_x = []
path_y = []

current_index = 0
previous_index = 0

txt_line_cnt = 0

is_one_lap_finished = False


status_msg=EgoVehicleStatus()

def statusCB(data):
    global status_msg
    status_msg=data
    # print(status_msg)
    br = tf.TransformBroadcaster()
    br.sendTransform((status_msg.position.x, status_msg.position.y, status_msg.position.z),
                    tf.transformations.quaternion_from_euler(0, 0, status_msg.heading/180*math.pi),
                    rospy.Time.now(),
                    "gps",
                    "map")
    is_status=True 

class State:

    def __init__(self, x = 0, y = 0, yaw = 0, v = current_v):
        self.x = x
        self.y = y
        self.yaw = yaw
        self.v = v
        self.rear_x = self.x - ((WB / 2) * math.cos(self.yaw))
        self.rear_y = self.y - ((WB / 2) * math.sin(self.yaw))

    def calc_distance(self, point_x, point_y):
        dx = self.rear_x - point_x
        dy = self.rear_y - point_y

        return math.hypot(dx, dy)

def proportional_control(target, current):
    a = Kp * (target - current)

    return a


class TargetCourse:

    def __init__(self, cx, cy):
        self.cx = cx
        self.cy = cy
        self.old_nearest_point_index = None
 

    def search_target_index(self, state):
        global txt_line_cnt
        # To speed up nearest point search, doing it at only first time.  
        if self.old_nearest_point_index is None:
            dx = [state.rear_x - icx for icx in self.cx]
            dy = [state.rear_y - icy for icy in self.cy]

            d = np.hypot(dx, dy)

            ind = np.argmin(d)
            self.old_nearest_point_index = ind

        else:
            ind = self.old_nearest_point_index

            distance_this_index = state.calc_distance(self.cx[ind], self.cy[ind])
            while True:
                distance_next_index = state.calc_distance(self.cx[ind + 1], self.cy[ind + 1])

                if distance_this_index < distance_next_index + 1:
                    break
                
                if (ind + 1) < len(self.cx):
                    ind = ind + 1
                else:
                    ind = ind 

                distance_this_index = distance_next_index
            self.old_nearest_point_index = ind

        
        # print(state.v)
        # print(current_v)
        Lf = k * current_v + Lfc  # update look ahead distance


        # search look ahead target point index
        while Lf > state.calc_distance(self.cx[ind], self.cy[ind]):
            if (ind + 1) >= len(self.cx):
                break  # not exceed goal
            ind += 1

        print("LF:", Lf)

        return ind, Lf


def pure_pursuit_steer_control(state, trajectory, pind):
    ind, Lf = trajectory.search_target_index(state)

    if pind >= ind:
        ind = pind

    if ind < len(trajectory.cx):
        tx = trajectory.cx[ind]
        ty = trajectory.cy[ind]
    else:  # toward goal
        tx = trajectory.cx[-1]
        ty = trajectory.cy[-1]
        ind = len(trajectory.cx) - 1

    alpha = math.atan2(ty - state.rear_y, tx - state.rear_x) - state.yaw

    delta = math.atan2(2.0 * WB * math.sin(alpha) / Lf, 0.8) # 0.75 #/ Lf, 1.4)

    return delta, ind, tx, ty


def findLocalPath(path_x, path_y, state_x, state_y): ## global_path와 차량의 status_msg를 이용해 현재waypoint와 local_path를 생성 ##
    global current_index, previous_index, txt_line_cnt

    # if (current_index >= txt_line_cnt- 3 and txt_line_cnt < len(path_x)):
    #     txt_line_cnt += txt_line_cnt
    #     print(txt_line_cnt,"#################################")

    current_x = state_x
    current_y = state_y
    min_dis = float('inf')

    for i in range(txt_line_cnt) :
        dx = current_x - path_x[i]
        dy = current_y - path_y[i]
        dis = math.sqrt(dx*dx + dy*dy)
        if dis < min_dis :
            min_dis = dis
            current_index = i
    # previous_index = current_index

    if current_index == txt_line_cnt:
        current_index = 0

def one_lap_flag_callback(data):
    global is_one_lap_finished
    is_one_lap_finished = data.data


if __name__ == '__main__':
    rospy.init_node("pure_pursuit", anonymous=True)

    rospy.Subscriber("/Ego_topic", EgoVehicleStatus, statusCB)
    rospy.Subscriber("/is_one_lap_finished", Bool, one_lap_flag_callback)

    motor_pub = rospy.Publisher("/ctrl_cmd", CtrlCmd, queue_size = 1)
    drive_value = CtrlCmd()

    drive_value.longlCmdType = 2

    rate = rospy.Rate(60)

    while is_one_lap_finished == False:
        continue

    # Path Setting
    f = open('/home/foscar/ISCC_2022/src/erp_ros/path/gps_track_path.txt' , mode = 'r')

    line = f.readline()
    first_line = line.split()
    path_x.append(float(first_line[0]))
    path_y.append(float(first_line[1]))

    while line:
        line = f.readline()
        tmp = line.split()

        txt_line_cnt += 1

        if len(tmp) != 0:
            path_x.append(float(tmp[0]))
            path_y.append(float(tmp[1]))
    f.close()
    
    print(txt_line_cnt, "///", len(path_x), "///", len(path_y))
    path_x *= 2
    path_y *= 2
    
    # initial statecurrent_v

    while not rospy.is_shutdown():
        print("GPS RUN")
        state = State(x = status_msg.position.x, y = status_msg.position.y, yaw = status_msg.heading/180*math.pi, v = current_v)

        findLocalPath(path_x, path_y, state.x, state.y)

        print(current_index)

        if len(path_x) != 0:
            # Calc control input
            target_course = TargetCourse(path_x, path_y)
            target_ind, _ = target_course.search_target_index(state)
            
            ai = proportional_control(target_speed, current_v)
            di, target_ind, target_x, target_y = pure_pursuit_steer_control(state, target_course, target_ind)
            # state.update(ai, di)  # Control vehicle

            print("di = ", di)

            if abs(di) > 0.175:
                current_v = 7      #7
            elif abs(di) > 0.08:
                current_v = 9     #12.5
            elif abs(di) > 0.04:
                current_v = 11      #15
            else:
                current_v = 18

            drive_value.velocity = current_v
            drive_value.steering = di

            print(drive_value.velocity)

            motor_pub.publish(drive_value)


        rate.sleep()