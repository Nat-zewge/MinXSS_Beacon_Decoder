import sys
import os
import logging
from configparser import ConfigParser
from PySide2 import QtGui, QtCore
from PySide2.QtWidgets import QMainWindow, QApplication
from PySide2.QtGui import QColor
from ui_mainWindow import Ui_MainWindow
import connect_port_get_packet
import file_upload
import datetime
from serial.tools import list_ports  # This is pyserial, not plain serial
import minxss_parser

"""Call the GUI and attach it to functions."""
__author__ = "James Paul Mason"
__contact__ = "jmason86@gmail.com"


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.green_color = QColor(55, 195, 58)
        self.yellow_color = QColor(244, 212, 66)
        self.red_color = QColor(242, 86, 77)
        self.connected_port = None

        self.log = self.create_log()  # Debug log
        self.setupUi(self)
        self.setup_available_ports()
        self.assign_widgets()
        self.setup_last_used_settings()
        self.setup_output_log()  # Log of buffer data
        self.port_read_thread = PortReadThread(self.read_port, self.stop_read)
        QApplication.instance().aboutToQuit.connect(self.prepare_to_exit)
        self.show()

    def setup_available_ports(self):
        """
        Determine what ports are available for serial reading and populate the combo box with these options
        """
        self.comboBox_serialPort.clear()
        list_port_info_objects = list_ports.comports()
        port_names = [x[0] for x in list_port_info_objects]
        self.comboBox_serialPort.addItems(port_names)

    def assign_widgets(self):
        """
        Connect UI interactive elements to other functions herein so that code is executed upon user interaction with these elements
        """
        self.actionConnect.triggered.connect(self.connect_clicked)
        self.checkBox_saveLog.stateChanged.connect(self.save_log_toggled)
        self.checkBox_forwardData.stateChanged.connect(self.forward_data_toggled)
        self.checkBox_decodeKiss.stateChanged.connect(self.decode_kiss_toggled)
        self.actionCompletePass.triggered.connect(self.complete_pass_clicked)

    def setup_last_used_settings(self):
        parser = ConfigParser()
        config_filename = os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg")
        if not self.config_file_exists_and_is_not_empty(config_filename):
            self.write_default_config(config_filename)

        parser.read(config_filename)
        self.set_instance_variables_from_config(parser)

    @staticmethod
    def config_file_exists_and_is_not_empty(config_filename):
        return os.path.isfile(config_filename) and os.stat(config_filename).st_size != 0

    @staticmethod
    def write_default_config(config_filename):
        with open(config_filename, "w") as config_file:
            print("[input_properties]", file=config_file)
            print("serial_port = 3", file=config_file)
            print("baud_rate = 19200", file=config_file)
            print("ip_address = localhost", file=config_file)
            print("port = 10000", file=config_file)
            print("decode_kiss = True", file=config_file)
            print("forward_data = True", file=config_file)
            print("latitude = 40.240", file=config_file)
            print("longitude = -105.2353", file=config_file)

    def set_instance_variables_from_config(self, parser):
        self.comboBox_serialPort.insertItem(0, parser.get('input_properties', 'serial_port'))
        self.comboBox_serialPort.setCurrentIndex(0)
        self.lineEdit_baudRate.setText(parser.get('input_properties', 'baud_rate'))
        self.lineEdit_ipAddress.setText(parser.get('input_properties', 'ip_address'))
        self.lineEdit_ipPort.setText(parser.get('input_properties', 'port'))
        self.lineEdit_latitude.setText(parser.get('input_properties', 'latitude'))
        self.lineEdit_longitude.setText(parser.get('input_properties', 'longitude'))
        self.checkBox_decodeKiss.setChecked(self.str2bool(parser.get('input_properties', 'decode_kiss')))
        self.checkBox_forwardData.setChecked(self.str2bool(parser.get('input_properties', 'forward_data')))

    @staticmethod
    def str2bool(bool_string):
        if bool_string == 'True':
            return True
        if bool_string == 'False':
            return False
        raise ValueError('Can only accept exact strings "True" or "False". Was passed {}'.format(bool_string))

    def connect_clicked(self):
        self.write_gui_config_options_to_config_file()

        connect_button_text = str(self.actionConnect.iconText())
        if connect_button_text == "Connect":
            self.connect_to_port()
        else:
            self.disconnect_from_port()

    def write_gui_config_options_to_config_file(self):
        config = ConfigParser()
        config.read('input_properties.cfg')
        config.set('input_properties', 'serial_port', self.comboBox_serialPort.currentText())
        config.set('input_properties', 'baud_rate', self.lineEdit_baudRate.text())
        config.set('input_properties', 'ip_address', self.lineEdit_ipAddress.text())
        config.set('input_properties', 'port', self.lineEdit_ipPort.text())
        config.set('input_properties', 'decode_kiss', str(self.checkBox_decodeKiss.isChecked()))
        config.set('input_properties', 'forward_data', str(self.checkBox_forwardData.isChecked()))
        config.set('input_properties', 'latitude', self.lineEdit_latitude.text())
        config.set('input_properties', 'longitude', self.lineEdit_longitude.text())
        with open(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg"), 'w') as configfile:
            config.write(configfile)

    def connect_to_port(self):
        self.log.info("Attempting to connect to port.")

        self.toggle_connect_button(is_currently_connect=True)

        if self.user_chose_serial_port():
            self.connected_port, port_readable = self.connect_to_serial_port()
        else:  # user chose TCP/IP socket
            self.connected_port, port_readable = self.connect_to_socket_port()

        if port_readable:
            self.port_read_thread.start()
            self.display_gui_reading()
        else:
            self.display_gui_read_failed()

    def toggle_connect_button(self, is_currently_connect):
        if is_currently_connect:
            connect_button_text = 'Disconnect'
        else:
            connect_button_text = 'Connect'
        self.actionConnect.setText(QApplication.translate("MainWindow", connect_button_text, None, -1))

    def user_chose_serial_port(self):
        if self.tabWidget_serialIp.currentIndex() == self.tabWidget_serialIp.indexOf(self.serial):
            return True
        else:
            return False  # implying user chose TCP/IP socket

    def connect_to_serial_port(self):
        port = self.comboBox_serialPort.currentText()
        baud_rate = self.lineEdit_baudRate.text()

        connected_port = connect_port_get_packet.connect_serial(port, baud_rate, self.log)
        port_readable = connected_port.testRead()
        if port_readable:
            self.log.info('Successfully connected to serial port')
        else:
            self.log.warning('Failed to connect to serial port.')
        return connected_port, port_readable

    def connect_to_socket_port(self):
        ip_address = self.lineEdit_ipAddress.text()
        port = self.lineEdit_ipPort.text()

        connect_socket = connect_port_get_packet.ConnectSocket(ip_address, port, self.log)
        connected_port = connect_socket.connect_to_port()
        port_readable = connect_socket.port_readable

        return connected_port, port_readable

    def display_gui_reading(self):
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Foreground, self.green_color)
        if self.user_chose_serial_port():
            self.label_serialStatus.setText(QApplication.translate("MainWindow", "Reading", None, -1))
            self.label_serialStatus.setPalette(palette)
        else:
            self.label_socketStatus.setText(QApplication.translate("MainWindow", "Reading", None, -1))
            self.label_socketStatus.setPalette(palette)

    def display_gui_read_failed(self):
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Foreground, self.red_color)
        if self.user_chose_serial_port:
            self.label_serialStatus.setText(QApplication.translate("MainWindow", "Read failed", None, -1))
            self.label_serialStatus.setPalette(palette)
        else:
            self.label_socketStatus.setText(QApplication.translate("MainWindow", "Read failed", None, -1))
            self.label_socketStatus.setPalette(palette)

    def disconnect_from_port(self):
        self.log.info("Attempting to disconnect from port")

        # Update the GUI to connect button
        self.actionConnect.setText(
            QApplication.translate("MainWindow", "Connect", None, -1))
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Foreground, self.red_color)
        if self.tabWidget_serialIp.currentIndex() == self.tabWidget_serialIp.indexOf(self.serial):
            self.label_serialStatus.setText(
                QApplication.translate("MainWindow", "Port closed", None, -1))
            self.label_serialStatus.setPalette(palette)
        else:
            self.label_socketStatus.setText(
                QApplication.translate("MainWindow", "Port closed", None, -1))
            self.label_socketStatus.setPalette(palette)

        # Actually close the port
        self.stop_read()

    def complete_pass_clicked(self):
        """
        Purpose:
            Respond to the complete pass button being clicked -- upload the binary output data, which is handled in a separate function
         Input:
            None
         Output:
            None
        """
        self.upload_data()

    def read_port(self):
        """
        Purpose:
            Read the buffer data from the port (be it serial or socket) in an infinite loop; decode and display any MinXSS housekeeping packets
         Input:
            None
         Output:
            None
        """
        # Infinite loop to read the port and display the data in the GUI and optionally write to output file
        while(True):
            bufferData = self.connected_port.read_packet()
            if len(bufferData) > 0:
                # Decode KISS escape characters if necessary
                if self.checkBox_decodeKiss.isChecked:
                    bufferData = bufferData.replace(bytearray([0xdb, 0xdc]), bytearray([0xc0]))  # C0 is a special KISS character that get replaced; unreplace it
                    bufferData = bufferData.replace(bytearray([0xdb, 0xdd]), bytearray([0xdb]))  # DB is a special KISS character that get replaced; unreplace it
                formattedBufferData = ' '.join('0x{:02x}'.format(x) for x in bufferData)
                self.textBrowser_serialOutput.append(formattedBufferData)
                self.textBrowser_serialOutput.verticalScrollBar().setValue(self.textBrowser_serialOutput.verticalScrollBar().maximum())

                if self.checkBox_saveLog.isChecked:
                    # Human readable
                    bufferOutputLog = open(self.bufferOutputFilename, 'a')  # append to existing file
                    bufferOutputLog.write(formattedBufferData)
                    bufferOutputLog.closed

                    # Binary
                    bufferOutputBinaryLog = open(self.bufferOutputBinaryFilename, 'ab')  # append to existing file
                    bufferOutputBinaryLog.write(bufferData)
                    bufferOutputBinaryLog.closed

                # Parse and interpret the binary data into human readable telemetry
                minxssParser = minxss_parser.Minxss_Parser(bufferData, self.log)
                selectedTelemetryDictionary = minxssParser.parsePacket(bufferData)

                # If valid data, update GUI with telemetry points
                if selectedTelemetryDictionary != -1:
                    ##
                    # Display numbers in GUI
                    ##

                    # Current timestamp
                    self.label_lastPacketTime.setText("Last packet at: {} local, {} UTC".format(datetime.datetime.now().isoformat(), datetime.datetime.utcnow().isoformat()))

                    # Spacecraft State
                    self.label_flightModel.setText("{0:0=1d}".format(selectedTelemetryDictionary['FlightModel']))
                    self.label_commandAcceptCount.setText("{0:0=1d}".format(selectedTelemetryDictionary['CommandAcceptCount']))
                    if selectedTelemetryDictionary['SpacecraftMode'] == 0:
                        self.label_spacecraftMode.setText("Unknown")
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 1:
                        self.label_spacecraftMode.setText("Phoenix")
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 2:
                        self.label_spacecraftMode.setText("Safe")
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 4:
                        self.label_spacecraftMode.setText("Science")
                    if selectedTelemetryDictionary['PointingMode'] == 0:
                        self.label_pointingMode.setText("Coarse Point")
                    elif selectedTelemetryDictionary['PointingMode'] == 1:
                        self.label_pointingMode.setText("Fine Point")
                    if selectedTelemetryDictionary['EnableX123'] == 1:
                        self.label_enableX123.setText("Yes")
                    else:
                        self.label_enableX123.setText("No")
                    if selectedTelemetryDictionary['EnableSps'] == 1:
                        self.label_enableSps.setText("Yes")
                    else:
                        self.label_enableSps.setText("No")
                    if selectedTelemetryDictionary['Eclipse'] == 1:
                        self.label_eclipse.setText("Eclipse")
                    else:
                        self.label_eclipse.setText("In Sun")

                    # Solar Data
                    self.label_spsX.setText("{0:.2f}".format(round(selectedTelemetryDictionary['SpsX'], 2)))
                    self.label_spsY.setText("{0:.2f}".format(round(selectedTelemetryDictionary['SpsY'], 2)))
                    self.label_xp.setText("{0:.2f}".format(round(selectedTelemetryDictionary['Xp'], 2)))

                    # Power
                    self.label_batteryVoltage.setText("{0:.2f}".format(round(selectedTelemetryDictionary['BatteryVoltage'], 2)))
                    if selectedTelemetryDictionary['BatteryChargeCurrent'] > selectedTelemetryDictionary['BatteryDischargeCurrent']:
                        batteryCurrent = selectedTelemetryDictionary['BatteryChargeCurrent'] / 1e3
                        self.label_batteryCurrentText.setText("Battery Charge Current")
                    else:
                        batteryCurrent = selectedTelemetryDictionary['BatteryDischargeCurrent'] / 1e3
                        self.label_batteryCurrentText.setText("Battery Discharge Current")
                    self.label_batteryCurrent.setText("{0:.2f}".format(round(batteryCurrent, 2)))
                    solarPanelMinusYPower = selectedTelemetryDictionary['SolarPanelMinusYVoltage'] * selectedTelemetryDictionary['SolarPanelMinusYCurrent'] / 1e3
                    self.label_solarPanelMinusYPower.setText("{0:.2f}".format(round(solarPanelMinusYPower, 2)))
                    solarPanelPlusXPower = selectedTelemetryDictionary['SolarPanelPlusXVoltage'] * selectedTelemetryDictionary['SolarPanelPlusXCurrent'] / 1e3
                    self.label_solarPanelPlusXPower.setText("{0:.2f}".format(round(solarPanelPlusXPower, 2)))
                    solarPanelPlusYPower = selectedTelemetryDictionary['SolarPanelPlusYVoltage'] * selectedTelemetryDictionary['SolarPanelPlusYCurrent'] / 1e3
                    self.label_solarPanelPlusYPower.setText("{0:.2f}".format(round(solarPanelPlusYPower, 2)))

                    # Temperature
                    self.label_commBoardTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['CommBoardTemperature'], 2)))
                    self.label_batteryTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['BatteryTemperature'], 2)))
                    self.label_epsBoardTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['EpsBoardTemperature'], 2)))
                    self.label_cdhTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['CdhBoardTemperature'], 2)))
                    self.label_motherboardTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['MotherboardTemperature'], 2)))
                    self.label_solarPanelMinusYTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['SolarPanelMinusYTemperature'], 2)))
                    self.label_solarPanelPlusXTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['SolarPanelPlusXTemperature'], 2)))
                    self.label_solarPanelPlusYTemperature.setText("{0:.2f}".format(round(selectedTelemetryDictionary['SolarPanelPlusYTemperature'], 2)))

                    # Setup color palettes
                    paletteGreen = QtGui.QPalette()
                    paletteGreen.setColor(QtGui.QPalette.Foreground, self.green_color)
                    paletteYellow = QtGui.QPalette()
                    paletteYellow.setColor(QtGui.QPalette.Foreground, self.yellow_color)
                    paletteRed = QtGui.QPalette()
                    paletteRed.setColor(QtGui.QPalette.Foreground, self.red_color)

                    ##
                    # Color code telemetry
                    ##

                    # Spacecraft State
                    if selectedTelemetryDictionary['SpacecraftMode'] == 0:
                        self.label_spacecraftMode.setPalette(paletteRed)
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 1:
                        self.label_spacecraftMode.setPalette(paletteRed)
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 2:
                        self.label_spacecraftMode.setPalette(paletteYellow)
                    elif selectedTelemetryDictionary['SpacecraftMode'] == 4:
                        self.label_spacecraftMode.setPalette(paletteGreen)
                    if selectedTelemetryDictionary['PointingMode'] == 0:
                        self.label_pointingMode.setPalette(paletteYellow)
                    elif selectedTelemetryDictionary['PointingMode'] == 1:
                        self.label_pointingMode.setPalette(paletteGreen)

                    # Solar Data
                    if abs(selectedTelemetryDictionary['SpsX']) <= 3.0:
                        self.label_spsX.setPalette(paletteGreen)
                    else:
                        self.label_spsX.setPalette(paletteRed)
                    if abs(selectedTelemetryDictionary['SpsY']) <= 3.0:
                        self.label_spsY.setPalette(paletteGreen)
                    else:
                        self.label_spsY.setPalette(paletteRed)
                    if selectedTelemetryDictionary['Xp'] <= 24860.0 and selectedTelemetryDictionary['Xp'] >= 0:
                        self.label_xp.setPalette(paletteGreen)
                    else:
                        self.label_xp.setPalette(paletteRed)

                    # Power
                    if solarPanelMinusYPower >= -1.0 and solarPanelMinusYPower <= 9.7:
                        self.label_solarPanelMinusYPower.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelMinusYPower.setPalette(paletteRed)
                    if solarPanelPlusXPower >= -1.0 and solarPanelPlusXPower <= 5.9:
                        self.label_solarPanelPlusXPower.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelPlusXPower.setPalette(paletteRed)
                    if solarPanelPlusYPower >= -1.0 and solarPanelPlusYPower <= 10.4:
                        self.label_solarPanelPlusYPower.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelPlusYPower.setPalette(paletteRed)
                    if selectedTelemetryDictionary['BatteryVoltage'] >= 7.1:
                        self.label_batteryVoltage.setPalette(paletteGreen)
                    elif selectedTelemetryDictionary['BatteryVoltage'] >= 6.9:
                        self.label_batteryVoltage.setPalette(paletteYellow)
                    else:
                        self.label_batteryVoltage.setPalette(paletteRed)
                    if batteryCurrent >= 0 and batteryCurrent <= 2.9:
                        self.label_batteryCurrent.setPalette(paletteGreen)
                    else:
                        self.label_batteryCurrent.setPalette(paletteRed)

                    # Temperature
                    if selectedTelemetryDictionary['CommBoardTemperature'] >= -8.0 and \
                       selectedTelemetryDictionary['CommBoardTemperature'] <= 60.0:
                        self.label_commBoardTemperature.setPalette(paletteGreen)
                    else:
                        self.label_commBoardTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['BatteryTemperature'] >= 5.0 and \
                       selectedTelemetryDictionary['BatteryTemperature'] <= 25:
                        self.label_batteryTemperature.setPalette(paletteGreen)
                    elif selectedTelemetryDictionary['BatteryTemperature'] >= 2.0 and selectedTelemetryDictionary['BatteryTemperature'] < 5.0 or selectedTelemetryDictionary['BatteryTemperature'] > 25.0:
                        self.label_batteryTemperature.setPalette(paletteYellow)
                    else:
                        self.label_batteryTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['EpsBoardTemperature'] >= -8.0 and \
                       selectedTelemetryDictionary['EpsBoardTemperature'] <= 45.0:
                        self.label_epsBoardTemperature.setPalette(paletteGreen)
                    else:
                        self.label_epsBoardTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['CdhBoardTemperature'] >= -8.0 and \
                       selectedTelemetryDictionary['CdhBoardTemperature'] <= 29.0:
                        self.label_cdhTemperature.setPalette(paletteGreen)
                    else:
                        self.label_cdhTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['MotherboardTemperature'] >= -13.0 and \
                       selectedTelemetryDictionary['MotherboardTemperature'] <= 28.0:
                        self.label_motherboardTemperature.setPalette(paletteGreen)
                    else:
                        self.label_motherboardTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['SolarPanelMinusYTemperature'] >= -42.0 and \
                       selectedTelemetryDictionary['SolarPanelMinusYTemperature'] <= 61.0:
                        self.label_solarPanelMinusYTemperature.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelMinusYTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['SolarPanelPlusXTemperature'] >= -24.0 and \
                       selectedTelemetryDictionary['SolarPanelPlusXTemperature'] <= 65.0:
                        self.label_solarPanelPlusXTemperature.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelPlusXTemperature.setPalette(paletteRed)
                    if selectedTelemetryDictionary['SolarPanelPlusYTemperature'] >= -35.0 and \
                       selectedTelemetryDictionary['SolarPanelPlusYTemperature'] <= 58.0:
                        self.label_solarPanelPlusYTemperature.setPalette(paletteGreen)
                    else:
                        self.label_solarPanelPlusYTemperature.setPalette(paletteRed)

    def stop_read(self):
        """
        Purpose:
            Respond to disconnect button being clicked -- disconnect from the port, be it serial or socket
        Input:
            None
        Output:
            None
        """
        self.connected_port.close()

        # Update GUI
        self.label_serialStatus.setText(QApplication.translate("MainWindow", "Port closed", None, -1))
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Foreground, self.red_color)
        self.label_serialStatus.setPalette(palette)

    def save_log_toggled(self):
        """
        Purpose:
            Respond to the user toggling the save log button (create a new output data log as appropriate)
        Input:
            None
        Output:
            Creates a log file on disk if toggling on
        """
        if self.checkBox_saveLog.isChecked():
            self.setup_output_log()
        else:
            # Update the GUI for the log file - not saving
            self.textBrowser_savingToLogFile.setText("Not saving to log file")
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.Text, self.red_color)
            self.textBrowser_savingToLogFile.setPalette(palette)

    def forward_data_toggled(self):
        """
        Purpose:
           Respond to the user toggling the forward data button (update the GUI to correspond)
        Input:
            None
        Output:
            Creates a log file on disk if toggling on
        """
        if self.checkBox_forwardData.isChecked():
            self.label_uploadStatus.setText("Upload status: Idle")

            # Write the input settings used to the input_properties.cfg configuration file
            config = ConfigParser()
            config.read('input_properties.cfg')
            config.set('input_properties', 'forwardData', "True")
            self.log.info("Forward data set to True")
            with open(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg"), 'wb') as configfile:
                config.write(configfile)
        else:
            self.label_uploadStatus.setText("Upload status: Disabled")

            # Write the input settings used to the input_properties.cfg configuration file
            config = ConfigParser()
            config.read('input_properties.cfg')
            config.set('input_properties', 'forwardData', "False")
            self.log.info("Forward data set to False")
            with open(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg"), 'wb') as configfile:
                config.write(configfile)

    def decode_kiss_toggled(self):
        """
        Purpose:
            Respond to the user toggling the forward data button (update the GUI to correspond)
        Input:
            None
        Output:
            Creates a log file on disk if toggling on
        """
        if self.checkBox_decodeKiss.isChecked():
            config = ConfigParser()
            config.read('input_properties.cfg')
            config.set('input_properties', 'decodeKiss', "True")
            self.log.info("Decode KISS set to True")
            with open(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg"), 'wb') as configfile:
                config.write(configfile)
        else:
            config = ConfigParser()
            config.read('input_properties.cfg')
            config.set('input_properties', 'decodeKiss', "False")
            self.log.info("Decode KISS set to False")
            with open(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "input_properties.cfg"), 'wb') as configfile:
                config.write(configfile)

    def setup_output_log(self):
        """
        Purpose:
            Create the output files for a human readable hex interpretation of the MinXSS data and a binary file
        Input:
            None
        Output:
            A .tex file with hex MinXSS data and a .dat file with binary MinXSS data
        """
        # Human readable log
        if not os.path.exists(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output")):
            os.makedirs(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output"))
        self.bufferOutputFilename = os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output", datetime.datetime.now().isoformat().replace(':', '_')) + ".txt"

        with open(self.bufferOutputFilename, 'w') as bufferOutputLog:
            # Update the GUI for the log file - is saving
            self.textBrowser_savingToLogFile.setText("Saving to log file: " + self.bufferOutputFilename)
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.Text, self.green_color)
            self.textBrowser_savingToLogFile.setPalette(palette)
        bufferOutputLog.closed

        # Binary log
        if not os.path.exists(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output")):
            os.makedirs(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output"))
        latitude = self.lineEdit_latitude.text()
        longitude = self.lineEdit_longitude.text()

        self.bufferOutputBinaryFilename = os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "output", datetime.datetime.now().isoformat().replace(':', '_')) + "_" + latitude + "_" + longitude + ".dat"

        with open(self.bufferOutputBinaryFilename, 'w') as bufferOutputBinaryLog:
            self.log.info("Opening binary file for buffer data")
        bufferOutputBinaryLog.closed

    def create_log(self):
        """
        Purpose:
            Initialize a debugger log file
        Input:
            None
        Output:
            The .log file for informational and debug statements
        """
        if not os.path.exists(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "log")):
            os.makedirs(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "log"))
        log = logging.getLogger('serial_reader_debug')
        handler = logging.FileHandler(os.path.join(os.path.expanduser("~"), "MinXSS_Beacon_Decoder", "log", "minxss_beacon_decoder_debug.log"))
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)
        log.info("Launched MinXSS Beacon Decoder")
        return log

    def upload_data(self):
        """
        Purpose:
            Upload binary data to the MinXSS team
        Input:
            None (though will grab the .dat binary file from disk)
        Output:
            None (though will send that .dat binary file over the internet via scp to a server handled by the MinXSS team)
        """
        if self.checkBox_forwardData.isChecked:
            self.label_uploadStatus.setText("Upload status: Uploading")
            file_upload.upload(self.bufferOutputBinaryFilename, self.log)
            self.label_uploadStatus.setText("Upload status: Complete")

    def prepare_to_exit(self):
        """
        Purpose:
            Respond to the user clicking the close application button -- handle any last business, which is just uploading the binary file in this case
        Input:
            None
        Output:
            None
        """
        self.log.info("About to quit")
        self.upload_data()
        self.log.info("Closing MinXSS Beacon Decoder")


class PortReadThread(QtCore.QThread):
    """
    Purpose:
        Separate class that handles reading the port in an infinite loop -- means the main loop can still be responsive to user interaction
    Input:
        QtCore.QThread: The thread to run this task on
    Output:
        N/A
    """
    def __init__(self, target, slotOnFinished=None):
        super(PortReadThread, self).__init__()
        self.target = target
        if slotOnFinished:
            self.finished.connect(slotOnFinished)

    def run(self, *args, **kwargs):
        """
        Purpose:
            Run a specific block of code in the thread
        Input:
            args, kwargs: flexible input for arguments
        Output:
            None
        """
        self.target(*args, **kwargs)


def main():
    app = QApplication(sys.argv)
    mainWin = MainWindow()
    ret = app.exec_()
    sys.exit(ret)


if __name__ == '__main__':
    main()
