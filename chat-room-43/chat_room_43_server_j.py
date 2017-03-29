# #!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Chat Room 43: Server. v. 0.0.1

Python 2.7+/3.4+ chat server program.

Run a simple TCP chat server.

Copyright (C) 2017 Illia Burov

Please do not remove this copyright notice.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.        See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.

"""

from __future__ import print_function
import sys
import argparse
import struct
import socket
import select
import threading
import json
import uuid
import logging
import time

# Module info.
__version__ = "0.0.1"
__author__ = "Illia Burov"
__title__ = 'Chat Room 43: Server'
__description__ = 'A simple message exchange server program.'
__email__ = 'ilya.burov.public@gmail.com'
__license__ = 'GPL'
__copyright__ = 'Copyright 2017 (C) Illia Burov'

# Set the default host address.
_HOST = '127.0.0.1'
_PORT = 14344

# Version information message.
_VERSIONINO_MSG = "{0} v.{1}\n{2}\n{3}".format(__title__,
                                               __version__,
                                               __description__,
                                               __copyright__)

# Configure logging facility.
# Log message format.
LOG_FORMAT = "%(asctime)-15s %(levelname)s: %(message)s"
# Set logging configuration.
logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG, datefmt="%d/%m/%y-%H:%M:%S")


class ChatServer(threading.Thread):
    """
    Base chat server class (threaded).
    """
    # The size of connection queue.
    CONN_QUEUE = 10
    # The size of a message buffer.
    RECV_BUFFER = 4096
    # The size of a message length prefix.
    RECV_MSG_LEN_PREFIX = 4

    def __init__(self, host, port):
        """
        Initialise a new ChatServer.
        :param host: the host on which the server is bound
        :param port: the port on which the server is bound
        """
        # Initialise the tread new.
        threading.Thread.__init__(self)
        # Host/port for server to listen at.
        self.host = str(host)
        self.port = int(port)
        # Connection list; all of incoming connections will be collected here.
        self.connections = list()
        # State indicator; Determines whether the server is running/should run or not.
        self.running = bool(True)
        # Username; In case the server will send a text message to user the self.username
        # will be prepended to it for user to be able to tell server messages from another user's.
        self.username = str("Server")
        # Assign a server socket.
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def __open_socket(self):
        """
        Create the server socket and bind it to the given host and port.
        """
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(self.CONN_QUEUE)
        self.connections.append(self.server_socket)

    def _disconnect(self, sock, logmessage="Client disconnected"):
        """
        (Force) Gracefully disconnect the client.
        :param sock: socket
        :param logmessage: optional message to write to log on disconnect.
        """
        # Shutdown the socket for read and write operations.
        try:
            sock.shutdown(socket.SHUT_RDWR)
        # Else socket is probably already closed;
        # It's ok by now, gnore the exception.
        except socket.error:
            pass
        # Close the socket.
        try:
            sock.close()
        # Else socket is probably already closed.
        except socket.error:
            pass
        # Remove connection from connections pool.
        self.connections.remove(sock)
        # Write a log message.
        logging.info(logmessage)

    # A method prefixed with two underscores, just like this one is
    # is a private method.
    def __sendmsg(self, sock, msg):
        """
        Prefix each message with a 4-byte length before sending it over to destination.
        :param sock: the incoming socket
        :param msg: the message to send
        """
        # Pack the message with 4 leading bytes representing the message length.
        msg = struct.pack('>I', len(str(msg))) + bytes(msg, 'utf8')
        # Sends the packed message.
        sock.send(msg)

    def __receivemsg(self, sock):
        """
        Receive an incoming message from the client and unpack it.
        :param sock: the incoming socket
        :return: the unpacked message
        """
        # The message data will be stored here.
        data = None
        # Will hold the total length of message (all msg_chunks combined).
        msg_total_length = 0
        # Read the first 4 bytes from the message we've just received.
        # (that's where the message length is stored)
        while msg_total_length < self.RECV_MSG_LEN_PREFIX:
            msg_len = sock.recv(self.RECV_MSG_LEN_PREFIX)
            msg_total_length += len(msg_len)
        # If there are these 4-bytes (where the length is stored)
        if msg_len:
            data = bytes()
            # Unpack the message and get the message length.
            msg_len = struct.unpack('>I', msg_len)[0]
            msg_data_length_total = 0
            while msg_data_length_total < msg_len:
                # Retrieve the n-th chunk of RECV_BUFFER size.
                msg_chunk = sock.recv(self.RECV_BUFFER)
                # If there isn't the part we are expecting.
                if not msg_chunk:
                    data = None
                    # Then break the loop.
                    break
                else:
                    # Merge the msg_chunks content together.
                    data += msg_chunk
                    msg_data_length_total += len(msg_chunk)
            return data.decode('utf-8')


    def __broadcastmsg(self, client_socket, client_message):
        """
        Broadcast a message to all the clients different from both the server itself and
        the client sending the message (since it does not need it anyway; the
        person already know what he/she's sending).
        :param client_socket: the socket of the client sending the message
        :param client_message: the message to broadcast
        """
        for sock in self.connections:
            # Remember the AND-OR-NOT thing.
            is_not_the_server = sock != self.server_socket
            is_not_the_client__sendmsging = sock != client_socket
            if is_not_the_server and is_not_the_client__sendmsging:
                try:
                    self.__sendmsg(sock, client_message)
                except socket.error:
                    # The client is most likely (not/dis-)connected.
                    self._disconnect(sock, "Client has been disconnected")

    def __run(self):
        """
        Actually run the server.
        """
        # Default the message type to "Unknown"
        recv_msgtype = str("unk")

        while self.running:
            # Get the list of streams available for reading.
            # Select those amongst sockets available in connection pool.
            # Note that this is the place where whole thing will fail on non-Unix
            # since the select call cannot actualle select stdin on these systems.
            # Set the timeout for that to be 45 seconds.
            try:
                ready_to_read, ready_to_write, in_error = select.select(self.connections, [], [], 60)
            except socket.error:
                continue
            else:
                for sock in ready_to_read:
                    # If this is our socket.
                    if sock == self.server_socket:
                        try:
                            # Then accept the connection.
                            client_socket, client_address = self.server_socket.accept()
                        except socket.error:
                            break
                        else:
                            # Then add the connection to connection pool.
                            self.connections.append(client_socket)
                            # And write a log message about it.
                            logging.info("Client %s:%d connected", client_address[0], client_address[1])

                            # Broadcast the "New guy has entered a room" message.
                            struct_msg = json.dumps(\
                                {
                                    'uuid': str(uuid.uuid4()),
                                    'username': self.username,
                                    'type': 'ursmsg',
                                    'body': "\r[{0}, {1}] entered the chat room".format(client_address[0], client_address[1])
                                })
                            self.__broadcastmsg(client_socket, struct_msg)
                    # Else we've got an incoming connection.
                    else:
                        try:
                            # Try to receive the incoming message.
                            data = self.__receivemsg(sock)
                            # If is ok, i.e. there is a message.
                            if data:

                                try:
                                    # Parse it (remember that we'are speaking JSON here).
                                    msg_dict = json.loads(data)
                                    recv_msgtype = msg_dict['type']
                                except (ValueError, TypeError):
                                    # If we failed to parse that JSON message.
                                    # Then set the message type to "msgerr" which is
                                    # a...uh.. "message error" or "error message" or something.
                                    recv_msgtype = "msgerr"
                                # If received message is a user message
                                # (the one that client/user is trying to send over to everyone).
                                # Then do not bother parsing it and just broadcats instead.
                                if recv_msgtype == "usrmsg":
                                    logging.info("Received/Broadcasting user message from %s:%d", client_address[0], client_address[1])
                                    self.__broadcastmsg(sock, data)
                                # If received message is service message. Then parse and process it w/o broadcasting.
                                elif recv_msgtype == "svcmsg":
                                    logging.info("Received service message from %s:%d", client_address[0], client_address[1])
                                    # If received message is a "shutdown client connection" service message.
                                    if msg_dict['body'] == 1:
                                        logging.info("Shutdown client command received; Disconnecting %s:%d", client_address[0], client_address[1])
                                        # Let client die, since client has initialised a local shutdown procedure before sending this message.
                                        # Just sleep for 2 seccond. This might be not necessary but still.
                                        logging.info("Waiting for client to die.")
                                        time.sleep(2)
                                        # Unbind the socket, print log message and disconnect the client.
                                        self._disconnect(sock, "Client %s:%d has been disconnected", client_address[0], client_address[1])
                                        continue
                                    if msg_dict['body'] == 6:
                                        struct_msg = json.dumps(\
                                        {
                                            'uuid': str(uuid.uuid4()),
                                            'username': msg_dict['username'],
                                            'type': 'svcmsg',
                                            'msgcommand': 'status',
                                            'newstatusstr': "Away",
                                            'newstatusid': 1,
                                            'body': "{0} has changed their status to Away".format(self.username)
                                        })
                                        self.__broadcastmsg(sock, struct_msg)

                                    
                                    else:
                                        logging.info("Unknown command \"%s\" received from %s:%d", str(msg_dict),  client_address[0], client_address[1])
                                # If received message is invalid.
                                elif recv_msgtype == "msgerr":
                                    logging.info("Received invalid message from %s:%d", client_address[0], client_address[1])
                                    # Then still broadcast it for client to take care of it.
                                    self.__broadcastmsg(sock, data)

                        except socket.error:
                            # Broadcast "Client has gone offline" message to
                            # all the connected clients stating that a client has left a room.
                            struct_msg = json.dumps(\
                                {
                                    'uuid': str(uuid.uuid4()),
                                    'username': self.username,
                                    'type': 'usrmsg',
                                    'body': "Client [{0}, {1}] has gone offline".format(client_address[0], client_address[1])
                                })
                            self.__broadcastmsg(sock, struct_msg)
                            self._disconnect(sock, "Client {0}:{1} has been disconnected".format(client_address[0], client_address[1]))
                            continue
        # Clear the connection and stop.
        self.stop()

    def run(self):
        """
        Open a socker and run the server.
        """
        logging.info("Starting server. Listening to %s:%d...", self.host, self.port)
        self.__open_socket()
        self.__run()

    def stop(self):
        """
        Stops the server by setting the "running" flag before closing
        the socket connection, this will break the application loop.
        """
        logging.info("Stopping server. Closing connections to %s:%d...", self.host, self.port)
        self.running = False
        self.server_socket.close()


def main():
    """
    The Main.
    Parse arguments and run a server session.
    """
    argparser = argparse.ArgumentParser(\
      formatter_class=argparse.RawTextHelpFormatter,
      description='Chat Room 43: Server',
      epilog="Chat Room 43: Server v. {0}\n{1}".format(__version__, __copyright__))
    argparser.add_argument(\
      '-n', '--host',
      type=str,
      default=_HOST,
      dest="host",
      help='Specify the host name to run server at.')
    argparser.add_argument(\
      '-p', '--port',
      type=str,
      default=_PORT,
      dest="port",
      help='Specify the port to listen to')
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

    # Run the server.
    chat_server = ChatServer(parsed_args.host, parsed_args.port)
    chat_server.start()

if __name__ == '__main__':
    # if-main; That is if we are calle by name "__main__"
    # then run "main()" function.
    main()

# EOF
