"""Parse MinXSS packet"""
__author__ = "James Paul Mason"
__contact__ = "jmason86@gmail.com"

import os
import logging
import pdb, binascii
from numpy import int8, uint8, int16, uint16, int32, uint32 

class Minxss_Parser():
    def __init__(self, minxssPacket, log):
        self.log = log # debug log

    # Purpose:
    #   Top level wrapper function to take serial data and return parsed and interpretted telemetry as a dictionary
    # Input:
    #   minxssPacket [bytearray]: The direct output of the python serial line (connect_serial_decode_kiss.read()), or simulated data in that format
    # Output:
    #   selectedTelemetryDictionary [dictionary]: The telemetry with key/value pairs
    #
    def parse_packet(self, minxss_packet):
        # Find the sync bytes (0x08, 0x19), reframe the packet to start after sync
        syncOffset = self.findSyncStartIndex(minxss_packet)
        if syncOffset == -1:
            self.log.error("No start sync bytes found in minxss_parser, exiting.")
            return None
        else:
            minxss_packet = minxss_packet[syncOffset:len(minxss_packet)]
        
        # Prepare a dictionary for storage of telemetry points
        selected_telemetry_dictionary = {}
        
        # Get the telemetry points
        # Note: Second index in range of minxssPacket must be +1 what you'd normally expect because python is wonky
        # For example, to grab bytes at indices 3 and 4, you don't do minxssPacket[3:4], you have to do minxssPacket[3:5]
        selected_telemetry_dictionary['FlightModel'] = self.decodeFlightModel(minxss_packet[51])                                       # [Unitless]
        selected_telemetry_dictionary['CommandAcceptCount'] = self.decodeCommandAcceptCount(minxss_packet[16:16 + 2])                    # [#]
        selected_telemetry_dictionary['SpacecraftMode'] = self.decodeSpacecraftMode(minxss_packet[12])                                 # [Unitless]
        selected_telemetry_dictionary['PointingMode'] = self.decodePointingMode(minxss_packet[13])                                     # [Unitless]
        selected_telemetry_dictionary['EnableX123'] = self.decodeEnableX123(minxss_packet[88:88 + 2])                                    # [Boolean]
        selected_telemetry_dictionary['EnableSps'] = self.decodeEnableSps(minxss_packet[88:88 + 2])                                      # [Boolean]
        selected_telemetry_dictionary['Eclipse'] = self.decodeEclipse(minxss_packet[12])                                               # [Boolean]
        selected_telemetry_dictionary['SpsX'] = self.decodeSps(minxss_packet[204:204 + 2])                                               # [deg]
        selected_telemetry_dictionary['SpsY'] = self.decodeSps(minxss_packet[206:206 + 2])                                               # [deg]
        selected_telemetry_dictionary['Xp'] = self.decodeXp(minxss_packet[192:192 + 4])                                                  # [DN]
        selected_telemetry_dictionary['CommBoardTemperature'] = self.decodeBytesTemperature(minxss_packet[122:122 + 2])                  # [deg C]
        selected_telemetry_dictionary['BatteryTemperature'] = self.decodeBytesTemperatureBattery(minxss_packet[174:174 + 2])             # [deg C]
        selected_telemetry_dictionary['EpsBoardTemperature'] = self.decodeBytesTemperature(minxss_packet[128:128 + 2])                   # [deg C]
        selected_telemetry_dictionary['CdhBoardTemperature'] = self.decodeBytesTemperature(minxss_packet[86:86 + 2])                     # [deg C]
        selected_telemetry_dictionary['MotherboardTemperature'] = self.decodeBytesTemperature(minxss_packet[124:124 + 2])                # [deg C]
        selected_telemetry_dictionary['SolarPanelMinusYTemperature'] = self.decodeBytesTemperatureSolarPanel(minxss_packet[160:160 + 2]) # [deg C]
        selected_telemetry_dictionary['SolarPanelPlusXTemperature'] = self.decodeBytesTemperatureSolarPanel(minxss_packet[162:162 + 2])  # [deg C]
        selected_telemetry_dictionary['SolarPanelPlusYTemperature'] = self.decodeBytesTemperatureSolarPanel(minxss_packet[164:164 + 2])  # [deg C]
        selected_telemetry_dictionary['BatteryVoltage'] = self.decodeBytesFuelGaugeBatteryVoltage(minxss_packet[132:132 + 2])            # [V]
        selected_telemetry_dictionary['BatteryChargeCurrent'] = self.decodeBytesBatteryCurrent(minxss_packet[168:168 + 2])               # [mA]
        selected_telemetry_dictionary['BatteryDischargeCurrent'] = self.decodeBytesBatteryCurrent(minxss_packet[172:172 + 2])            # [mA]
        selected_telemetry_dictionary['SolarPanelMinusYCurrent'] = self.decodeBytesSolarArrayCurrent(minxss_packet[136:136 + 2])         # [mA]
        selected_telemetry_dictionary['SolarPanelPlusXCurrent'] = self.decodeBytesSolarArrayCurrent(minxss_packet[140:140 + 2])          # [mA]
        selected_telemetry_dictionary['SolarPanelPlusYCurrent'] = self.decodeBytesSolarArrayCurrent(minxss_packet[144:144 + 2])          # [mA]
        selected_telemetry_dictionary['SolarPanelMinusYVoltage'] = self.decodeBytesSolarArrayVoltage(minxss_packet[138:138 + 2])         # [V]
        selected_telemetry_dictionary['SolarPanelPlusXVoltage'] = self.decodeBytesSolarArrayVoltage(minxss_packet[142:142 + 2])          # [V]
        selected_telemetry_dictionary['SolarPanelPlusYVoltage'] = self.decodeBytesSolarArrayVoltage(minxss_packet[146:146 + 2])          # [V]
        
        self.log.info("From MinXSS parser:")
        self.log.info(selected_telemetry_dictionary)
        return selected_telemetry_dictionary

    # Purpose:
    #   Find the start of the MinXSS packet and return the index within minxssSerialData
    # Input:
    #   minxssSerialData [bytearray]: The direct output of the python serial line (connect_serial_decode_kiss.read()), or simulated data in that format
    # Output:
    #   packetStartIndex [int]: The index within minxssSerialData where the start sync bytes were found. -1 if not found.
    #
    def findSyncStartIndex(self, minxssSerialData):
        syncBytes = bytearray([0x08, 0x19]) # Other Cubesats: Change these start sync bytes to whatever you are using to define the start of your packet
        packetStartIndex = bytearray(minxssSerialData).find(syncBytes)
        return packetStartIndex
    
    # Purpose:
    #   Find the end of the MinXSS packet and return the index within minxssSerialData
    # Input:
    #   minxssSerialData [bytearray]: The direct output of the python serial line (connect_serial_decode_kiss.read()), or simulated data in that format
    # Output:
    #   packetStopIndex [int]: The index within minxssSerialData where the end sync bytes were found. -1 if not found.
    #
    def findSyncStopIndex(self, minxssSerialData):
        syncBytes = bytearray([0xa5, 0xa5]) # Other CubeSats: Change these stop sync bytes to whatever you are using to define the end of your packet
        packetStopIndex = bytearray(minxssSerialData).find(syncBytes)
        return packetStopIndex
    
    # Purpose:
    #   Combine several bytes corresponding to a single telemetry point to a single integer
    # Input:
    #   bytearrayTemp [bytearray]: The bytes corresponding to the telemetry to decode.
    #                              Can accept any number of bytes but do not expect more than 4
    # Flags:
    #   returnUnsignedInt: Set this to 1 or True to return an unsigned integer instead of the default signed integer
    # Output:
    #   telemetryPointRaw [int]: The single integer for the telemetry point to be converted to human-readable by the appropriate function
    #
    def decodeBytes(self, bytearrayTemp, returnUnsignedInt = 0):
        if len(bytearrayTemp) == 1:
            return bytearrayTemp
        elif len(bytearrayTemp) == 2:
            if returnUnsignedInt:
                return uint16((int8(bytearrayTemp[1]) << 8) | uint8(bytearrayTemp[0]))
            else:
                return int16((uint8(bytearrayTemp[1]) << 8) | uint8(bytearrayTemp[0]))
        elif len(bytearrayTemp) == 4:
            if returnUnsignedInt:
                return uint32((uint8(bytearrayTemp[3]) << 24) | (uint8(bytearrayTemp[2] << 16)) |
                                (uint8(bytearrayTemp[1] << 8)) | (uint8(bytearrayTemp[0] << 0)))
            else:
                return int32((uint8(bytearrayTemp[3]) << 24) | (uint8(bytearrayTemp[2] << 16)) |
                                (uint8(bytearrayTemp[1] << 8)) | (uint8(bytearrayTemp[0] << 0)))
        else:
            self.log.debug("More bytes than expected")
                
    ##
    # The following functions all have the same purpose: to convert raw bytes to human-readable output.
    # Only the units will be commented on. The function and variable names are explicit and verbose for clarity.
    ##
    
    # Purpose:
    #   Convert raw telemetry to human-readable number in human-readable units
    # Input:
    #   bytearrayTemp [bytearray]: The bytes corresponding to the telemetry to decode.
    #                              Can accept any number of bytes but do not expect more than 4
    # Output:
    #   telemetryPoint [int, float, string, as appropriate]: The telemetry point in human-readable form and units
    #
    
    def decodeFlightModel(self, bytearrayTemp):
        flight_model = (bytearrayTemp & 0x0030) >> 4  # [Unitless]

        # Fix mistaken flight model number in final flight software burn
        if flight_model == 3:
            flight_model = 2
        elif flight_model == 4:
            flight_model = 3  # This is the engineering test unit (AKA FlatSat)
        return flight_model
    
    def decodeCommandAcceptCount(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp) # [#]
    
    def decodeSpacecraftMode(self, bytearrayTemp):
        return (bytearrayTemp & 0x07) # [Unitless]
    
    def decodePointingMode(self, bytearrayTemp):
        return (bytearrayTemp & 0x01) # [Unitless]
    
    def decodeEnableX123(self, bytearrayTemp):
        decodedByte = self.decodeBytes(bytearrayTemp)
        return (decodedByte & 0x0002) >> 1 # [Boolean]
    
    def decodeEnableSps(self, bytearrayTemp):
        decodedByte = self.decodeBytes(bytearrayTemp)
        return (decodedByte & 0x0004) >> 2 # [Boolean]
    
    def decodeSps(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp) / 1e4 * 3.0 # [deg]
    
    def decodeEclipse(self, bytearrayTemp):
        return (bytearrayTemp & 0x08) >> 3

    def decodeXp(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) # [DN]
    
    def decodeBytesTemperature(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp) / 256.0 # [deg C]
    
    def decodeBytesTemperatureBattery(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) * 0.18766 - 250.2 # [deg C]
    
    def decodeBytesTemperatureSolarPanel(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) * 0.1744 - 216.0 # [deg C]
    
    def decodeBytesFuelGaugeBatteryVoltage(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) / 6415.0 # [V]
    
    def decodeBytesBatteryCurrent(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) * 3.5568 - 61.6 # [mA]
    
    def decodeBytesSolarArrayCurrent(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) * 163.8 / 327.68 # [mA]
    
    def decodeBytesSolarArrayVoltage(self, bytearrayTemp):
        return self.decodeBytes(bytearrayTemp, returnUnsignedInt = 1) * 32.76 / 32768.0 # [V]
    
    ##
    # End byte->human-readable conversion functions
    ##
    
    # Purpose:
    #   Test parsing a packet
    # Input:
    #   minxssPacket [bytearray]: The direct output of the python serial line (connect_serial_decode_kiss.read()), or simulated data in that format
    # Output:
    #   ... not sure yet
    #
    def testParsePacket(self, minxssPacket, log):
        log.info("Testing MinXSS packet parse")
        selectedTelemetryDictionary = self.parse_packet(minxssPacket)
        print(selectedTelemetryDictionary)
        log.info(selectedTelemetryDictionary)

# Purpose:
#   If called directly from Unix, just do a test
#
if __name__ == '__main__':
    # Create a typical telemetry packet as received by the serial line
    exampleData = bytearray([0xc0, 0x00, 0x9a, 0x92, 0x00, 0xb0, 0xa6, 0x64, 0x60, 0x86,
                             0xa2, 0x40, 0x40, 0x40, 0x40, 0xe1, 0x03, 0xf0, 0x08, 0x19,
                             0xc1, 0x6f, 0x00, 0xf7, 0xf1, 0x34, 0xd6, 0x45, 0x47, 0x02,
                             0x0a, 0x86, 0x4b, 0x00, 0x0c, 0x00, 0x01, 0x00, 0x2e, 0x74,
                             0x01, 0x03, 0x30, 0x03, 0x00, 0x03, 0x79, 0x00, 0x00, 0x01,
                             0xfa, 0xc7, 0x10, 0x01, 0x03, 0x00, 0x00, 0x01, 0x5a, 0x80,
                             0x04, 0x01, 0x00, 0x00, 0x00, 0x92, 0x00, 0x00, 0x00, 0x21,
                             0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00,
                             0x00, 0x01, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x5f, 0x00,
                             0x47, 0x13, 0x00, 0x00, 0x0a, 0x80, 0xf6, 0x01, 0xe2, 0x03,
                             0xd3, 0x0b, 0x06, 0x08, 0x90, 0x18, 0x05, 0x04, 0x00, 0x00,
                             0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00,
                             0x00, 0x00, 0x8e, 0x01, 0x13, 0x00, 0x6d, 0x00, 0x00, 0x64,
                             0x88, 0x01, 0x00, 0x00, 0xac, 0x25, 0x01, 0x00, 0x07, 0x0b,
                             0x20, 0x17, 0x40, 0x15, 0x90, 0x15, 0x80, 0x17, 0x40, 0x18,
                             0xe0, 0xce, 0x58, 0x61, 0x08, 0x00, 0x78, 0x07, 0x08, 0x00,
                             0x80, 0x06, 0x08, 0x00, 0x30, 0x06, 0x18, 0x00, 0x50, 0x20,
                             0x30, 0x01, 0x90, 0x0d, 0x18, 0x00, 0x78, 0x13, 0x4d, 0x05,
                             0x44, 0x05, 0x51, 0x05, 0x09, 0x08, 0x14, 0x00, 0x9e, 0x05,
                             0x6c, 0x00, 0xa0, 0x05, 0xf3, 0x01, 0x5c, 0x00, 0x4f, 0x02,
                             0x52, 0x02, 0x53, 0x01, 0x53, 0x01, 0x33, 0x01, 0x00, 0x00,
                             0x08, 0x01, 0x00, 0x00, 0x7e, 0x00, 0x00, 0x00, 0xcd, 0x00,
                             0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                             0x00, 0x00, 0xc7, 0x2f, 0x20, 0x12, 0xd8, 0x00, 0x00, 0x00,
                             0x05, 0x07, 0x02, 0x00, 0x00, 0x00, 0x27, 0x06, 0x00, 0x00,
                             0x09, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfc, 0xff,
                             0xfd, 0xff, 0x07, 0x00, 0x07, 0x49, 0x00, 0x00, 0xe5, 0xf9,
                             0xa5, 0xa5, 0xc0])
