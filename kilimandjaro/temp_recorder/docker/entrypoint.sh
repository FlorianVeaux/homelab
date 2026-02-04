#!/bin/bash

service dbus start
service bluetooth start
sleep 5
bluetoothctl -- power on
sleep 3
python3 /app/listen.py
