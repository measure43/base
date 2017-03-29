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
import logging
from StringIO import StringIO
import atexit
from datetime import datetime
import time

try:
    from javax.swing import *
    from java.lang import *
    from java.awt import *
    from java.awt.event import KeyEvent
    from java.awt.event import ActionEvent
    from javax.swing.table import DefaultTableModel
    from java.util import *
    from javax.swing.border import *
    from javax.swing.text import SimpleAttributeSet
    from javax.swing.text import StyleConstants
except ImportError as errmsg:
    pass

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
_PORT = 14344

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




class ChatClientBase(object):
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
        self.connections = list()
        # Username for current session.
        self.username = username
        # State indicator; Determines whether the server is running/should run or not. 
        self.running = False
        self.is_connected = False
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_gui_condition = False


    def write_out_msg(self, from_user, message):

        msg_prefix = "[{0} {1}]: ".format(datetime.fromtimestamp(time.time()).strftime("%m/%d %H:%M:%S"), from_user)
        print("{0}{1}\n".format(msg_prefix, message))


    def socket_connect(self):
        """
        Open a socket and bind it to the host and port.
        """
        self.write_out_msg("System", "Trying to connect to server at {0}:{1}".format(self.host, self.port))
        
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.client.connect((self.host, self.port))
        except socket.error as exc_msg:
            self.write_out_msg("System", "Unable to connect to server at {0}:{1} ({2})".format(self.host,
                                                                        self.port,
                                                                        os.strerror(exc_msg.errno)))
            self.stop()
        else:
            self.is_connected = True
            self.write_out_msg("System", "Connected to server at {0}:{1}".format(self.host, self.port))
            self.connections.append(self.client)
            self.running = True

    # A method prefixed with two underscores, just like this one is
    # is a protected method.
    def sendmsg(self, msg, msgtype="usrmsg"):
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
            self.client.send(bytes(snd_msg).encode('utf-8'))
        except socket.error:
            self.write_out_msg("System", "Unable to send message.")

    def receivemsg(self):
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
            msg_len = str(self.client.recv(self.RECV_MSG_LEN))
            if msg_len:
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
                    data += str(msg_chunk)
                    msg_data_length_total += len(msg_chunk)
        # Received nothing (no connection).
        if not data:
            ret_code = 3
            ret_username = "System"
            ret_body = "No data received. (Disconnected from server)"
        else:
            # Try to parse JSON message response.
            try:
                msg_dict = json.loads(data.decode('utf-8'))
                current_time = datetime.now()
                ret_username = msg_dict['username']
                ret_body = msg_dict['body']
            # Received somehting that is not JSON.
            except ValueError as errmsg:
                ret_code = 1
                ret_body = "Invalid message format. Discarding message."
                ret_username = "System"
            # Received something that is JSON but with no required keys.
            except KeyError as errmsg:
                ret_code = 2
                ret_body = "Incomplete message received. Discarding message."
                ret_username = "System"
        # Return e.g. (0, {"user": "Jane Doe", "body": "Hi there!"})
        return (ret_code, ret_username, ret_body, msg_dict or None)


    def stop(self):
        """
        Stops the server by setting the "running" flag before closing
        the socket connection, this will break the application loop.
        """
        self.write_out_msg("System", "Stopping client. Tearing down the connection...")
        # Shutting down the socket (no ReaDs or WRites allowed anymore)
        # :msg 1: shutdown
        self.sendmsg(1, msgtype="svcmsg")
        try:
            self.client.shutdown(socket.SHUT_WR)
            self.client.close()
        except socket.error:
            self.write_out_msg("System", "Unable to close connection to server (Not connected?)")
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
                    recv_status, recv_username, recv_body, recv_dict = self.receivemsg()
                    # If there is no message.

                    if recv_status != 0:
                        self.write_out_msg(recv_username, "{0} ({1})".format(recv_body, recv_status))
                        if recv_status == 3:
                            self.stop()
                            break
                        else:
                            continue
                    else:
                        # Print received message.
                        self.write_out_msg(recv_username, "{0}".format(recv_body.strip()))
                # User entered the message (STDIN is ready to be read from)
                else:
                    # Reading the line of user input.
                    msg = sys.stdin.readline()
                    # If the 'quit' command received.
                    # If received message exacly matches any service message pattern.
                    if any([bool(re.match(cmd_pattern, msg.strip().lower())) for cmd_pattern in ["^\!q$", "^\!quit$", "^\!shutdown$", "^\!status:.*$"]]):
                        # If requested send "shutdown" service message to server
                        # :msg 1: shutdown
                        # :msg 9: shutdown server (Should be avoided)
                        # :msg 5: set "online" status.
                        # :msg 6: set "away" status.
                        # :msg 7: set "dnd" status.
                        # :msg 8: set "offline" status and disconnect from server.
                        # str.startswith("foo") is much faster than re.match("^foo")
                        if msg.startswith("!shutdown"):
                            self.sendmsg(1, msgtype="svcmsg")
                        elif msg.startswith("!status:"):
                            status_id = msg.split(":")[-1]
                            if status_id == "on":
                                self.sendmsg(5, msgtype="svcmsg")
                            elif status_id == "afk":
                                self.sendmsg(6, msgtype="svcmsg")
                            elif status_id == "dnd":
                                self.sendmsg(7, msgtype="svcmsg")
                            elif status_id == "off":
                                # First send "set offline status" service message.
                                self.sendmsg(8, msgtype="svcmsg")
                                # Then send "connection shutdown" service message.
                                self.sendmsg(1, msgtype="svcmsg")
                        # Stopping the client and tearing down the connection.
                        self.stop()
                        break
                    self.sendmsg(msg)



class ChatClientGUI(ChatClientBase):


    def __init__(self, host, port, username):
        
        # Calling __init__ of a parent class.
        super(ChatClientGUI, self).__init__(host, port, username)
        
        self.text_pane_h = 400
        self.text_pane_w = 512
        self.online_table_w = 220
        self.ready_to_send = False
        self.common_control_label_h = 32

        self.colour_blue = Color(77, 148, 255)
        self.colour_green = Color(77, 148, 255)

        self.map_statuses = [
        (5, "on", "Online"),
        (6, "afk", "Away"),
        (7, "dnd", "Do not Disturb"),
        (8, "off", "Offline")
        ]

    
        # Main JFrame
        self.container_main_frame = JFrame("Chat Room")
        self.container_main_frame.setResizable(False)
        self.container_main_frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)

        # IM JTextArea
        self.im_text_pane = JTextPane()
        self.im_text_pane.setPreferredSize(Dimension(self.text_pane_w, self.text_pane_h))
        self.im_text_pane_styled_doc = self.im_text_pane.getStyledDocument()
        self.im_text_pane.setEditable(False)
        im_scroll_panel = JScrollPane()
        im_scroll_panel.getViewport().setView(self.im_text_pane)
        im_scroll_panel.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_ALWAYS)

        # User input field label.
        inputLabel = JLabel("You: ")
        input_label_dimension_common = inputLabel.getPreferredSize()
        input_label_dimension_common.height = self.common_control_label_h
        inputLabel.setPreferredSize(input_label_dimension_common)
        inputLabel.setHorizontalAlignment(SwingConstants.LEFT)
        
        # Controls pane.
        im_control_panel = JPanel()
        im_control_panel.setLayout(BorderLayout())
        im_control_panel.add(inputLabel, BorderLayout.LINE_START)

        # User input field.
        self.im_input_field = JTextField("", 12)
        button_send = JButton("Send", actionPerformed=self.get_out_msg_text)
        button_send.setPreferredSize(Dimension(92, 0))
        im_control_panel.add(self.im_input_field, BorderLayout.CENTER)
        im_control_panel.add(button_send,  BorderLayout.LINE_END)
        
        # IM panel (Text area and input field-send-button group)
        im_inner_panel = JPanel()
        im_inner_panel.setLayout(BorderLayout())
        im_inner_panel.add(im_scroll_panel, BorderLayout.PAGE_START)
        im_inner_panel.add(im_control_panel, BorderLayout.PAGE_END)

        # Current user status dropdown menu and label panel.
        current_status_panel = JPanel()
        current_status_panel.setLayout(BorderLayout())
        current_status_select_label = JLabel("Your status")
        avail_statuses = [status_tuple[2] for status_tuple in self.map_statuses]
        self.current_status_select_cbox = JComboBox(avail_statuses)
        self.current_status_select_cbox.addActionListener(self.status_cb_action)
        self.current_status_select_cbox.setSelectedIndex(1)
        # petList.addActionListener(this);

        current_status_panel.add(current_status_select_label, BorderLayout.LINE_START)
        current_status_panel.add(self.current_status_select_cbox, BorderLayout.LINE_END)


        # Online users panel.
        online_users_panel = JPanel()
        online_users_panel.setLayout(BorderLayout())
        online_users_label = JLabel("Online Users: ")
        online_users_label_dimension_common = online_users_label.getPreferredSize()
        online_users_label_dimension_common.height = self.common_control_label_h
        online_users_label.setPreferredSize(online_users_label_dimension_common)
        online_user_count_label = JLabel("0")
        online_user_count_label.setHorizontalAlignment(SwingConstants.LEFT)
        online_users_panel.add(online_users_label, BorderLayout.LINE_START)
        online_users_panel.add(online_user_count_label, BorderLayout.CENTER)

        # Online users table view.
        table_data_init = [['Fake User', 'Online']]
        table_cols = ('User','Status')
        self.online_table_dm = DefaultTableModel(table_data_init, table_cols)
        self.table = JTable(self.online_table_dm)
        self.table.setShowGrid(False)

        # Table view scroll pane.
        scroll_pane_table = JScrollPane()
        scroll_pane_table.setPreferredSize(Dimension(self.online_table_w, 0))
        scroll_pane_table.getViewport().setBackground(Color.WHITE);
        scroll_pane_table.getViewport().setView((self.table))

        # Split view container.
        container_split_pane_vertical_right = JPanel()
        container_split_pane_vertical_right.setLayout(BorderLayout())
        container_split_pane_vertical_right.add(current_status_panel, BorderLayout.PAGE_START)
        container_split_pane_vertical_right.add(scroll_pane_table, BorderLayout.CENTER)
        container_split_pane_vertical_right.add(online_users_panel, BorderLayout.PAGE_END)
        
        
        # # "Online Users" label.
        # online_label = JLabel("Online Users: 0")
        # container_split_pane_vertical_right.add(online_label, BorderLayout.PAGE_END)

        container_split_pane_h = JPanel()
        container_split_pane_h.setLayout(BorderLayout())
        container_split_pane_h.add(container_split_pane_vertical_right, BorderLayout.LINE_START)
        container_split_pane_h.add(im_inner_panel, BorderLayout.LINE_END)
        
        # Main menua bar.
        main_menu_bar = JMenuBar()

        # "File" menu.
        menu_file = JMenu("File")
        menu_file.setMnemonic(KeyEvent.VK_A)
        menu_file.getAccessibleContext().setAccessibleDescription("File operations")

        # "Exit" menu item.
        reconnect_mitem = JMenuItem("Exit...", KeyEvent.VK_T, actionPerformed=self.dispose_and_exit)
        reconnect_mitem.setAccelerator(KeyStroke.getKeyStroke(KeyEvent.VK_F10, ActionEvent.ALT_MASK))
        reconnect_mitem.getAccessibleContext().setAccessibleDescription("Exit")
        menu_file.add(reconnect_mitem);
        
        # "Connection" menu.
        menu_connection = JMenu("Connection")
        menu_connection.setMnemonic(KeyEvent.VK_A)
        menu_connection.getAccessibleContext().setAccessibleDescription("Server Connection Manipulations")
        
        # "Re-connect" menu item.
        reconnect_mitem = JMenuItem("Re-connect...", KeyEvent.VK_T)
        reconnect_mitem.setAccelerator(KeyStroke.getKeyStroke(KeyEvent.VK_1, ActionEvent.ALT_MASK))
        reconnect_mitem.getAccessibleContext().setAccessibleDescription("Re-connect to the server")
        menu_connection.add(reconnect_mitem);

        # "Disconnect" menu item.
        disconnect_mitem = JMenuItem("Disconnect...", KeyEvent.VK_T)
        disconnect_mitem.setAccelerator(KeyStroke.getKeyStroke(KeyEvent.VK_2, ActionEvent.ALT_MASK))
        disconnect_mitem.getAccessibleContext().setAccessibleDescription("Disconnect from the server")
        menu_connection.add(disconnect_mitem);

        main_menu_bar.add(menu_file)
        main_menu_bar.add(menu_connection)
       
        container_split_pane_h.add(main_menu_bar, BorderLayout.PAGE_START)
        self.container_main_frame.add(container_split_pane_h)
        self.container_main_frame.pack()
        self.container_main_frame.setVisible(True)
        self.im_input_field.requestFocus()


    def write_out_msg(self, from_user, message):

        msg_prefix = "[{0} {1}]: ".format(datetime.fromtimestamp(time.time()).strftime("%m/%d %H:%M:%S"), from_user)

        styled_label = SimpleAttributeSet()
        StyleConstants.setForeground(styled_label, self.colour_blue)
        StyleConstants.setBold(styled_label, True)

        self.im_text_pane_styled_doc.insertString(self.im_text_pane_styled_doc.getLength(), msg_prefix , styled_label)
        self.im_text_pane_styled_doc.insertString(self.im_text_pane_styled_doc.getLength(), "{0}\n".format(message), None)

    def get_out_msg_text(self, event):
        self.ready_to_send = False
        msg_text = self.im_input_field.getText()
        if self.im_input_field.getText():
            self.ready_to_send = True

        self.write_out_msg("You", msg_text)
        self.sendmsg(msg_text)
        
        self.im_input_field.setText(None)
        self.im_input_field.requestFocus()

    def status_cb_action(self, event):
        selected_status_index = int(event.getSource().getSelectedIndex())
        self.sendmsg(self.map_statuses[selected_status_index][0], msgtype="svcmsg")

    def dispose_and_exit(self, event):
        self.container_main_frame.dispose()
        sys.exit(0)


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
            # sys.stdout.write("You: ")

            # TODO: ---------------------------------------------------------------------------------
            # sys.stdout.flush()
            ready_to_read, ready_to_write, in_error = select.select([self.client],[],[])
            if self.client in ready_to_read:
                # Receiving message from server.
                # recv_data = read_stream.recv(self.RECV_BUFFER)
                recv_status, recv_username, recv_body, recv_dict = self.receivemsg()
                # If there is no message.
                if recv_status != 0:
                    if recv_status == 3:
                        self.stop()
                        break
                    else:
                        continue
                else:
                    # Print received message.
                    if recv_dict["type"] == "usrmsg":
                        self.write_out_msg(recv_username, "{0}".format(recv_body.strip()))
                    elif recv_dict["type"] == "svcmsg":
                        self.write_out_msg("Service message", "{0}".format(str(recv_dict)))
            # User entered the message (STDIN is ready to be read from)
            else:
                # Reading the line of user input.
                if not self.ready_to_send:
                    continue
                msg = self.im_input_field.getText()
                # If the 'quit' command received.
                msg_service = msg.strip().lower()
                if any([bool(re.match(cmd_pattern, msg.strip().lower())) for cmd_pattern in ["^\!q$", "^\!quit$", "^\!shutdown$", "^\!status:.*$"]]):
                    # If requested send "shutdown" service message to server
                    # :msg 1: shutdown
                    # :msg 9: shutdown server (Should be avoided)
                    # :msg 5: set "online" status.
                    # :msg 6: set "away" status.
                    # :msg 7: set "dnd" status.
                    # :msg 8: set "offline" status and disconnect from server.
                    # str.startswith("foo") is much faster than re.match("^foo")
                    if msg.startswith("!shutdown"):
                        self.sendmsg(1, msgtype="svcmsg")
                        self.stop()
                        break
                    # elif msg.startswith("!status:"):
                    #     status_id = msg.split(":")[-1]
                    #     if status_id == "on":
                    #         self.sendmsg(5, msgtype="svcmsg")
                    #     elif status_id == "afk":
                    #         self.sendmsg(6, msgtype="svcmsg")
                    #     elif status_id == "dnd":
                    #         self.sendmsg(7, msgtype="svcmsg")
                    #     elif status_id == "off":
                    #         # First send "set offline status" service message.
                    #         self.sendmsg(8, msgtype="svcmsg")
                    #         # Then send "connection shutdown" service message.
                    #         self.sendmsg(1, msgtype="svcmsg")
                    # Stopping the client and tearing down the connection.
                    # self.stop()
                    # break
                self.sendmsg(msg)


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
    # if parsed_args.versioninfo:
    #     self.write_out_msg(_VERSIONINO_MSG)
    #     sys.exit(0)

    # Else print an invitation message and continue to initialise.
    # self.write_out_msg("{0}\n\n{1}".format(_PROLOGUE_MSG, _INVITE_MSG))

    connection = ChatClientGUI(parsed_args.host, parsed_args.port, parsed_args.username)
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
