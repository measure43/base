# #!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Room 43: Client. v. 0.0.1

Python 2.7+/3.4+ chat client program.

Used to send or receive text messages over the TCP/IP network.

Copyright (C) 2017 Illia Burov

Please do not remove this copyright notice.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.

"""

from __future__ import print_function
import os
import sys
import argparse
import struct
import socket
import select
import datetime
import json
import uuid

# Module info.
__version__ = "0.0.1"
__author__ = "Illia Burov"
__title__ = 'Chat Room 43: Client'
__description__ = 'A simple message exchange client program.'
__email__ = 'ilya.burov.public@gmail.com'
__license__ = 'GPL'
__copyright__ = 'Copyright 2017 (C) Illia Burov'

# Set the default host address.
_HOST = '127.0.0.1'
_PORT = 90210

# Invitation Message.
_PROLOGUE_MSG = 'Chat Room 43: Client'
_INVITE_MSG = \
    """\rWelcome to Chat room 43, a 90s-style obscure invite-only chatting space!
    \rHow many gluten is there in your cheesecake, how tight to cut your pants or
    \rhow many last.fm listeners your fav band has? We have a room for all of your
    \rgreat questions and novel ideas! NO encryption, NO personal space, NO limits!
    \rHit enter to start conversation; Then type your message and hit enter to
    \rsend it. You will automatically receive messages from other users.
    \rType \"!q\" or press Ctrl+C to exit chat room and disconnect from the server."""

# Version information message.
_VERSIONINO_MSG = "{0} v.{1}\n{2}\n{3}".format(__title__,
                                               __version__,
                                               __description__,
                                               __copyright__)


class ChatClient(object):
    """
    Base chat client class.
    """

    RECV_BUFFER = 4096
    RECV_MSG_LEN = 4
    MSG_TIME_FMT = "%H:%M:%S"

    def __init__(self, host, port, username):
        """
        Initializes a new ChatServer.
        :param host: the host on which the server is bounded
        :param port: the port on which the server is bounded
        """
        # Host/port for client to connect to.
        self.host = str(host)
        self.port = int(port)
        # Connection list; all of incoming connections will be collected here.
        self.connections = []
        # Username for current session.
        self.username = username
        # State indicator; Determines whether the server is running/should run or not. 
        self.running = False
        self.is_connected = False
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


    def socket_connect(self):
        """
        Open a socket and bind it to the host and port.
        """

        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.client.connect((self.host, self.port))
        except socket.error as exc_msg:
            print("Unable to connect to server at {0}:{1} ({2})".format(self.host,
                                                                        self.port,
                                                                        os.strerror(exc_msg.errno)))
            self.stop()
            sys.exit(1)
        else:
            self.is_connected = True
            print("Connected to server at {0}:{1}".format(self.host, self.port))
            self.connections.append(self.client)
            self.running = True

    # A method prefixed with two underscores, just like this one is
    # is a protected method.
    def __sendmsg(self, msg, msgtype="usrmsg"):
        """
        Prefix a message with 4-bytes long length indicator,
        wrap it into JSON structure and sen it over to server.
        :param msg: the message to send
        """
        # Maybe use a time when user sends a message rather
        # than the when one receives it.
        # time_struct = time.gmtime()
        struct_msg = json.dumps({
            'uuid': str(uuid.uuid4()),
            'username': self.username,
            'type': msgtype,
            'body': msg
        })
        # Prepend a lenght prefix,
        snd_msg = struct.pack('>I', len(struct_msg)) + struct_msg
        # Actually send a message.
        try:
            self.client.send(snd_msg)
        except socket.error:
            print("* ERROR: Unable to send message.")

    def __receivemsg(self):
        """
        Receive the message from a server, unpack and (probably) parse it.
        :param sock: the incoming socket
        :param ret_code: the return code (whether the message is ok)
        :param ret_data: the unpacked message

        """
        # Will be used to store received data.
        data = None
        # Will be used to compose message.
        msg_dict = dict()
        # Will hold the data to be returned.
        ret_data = str()
        # Will hold the error code.
        ret_code = 0
        # Will hold the total length of message (all chunks combined).
        msg_total_length = 0

        # Retrieve the first 4 bytes of the message.
        while msg_total_length < self.RECV_MSG_LEN:
            msg_len = self.client.recv(self.RECV_MSG_LEN)
            msg_total_length += len(msg_len)
        # If the message has the 4 bytes representing the length.
        if msg_len:
            data = str()
            # Unpack the message and get the message length.
            msg_len = struct.unpack('>I', msg_len)[0]
            msg_data_length_total = 0
            while msg_data_length_total < msg_len:
                # Retrieves the chunk i-th chunk of RECV_BUFFER.
                msg_chunk = self.client.recv(self.RECV_BUFFER)
                # If there isn't the expected chunk.
                if not msg_chunk:
                    data = None
                    # Then break the loop.
                    break
                else:
                    # Merge the msg_chunks. (append these to each other)
                    data += msg_chunk
                    msg_data_length_total += len(msg_chunk)
        # Received nothing (no connection).
        if not data:
            ret_code = 3
            ret_data = "No data received. (Disconnected from server)"
        else:
            # Try to parse JSON message response.
            try:
                msg_dict = json.loads(data)
                current_time = datetime.datetime.now()
                # Formatting message to be "01/01/01 Johnny: Hey Jude!"
                ret_data = "[{0}] {1}: {2}".format(current_time.strftime(self.MSG_TIME_FMT),
                                                   msg_dict['username'],
                                                   msg_dict['body'])
            # Received somehting that is not JSON.
            except ValueError:
                ret_code = 1
                ret_data = "Invalid message format. Discarding message."
            # Received something that is JSON but with no required keys.
            except KeyError:
                ret_code = 2
                ret_data = "Incomplete message received. Discarding message."
        # Return e.g. (0, {"user": "Jane Doe", "body": "Hi there!"})
        return (ret_code, ret_data)


    def stop(self):
        """
        Stops the server by setting the "running" flag before closing
        the socket connection, this will break the application loop.
        """
        print("\rStopping client. Tearing down the connection...\n")
        # Shutting down the socket (no ReaDs or WRites allowed anymore)
        # :msg 1: shutdown
        self.__sendmsg(1, msgtype="svcmsg")
        try:
            self.client.shutdown(socket.SHUT_WR)
            self.client.close()
        except socket.error:
            print("* ERROR: Unable to close connection to server (Not connected?)")
        self.running = False

    def msgexchange(self):
        """
        Exchanges messages between client and server.
        """
        # While 'running' flag is True.
        while self.running:
            # Get the list of streams available for reading.
            # Select those amongst STDIN and the socket.
            # Note that this is the place where whole thing will fail on non-Unix
            # since the select call cannot actualle select stdin on these systems.
            sys.stdout.write("You: ")
            sys.stdout.flush()
            ready_to_read, ready_to_write, in_error = select.select([sys.stdin, self.client],
                                                                    [],
                                                                    [])
            for read_stream in ready_to_read:
                # Incoming message from server (socket is ready to be read from)
                if read_stream == self.client:
                    # Receiving message from server.
                    # recv_data = read_stream.recv(self.RECV_BUFFER)
                    recv_status, recv_data = self.__receivemsg()
                    # If there is no message.

                    if recv_status != 0:
                        print("\r{0} ({1})".format(recv_data, recv_status))
                        if recv_status == 3:
                            self.stop()
                            break
                        else:
                            continue
                    else:
                        # Print received message.
                        print("\r{0}".format(recv_data.strip()))
                # User entered the message (STDIN is ready to be read from)
                else:
                    # Reading the line of user input.
                    msg = sys.stdin.readline()
                    # If the 'quit' command received.
                    msg_service = msg.strip().lower()
                    if msg_service in ["!q", "!quit", "!shutdown", "!killsrv"]:
                        # If requested send "shutdown" service message to server
                        # :msg 1: shutdown
                        # :msg 2: set online status
                        # :msg 3: set away status
                        # :msg 9: shutdown server (Should be avoided)
                        if msg_service == "!shutdown":
                            self.__sendmsg(1, msgtype="svcmsg")
                        if msg_service == "!killsrv":
                            self.__sendmsg(9, msgtype="svcmsg")
                        # Stopping the client and tearing down the connection.
                        self.stop()
                        break
                    self.__sendmsg(msg)


def main():
    """
    The Main. 
    Parse arguments and run a client session.
    """
    argparser = argparse.ArgumentParser(\
        formatter_class=argparse.RawTextHelpFormatter,
        description='Chat Room 43: Client',
        epilog="Chat Room 43: Client v. {0}\n{1}".format(__version__, __copyright__))
    argparser.add_argument(\
        '-u', '--name',
        type=str,
        default="Unnamed",
        dest="username",
        help='Specify the user name to start chat session with.')
    argparser.add_argument(\
        '-n', '--host',
        type=str,
        default=_HOST,
        dest="host",
        help='Specify the host name of the server.')
    argparser.add_argument(\
        '-p', '--port',
        type=str,
        default=_PORT,
        dest="port",
        help='Specify the server port to connect to.')
    argparser.add_argument(\
        '--version',
        default=False,
        action='store_true',
        dest="versioninfo",
        help='Show version information and exit.')
    parsed_args = argparser.parse_args()
    # If the user wants to see version information.
    if parsed_args.versioninfo:
        print(_VERSIONINO_MSG)
        sys.exit(0)

    # Else print an invitation message and continue to initialise.
    print("{0}\n\n{1}".format(_PROLOGUE_MSG, _INVITE_MSG))

    connection = ChatClient(parsed_args.host, parsed_args.port, parsed_args.username)
    connection.socket_connect()
    try:
        connection.msgexchange()
    # If user hits Ctrl + C
    except KeyboardInterrupt:
        connection.stop()
        sys.exit(0)

if __name__ == '__main__':
    # if-main; That is if we are calle by name "__main__"
    # then run "main()" function.
    main()

# EOF
