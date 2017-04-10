# #!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
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

'''
# Python imports
from __future__ import print_function
import os
import sys
import argparse
import struct
import socket
import select
import json
import uuid
from datetime import datetime
import time
import atexit

# Java imports.
# Using absolute imports as wildcard imports will fail on attemp to
# launch with a portable jython.
# Also wildcard imports are not PEP8 compliant.

# Swing.
from javax.swing import JFrame
from javax.swing import JLabel
from javax.swing import JTextPane
from javax.swing import JScrollPane
from javax.swing import JTextField
from javax.swing import JButton
from javax.swing import JPanel
from javax.swing import JMenuBar
from javax.swing import JMenu
from javax.swing import JMenuItem
from javax.swing import JComboBox
from javax.swing import JTable
from javax.swing.table import DefaultTableModel
from javax.swing.text import SimpleAttributeSet
from javax.swing.text import StyleConstants
from javax.swing import WindowConstants
from javax.swing import SwingConstants
from javax.swing import KeyStroke

# AWT
from java.awt import BorderLayout
from java.awt import Dimension
from java.awt import Color
from java.awt.event import KeyEvent
from java.awt.event import ActionEvent


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

# Version information message.
_VERSIONINO_MSG = "{0} v.{1}\n{2}\n{3}".format(__title__,
                                               __version__,
                                               __description__,
                                               __copyright__)

class ChatClientBase(object):
    '''
    Base chat client class. Containt all the methods related to network
    connection and message transmission
    '''

    RECV_BUFFER = 4096
    RECV_MSG_LEN = 4
    MSG_TIME_FMT = "%H:%M:%S"

    def __init__(self, host, port, username):
        '''
        Initializes a new ChatServer.
        :param host: the host on which the server is bounded
        :param port: the port on which the server is bounded
        '''

        # Host/port for client to connect to.
        self.host = str(host)
        self.port = int(port)
        # Connection list;
        # all of incoming connections will be collected here.
        self.connections = list()
        # Username for current session.
        self.username = username
        # Creating client socket.
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # State indicator;
        # Determines whether the server is running/should run or not.
        self.is_running = False
        # Wheter the instnce is GUI-enabled one.
        self.is_gui_instance = False


    def _display_im(self, from_user, message):
        '''
        Print incoming message out (CLImode only).
        '''

        msg_prefix = "[{0} {1}]: ".format(
            datetime.fromtimestamp(
                time.time()
                ).strftime("%m/%d %H:%M:%S"),
            from_user
            )
        print("{0}{1}\n".format(msg_prefix, message))


    def socket_connect(self):
        '''
        Open a socket, bind it to the host and port. Try to connecto to server.
        '''

        self._display_im(
            "System",
            "Trying to connect to server at {0}:{1}".format(
                self.host,
                self.port
                )
            )

        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.client.connect((self.host, self.port))
        except socket.error as exc_msg:
            self._display_im(
                "System",
                "Unable to connect to server at {0}:{1} ({2})".format(
                    self.host,
                    self.port,
                    os.strerror(exc_msg.errno)
                    )
                )
            self.stop_session()
        else:
            self.is_running = True
            self._display_im(
                "System",
                "Connected to server at {0}:{1}".format(
                    self.host,
                    self.port
                    )
                )
            self.connections.append(self.client)


    def sendmsg(self,
                msg,
                msgtype=0,
                command=None,
                actionkey=None,
                primarykey=None,
                secondarykey=None):
        '''
        Prefix a message with 4-bytes long length indicator,
        wrap it into JSON structure and sen it over to server.
        :param msg: the message to send
        '''

        # Maybe use a time when user sends a message rather
        # than the when he/she receives it.
        # TODO: ?
        # Message Type IDs:
        # 0 : User Message
        # 1 : Service Message
        # Message Commands:
        # 0 : Status Change
        # 9 : Shutdown Connection
        struct_msg = json.dumps({
            'uuid': str(uuid.uuid4()),
            'username': self.username,
            'type': msgtype,
            'body': msg,
            "command": command,
            "action": actionkey,
            "primarykey": primarykey,
            "secondarykey": secondarykey
        })
        # Prepend a lenght prefix,
        snd_msg = struct.pack(
            '>I',
            len(struct_msg)
            ) + bytes(struct_msg).encode('utf-8')
        # Actually send a message.
        if self.is_running:
            try:
                self.client.send(snd_msg)
            except socket.error:
                if msgtype == 0:
                    self._display_im("System", "Unable to send message.")

    def receivemsg(self):
        '''
        Receive the message from a server, unpack and parse it.
        Return received message as a tuple of values.
        '''

        # Will be used to store received data.
        data = None
        # Will be used to compose message.
        msg_dict = dict().fromkeys(['username',
                                    'body',
                                    'type',
                                    'command',
                                    'action',
                                    'primarykey',
                                    'secondarykey'],
                                   None
                                  )
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
            msg_dict['username'] = "System"
            msg_dict['body'] = "No data received. (Disconnected from server)"
        else:
            # Try to parse JSON message response.
            try:
                # Update the msg_dict with what is received.
                msg_dict.update(json.loads(data.decode('utf-8')))
                ret_code = 0
            # Received somehting that is not JSON.
            except ValueError:
                ret_code = 1
                msg_dict['body'] = "Invalid message format. Discarding message."
                msg_dict['username'] = "System"
            # Received something that is JSON but with no required keys.
            except KeyError:
                ret_code = 2
                msg_dict['body'] = "Incomplete message received. Discarding message."
                msg_dict['username'] = "System"
        # Return e.g. (0, "Jane Doe", "Hi there!" etc.)
        return (
            ret_code,
            msg_dict['username'],
            msg_dict['body'],
            msg_dict['type'],
            msg_dict['command'],
            msg_dict['action'],
            msg_dict['primarykey'],
            msg_dict['secondarykey']
            )

    def stop_session(self, event=None):
        '''
        Stop the server by setting the "running" flag before closing
        the socket connection, this will break the application loop.
        :param event: Event. Discarded.
        '''

        del event
        self._display_im(
            "System",
            "Stopping client. Tearing down the connection..."
            )
        # Shutting down the socket (no ReaDs or WRites allowed anymore)
        self.sendmsg(None, msgtype=1, command=9)
        try:
            self.client.shutdown(socket.SHUT_WR)
            aaa = self.client.recv(4096)
            del aaa
            self.client.close()
        except socket.error:
            self._display_im(
                "System",
                "Unable to close connection to server (Not connected?)"
                )
        self.connections = list()
        self.is_running = False



class ChatClientGUI(ChatClientBase):
    '''
    GUI
    '''

    def __init__(self, host, port, username):
        '''
        Initialising ChatClientGUI. 
        GUI is being built in __init__.
        '''
        
        # Calling __init__ of a parent class.
        super(ChatClientGUI, self).__init__(host, port, username)

        # Whether the instance is GUI-enabled one.
        self.is_gui_instance = True
        
        self.text_pane_h = 400
        self.text_pane_w = 512
        self.online_table_w = 220
        self.ready_to_send = False
        self.common_control_label_h = 32

        self.colour_blue = Color(77, 148, 255)
        self.colour_green = Color(77, 148, 255)

        self.app_title = "Chat Room 43"
        self.usertbl_sel_values = [
            "Online",
            "Away",
            "Do not Disturb",
            "Offline"
            ]
        self.usertbl_colnames = [
            "User",
            "Status"
            ]

        # Main JFrame
        self.frame_main_cont = JFrame(self.app_title, 
            windowClosing=self._action_dispose_and_exit
            )
        self.frame_main_cont.setResizable(False)
        self.frame_main_cont.setDefaultCloseOperation(
            WindowConstants.DISPOSE_ON_CLOSE
            )

        # IM JTextArea
        self.textpane_im = JTextPane()
        self.textpane_im.setPreferredSize(Dimension(self.text_pane_w,
                                                    self.text_pane_h))
        self.styleddoc_textpane_im = self.textpane_im.getStyledDocument()
        self.textpane_im.setEditable(False)
        scrollpane_im = JScrollPane()
        scrollpane_im.getViewport().setView(self.textpane_im)
        scrollpane_im.setVerticalScrollBarPolicy(
            JScrollPane.VERTICAL_SCROLLBAR_ALWAYS
            )

        # User input field label.
        label_im_input = JLabel("You: ")
        dim_label_im_input = label_im_input.getPreferredSize()
        dim_label_im_input.height = self.common_control_label_h
        label_im_input.setPreferredSize(dim_label_im_input)
        label_im_input.setHorizontalAlignment(SwingConstants.LEFT)

        # Controls pane.
        panel_im_ctrl = JPanel()
        panel_im_ctrl.setLayout(BorderLayout())
        panel_im_ctrl.add(label_im_input, BorderLayout.LINE_START)

        # User input field.
        self.textfield_im_input = JTextField("", 12)
        button_send = JButton("Send", actionPerformed=self._action_send_button)
        button_send.setPreferredSize(Dimension(92, 0))
        panel_im_ctrl.add(self.textfield_im_input, BorderLayout.CENTER)
        panel_im_ctrl.add(button_send, BorderLayout.LINE_END)

        # IM panel (Text area and input field-send-button group)
        panel_im_inner = JPanel()
        panel_im_inner.setLayout(BorderLayout())
        panel_im_inner.add(scrollpane_im, BorderLayout.PAGE_START)
        panel_im_inner.add(panel_im_ctrl, BorderLayout.PAGE_END)

        # Current user status dropdown menu and label panel.
        panel_curr_status = JPanel()
        panel_curr_status.setLayout(BorderLayout())
        label_curr_status_sel = JLabel(
            self.username[:8] + (self.username[8:] and "...")
            )
        self.current_status_select_cbox = JComboBox(self.usertbl_sel_values)
        self.current_status_select_cbox.addActionListener(
            self._action_status_combo
            )
        self.current_status_select_cbox.setSelectedIndex(3)
        # petList.addActionListener(this);

        panel_curr_status.add(label_curr_status_sel,
                              BorderLayout.LINE_START)
        panel_curr_status.add(self.current_status_select_cbox,
                              BorderLayout.LINE_END)

        # Online users panel.
        panel_online_usr = JPanel()
        panel_online_usr.setLayout(BorderLayout())
        label_online_usr = JLabel("Online Users: ")
        dim_label_usr_common = label_online_usr.getPreferredSize()
        dim_label_usr_common.height = self.common_control_label_h
        label_online_usr.setPreferredSize(dim_label_usr_common)
        label_online_usr_cnt = JLabel("0")
        label_online_usr_cnt.setHorizontalAlignment(SwingConstants.LEFT)
        panel_online_usr.add(label_online_usr, BorderLayout.LINE_START)
        panel_online_usr.add(label_online_usr_cnt, BorderLayout.CENTER)

        # Online users table data model.
        self.online_table_dm = DefaultTableModel(
            [None, None],
            self.usertbl_colnames
        )
        self.table = JTable(self.online_table_dm)
        self.table.setShowGrid(False)

        # Table view JScrollPane.
        scroll_pane_table = JScrollPane()
        scroll_pane_table.setPreferredSize(Dimension(self.online_table_w, 0))
        scroll_pane_table.getViewport().setBackground(Color.WHITE)
        scroll_pane_table.getViewport().setView((self.table))

        # Split view (vertical-right) container JPanel.
        cont_split_pane_vr = JPanel()
        cont_split_pane_vr.setLayout(BorderLayout())
        cont_split_pane_vr.add(panel_curr_status, BorderLayout.PAGE_START)
        cont_split_pane_vr.add(scroll_pane_table, BorderLayout.CENTER)
        cont_split_pane_vr.add(panel_online_usr, BorderLayout.PAGE_END)

        # Split view (horizontal) container JPanel.
        cont_split_pane_h = JPanel()
        cont_split_pane_h.setLayout(BorderLayout())
        cont_split_pane_h.add(cont_split_pane_vr, BorderLayout.LINE_START)
        cont_split_pane_h.add(panel_im_inner, BorderLayout.LINE_END)

        # Main JMenuBar.
        main_menu_bar = JMenuBar()

        # "File" JMenu.
        menu_file = JMenu("File")
        menu_file.setMnemonic(KeyEvent.VK_A)
        menu_file.getAccessibleContext().setAccessibleDescription("File operations")

        # "Exit" JMenuItem.
        reconnect_mitem = JMenuItem(
            "Exit",
            KeyEvent.VK_T,
            actionPerformed=self._action_dispose_and_exit
            )
        reconnect_mitem.setAccelerator(
            KeyStroke.getKeyStroke(KeyEvent.VK_F10, ActionEvent.ALT_MASK)
            )
        reconnect_mitem.getAccessibleContext().setAccessibleDescription("Exit")
        menu_file.add(reconnect_mitem)

        # "Connection" JMenu.
        menu_connection = JMenu("Connection")
        menu_connection.setMnemonic(KeyEvent.VK_A)
        menu_connection.getAccessibleContext().setAccessibleDescription(
            "Server Connection Manipulations"
            )

        # "Re-connect" JMenuItem.
        reconnect_mitem = JMenuItem(
            "Re-connect",
            KeyEvent.VK_T,
            actionPerformed=self.restart_session
            )
        reconnect_mitem.setAccelerator(
            KeyStroke.getKeyStroke(KeyEvent.VK_1, ActionEvent.ALT_MASK)
            )
        reconnect_mitem.getAccessibleContext().setAccessibleDescription(
            "Re-connect to the server"
            )
        menu_connection.add(reconnect_mitem)

        # "Disconnect" JMenuItem.
        disconnect_mitem = JMenuItem(
            "Disconnect",
            KeyEvent.VK_T,
            actionPerformed=self.stop_session
            )
        disconnect_mitem.setAccelerator(
            KeyStroke.getKeyStroke(KeyEvent.VK_2, ActionEvent.ALT_MASK)
            )
        disconnect_mitem.getAccessibleContext().setAccessibleDescription(
            "Disconnect from the server"
            )
        menu_connection.add(disconnect_mitem)

        main_menu_bar.add(menu_file)
        main_menu_bar.add(menu_connection)
        
        # Adding elements one to another.
        cont_split_pane_h.add(main_menu_bar, BorderLayout.PAGE_START)
  
        self.frame_main_cont.add(cont_split_pane_h)
        self.frame_main_cont.pack()
        self.frame_main_cont.setVisible(True)
        self.textfield_im_input.requestFocus()


    def _display_im(self, from_user, message):
        '''
        Display incoming message.
        :param from_user: The name of user sending the message 
                          to display in bold typeface.
        :param message:   The message itself.
        '''

        msg_prefix = "[{0} {1}]: ".format(
            datetime.fromtimestamp(
                time.time()
                ).strftime("%m/%d %H:%M:%S"),
            from_user
            )
        styled_label = SimpleAttributeSet()
        StyleConstants.setForeground(styled_label, self.colour_blue)
        StyleConstants.setBold(styled_label, True)
        self.styleddoc_textpane_im.insertString(
            self.styleddoc_textpane_im.getLength(),
            msg_prefix,
            styled_label
            )
        self.styleddoc_textpane_im.insertString(
            self.styleddoc_textpane_im.getLength(),
            "{0}\n".format(message),
            None
            )

    def _action_send_button(self, event=None):
        '''
        "Send" button action listener method.
        :param event: Event. Discarded.
        '''

        del event
        self.ready_to_send = False
        msg_text = self.textfield_im_input.getText()
        if self.textfield_im_input.getText():
            self.ready_to_send = True
        self._display_im("You", msg_text)
        self.sendmsg(msg_text, msgtype=0)
        self.textfield_im_input.setText(None)
        self.textfield_im_input.requestFocus()

    def _action_status_combo(self, event=None):
        '''
        Status combobox action listener method.
        :param event: Event. Discarded.
        '''

        del event
        selected_status_index = int(
            self.current_status_select_cbox.getSelectedIndex()
            )
        self.sendmsg(None, msgtype=1, command=0, primarykey=selected_status_index)

    def _action_dispose_and_exit(self, event=None):
        '''
        Exit action controls action listener method.
        :param event: Event. Discarded.
        '''

        del event
        self.stop_session()
        self.frame_main_cont.dispose()
        sys.exit(0)

    def restart_session(self, event=None):
        '''
        (Re)Connect to server and start message exchange session.
        :param event: Event. Discarded.
        '''

        del event
        self._display_im("sys", "before drop")
        # Tear down the connection if it is established.
        if self.is_running:
            self.stop_session()
        self._display_im("sys", "after drop")
        time.sleep(5)

        try:
            self._display_im("sys", "befor sockassign")
            # Creating client socket.
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Try to connect to server.
            self.socket_connect()
            if self.is_gui_instance:
                # Select "Online" status.
                # "_action_status_combo" action will be triggered
                # automatically.
                self.current_status_select_cbox.setSelectedIndex(0)

        except socket.error as err_msg:
            # In case of error keep retrying.
            self._display_im("System", err_msg)
        if self.is_running:
            # Start exchanging messages.
            self._im_exchange()
        else:
            self._display_im("System", "Gave up trying to connect to server.")


    def _im_exchange(self):
        '''
        Exchange messages between client and server.
        '''

        # While 'running' flag is True.
        while self.is_running:
            # Get the list of streams available for reading.
            # Select those amongst STDIN and the socket.
            # Note that this is the place where whole thing will fail on non-Unix
            # since the select call cannot actualle select stdin on these systems.
            rlist = list()
            wlist = list()
            elist = list()

            try:
                (rlist, wlist, elist) = select.select([self.client], [], [])
            except socket.error:
                self._display_im("System", "Error on select.")
                return
            finally:
                del wlist
                del elist
            if self.client in rlist:
                # Receiving message from server.
                # recv_data = read_stream.recv(self.RECV_BUFFER)
                (
                    recv_status,
                    recv_username,
                    recv_body,
                    recv_msgtype,
                    recv_command,
                    recv_action,
                    recv_primarykey,
                    recv_secondarykey
                ) = self.receivemsg()
                del recv_action
                del recv_secondarykey
                del recv_primarykey
                # recv_msgtype = recv_dict["type"]
                # recv_command = recv_dict[""]
                # If there is no message.
                if recv_status != 0:
                    if recv_status == 3:
                    #     self.stop_session()
                    #     break
                    # else:
                        continue
                else:
                    # Print received message.
                    if recv_msgtype == 0:
                        self._display_im(
                            recv_username,
                            "{0}".format(recv_body.strip())
                        )
                    # elif recv_msgtype == 1 and recv_command == 0:
                    #     dm_row_count = self.online_table_dm.getRowCount()
                    #     dm_col_count = self.online_table_dm.getColumnCount()
                    #     recv_set_status = self.usertbl_sel_values[recv_primarykey]
                    #     switch_duplicated_row = False
                    #     list_rows_to_remove = list()
                    #     switch_should_add_row = False
                    #     for dm_row_index in xrange(dm_row_count - 1, -1, -1):
                    #         col_username_value = self.online_table_dm.getValueAt(dm_row_index, 0)
                    #         col_status_value = self.online_table_dm.getValueAt(dm_row_index, 1)
                    #         if not col_username_value and not col_status_value:
                    #             list_rows_to_remove.append(dm_row_index)   
                    #             switch_should_add_row = True
                    #         elif col_username_value == recv_username:
                    #             if col_status_value == recv_set_status:
                    #                 # Already has the status that is about to be set.
                    #                 switch_should_add_row = False

                    #                 if switch_duplicated_row:
                    #                     list_rows_to_remove.append(dm_row_index)                                        
                    #                     switch_should_add_row = False
                    #                 else:
                    #                     switch_duplicated_row = True
                    #             else:
                    #                 self.online_table_dm.setValueAt(recv_set_status, dm_row_index, 1)
                    #                 self.online_table_dm.fireTableDataChanged()
                    #                 # Display "User changed their status" message.
                    #                 self._display_im("System", "{0} changed their status to \"{1}\"".format(recv_username, recv_set_status))
                    #         else:
                    #             switch_should_add_row = True

                    #     for row_to_remove in list_rows_to_remove:
                    #         self.online_table_dm.removeRow(row_to_remove)
                    #         self.online_table_dm.fireTableRowsDeleted(dm_row_index, dm_row_index)

                    #     if switch_should_add_row:
                    #         self.online_table_dm.addRow([recv_username, recv_set_status])
                    #         self.online_table_dm.fireTableDataChanged()
                    elif recv_msgtype == 1 and recv_command == 7:
                        self._display_im("System", "User {0} has gone offline".format(recv_username))
            else:
                # Reading the line of user input.
                if not self.ready_to_send:
                    continue
                msg = self.textfield_im_input.getText()
                # If the 'quit' command received.
                self.sendmsg(msg)


def main():
    '''
    The Main. 
    Parse arguments and run a client session.
    '''
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
    #     self._display_im(_VERSIONINO_MSG)
    #     sys.exit(0)

    # Else print an invitation message and continue to initialise.
    # self._display_im("{0}\n\n{1}".format(_PROLOGUE_MSG, _INVITE_MSG))

    connection = ChatClientGUI(parsed_args.host, parsed_args.port, parsed_args.username)
    try:
        connection.restart_session()
    # If user hits Ctrl + C
    except KeyboardInterrupt:
        connection.stop_session()
        sys.exit(0)

if __name__ == '__main__':
    # if-main; That is if we are calle by name "__main__"
    # then run "main()" function.
    main()

# EOF
