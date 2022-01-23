###############################################################
#                      __        ____       __
#    _________  ____ _/ /_____  / __ \___  / /___ ___  __
#   / ___/ __ \/ __ `/ //_/ _ \/ /_/ / _ \/ / __ `/ / / /
#  (__  ) / / / /_/ / ,< /  __/ _, _/  __/ / /_/ / /_/ /
# /____/_/ /_/\__,_/_/|_|\___/_/ |_|\___/_/\__,_/\__, /
#                                               /____/
#
###############################################################
# Filename: snakeRelay.py
# Author: Jonas Werner (https://jonamiki.com)
# Version: 3.0
###############################################################

import os
import glob
import time
import json
import redis
from influxdb import InfluxDBClient
from datetime import datetime
import RPi.GPIO as GPIO

debug = 0

# Set mode, warnings and relay control pins to output
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(17,GPIO.OUT) # Relay 1
GPIO.setup(24,GPIO.OUT) # Relay 2
GPIO.setup(8,GPIO.OUT)  # Relay 3
GPIO.setup(7,GPIO.OUT)  # Relay 4

# Set default relay states
GPIO.output(17,GPIO.HIGH)   # R1 / hotZoneMat
GPIO.output(24,GPIO.HIGH)   # R2 / heatLamp
GPIO.output(8,GPIO.HIGH)    # R3 / side and bottom heat mats
GPIO.output(7,GPIO.HIGH)    # R4 / light switch

# Mapping of relay to GPIO pin value
relays = {
    'DS18b20_hotZoneMat': 17,
    'DHT22_AirTemp': 24,
    'DS18b20_midBack': 8,
    'r4': 7
    }

# InfluxDB connection information
host        =   "127.0.0.1"
port        =   "8086"
user        =   "someuser"
password    =   "somepass"
dbname      =   "somedb"

# Redis connection details
redisHost   =   "127.0.0.1"
redisPort   =   "6379"

# Initialize sensor data variables
sensor  = ""
sensors = ""

def influxDBconnect():
   influxDBConnection = InfluxDBClient(host, port, user, password, dbname)
   return influxDBConnection


def redisDBconnect():
   redisDBConnection = redis.Redis(host=redisHost, port=redisPort, charset="utf-8", decode_responses=True)
   return redisDBConnection


def influxDBmeasurements(sensors):
    sensors = influxDBConnection.get_list_measurements()
    return sensors

def influxDBwrite(sensorName, sensorValue):
   timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

   if debug:
       print(" ### Storing data into InfluxDB: %s: %s" % (sensorName, sensorValue))

   measurementData = [
       {
           "measurement": sensorName,
           "tags": {
               "gateway": "snakePi2",
               "location": "Tokyo"
           },
           "time": timestamp,
           "fields": {
               "State": sensorValue
           }
       }
   ]

   influxDBConnection.write_points(measurementData, time_precision='ms')


def heatControl(relay, desiredState):
    gpioState = ""

    if debug:
        print("Relay: %s, Setting state: %s" % (relay,desiredState))

    if desiredState == "on":
        GPIO.output(relays[relay],GPIO.HIGH)
        influxDBwrite("Relay_" + relay, 1)
    elif desiredState == "off":
        GPIO.output(relays[relay],GPIO.LOW)
        influxDBwrite("Relay_" + relay, 0)


if __name__ == "__main__":

    influxDBConnection = influxDBconnect()
    redisDBConnection  = redisDBconnect()

    # Get the list of sensors in InfluxDB
    sensors = influxDBmeasurements(sensors)

    while True:

        # Get the latest value for each sensor
        for sensor in sensors:
            sensor = str(sensor['name'])

            if not "Relay" in sensor:
                desired      = sensor + "Desired"
                # Float and int weirdness to avoid crashing if we get empty values from Redis
                currentValue = int(float(redisDBConnection.mget(sensor)[0] or 0))
                desiredValue = int(float(redisDBConnection.mget(desired)[0] or 0))

                # If the the value is one we care about
                if sensor in relays.keys():
                    # Write the current state of the relay to InfluxDB so it can be tracked
                    influxDBwrite("Relay_" + sensor, GPIO.input(relays[sensor]))

                    # If the actual value differs from what is desired
                    if currentValue < desiredValue:
                        # Check to see if the GPIO state is already what we want (could already be working on fixing the temp)
                        if not GPIO.input(relays[sensor]):
                            heatControl(sensor, "on")
                    elif currentValue > desiredValue:
                        if GPIO.input(relays[sensor]):
                            heatControl(sensor, "off")


                if debug:
                    print("Sensor %s: Currently %s, Desired: %s" % (sensor,currentValue,desiredValue))

        if debug:
            print("")

        time.sleep(15)
