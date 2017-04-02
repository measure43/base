#!/bin/bash
python chat_room_43_server_j.py &
sleep 1
jython chat_room_43_client_j.py &
jython chat_room_43_client_j.py &