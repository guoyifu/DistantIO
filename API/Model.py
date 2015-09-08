# Copyright (C) 2014 Rémi Bèges
# For conditions of distribution and use, see copyright notice in the LICENSE file

from .SerialPort import SerialPort
from .distantio_protocol import distantio_protocol
from .Protocol import Protocol
from signalslot import Signal
from threading import *

class Model():
    def __init__(self):
        # Signals
        self.signal_connected = Signal(args=['port'])
        self.signal_disconnected = Signal()
        self.signal_connecting = Signal()
        self.signal_MCU_state_changed = Signal(args=['alive'])
        self.signal_received_descriptor = Signal(args=['var_id','var_type','var_name'])
        self.signal_received_value = Signal(args=['var_id','var_type','value'])

        self.serial = SerialPort(self.on_rx_data_callback,self.on_connection_attempt_callback)
        self.protocol = Protocol(self.on_frame_decoded_callback)
        self.distantio = distantio_protocol(self.on_tx_frame_callback)

        self.mcu_died_delay = 2.0
        self.mcu_alive_timer = Timer(self.mcu_died_delay,self.on_mcu_lost_connection)


    def connect(self,port,baudrate=115200):
        self.signal_connecting.emit()
        self.serial.connect(port,baudrate)

        self.mcu_alive_timer.start()

    def disconnect(self):
        self.serial.disconnect()
        self.signal_MCU_state_changed.emit(alive=False)
        self.mcu_alive_timer.cancel()
        if self.mcu_alive_timer.isAlive():
            self.mcu_alive_timer.join()

    def finish(self):
        self.disconnect()
        self.serial.stop()
        self.serial.join()

    def get_ports(self):
        return self.serial.get_ports()

    ### Distant IO calls to MCU
    # Ask the MCU to return all descriptors
    def request_descriptors(self):
        frame = self.distantio.get_descriptors_frame()
        frame = self.protocol.encode(frame)
        self.serial.write(frame)

    # Ask the MCU to write a variable
    def request_write(self, variable_id, data):
        frame = self.distantio.write(variable_id,data)
        frame = self.protocol.encode(frame)
        self.serial.write(frame)

    def request_read(self):
        pass

    ## Callbacks
        # RX : serial to protocol
    def on_rx_data_callback(self,c):
        self.protocol.decode(c)

        # RX : protocol to distantio
    def on_frame_decoded_callback(self,frame):
        try:
            instruction = self.distantio.process(frame)
        except IndexError as e:
            print(str(e))
            print("Continuing happily.")
            return
        except ValueError as e:
            print(str(e))
            print("Continuing happily.")
            return
        except:
            print("Unkown exception in Model.on_frame_decoded_callback.")
            return

        # If distantio received a alive signal
        if instruction['type'] == "alive-signal":
            # Restart the timer
            self.mcu_alive_timer.cancel()
            self.mcu_alive_timer.join()

            self.mcu_alive_timer = Timer(self.mcu_died_delay,self.on_mcu_lost_connection)

            self.mcu_alive_timer.start()
            self.signal_MCU_state_changed.emit(alive=True)

        # if returned-value
        elif instruction['type'] == 'returned-value':
            self.signal_received_value.emit(var_id=instruction['var-id'],
                                            var_type=instruction['var-type'],
                                            value=instruction['var-value'])
        # if returned-descriptor
        elif instruction['type'] == 'returned-descriptor':
            self.signal_received_descriptor.emit(var_id=instruction['var-id'],
                                                 var_type=instruction['var-type'],
                                                 var_name=instruction['var-name'])


    def on_mcu_lost_connection(self):
        self.signal_MCU_state_changed.emit(alive=False)

        # TX : distantio to serial
    def on_tx_frame_callback(self,frame):
        frame = self.protocol.encode(frame)
        self.serial.write(frame)

    def on_connection_attempt_callback(self,message):
        if message in ["NO-PORT-FOUND","UNKNOWN-CONNECTION-ISSUE","CONNECTION-ISSUE","OTHER-PORTS-FOUND","DISCONNECTED"]:
           self.signal_disconnected.emit()
        else:
           self.signal_connected.emit(port=message)
