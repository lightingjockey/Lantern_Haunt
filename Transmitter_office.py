#official transmitter code
from micropython import mem_info, alloc_emergency_exception_buf
import gc
import apa102_thread
import dmx512_rx
import config
from machine import Pin
from micropython import const
from gc import collect
import json
from UpyIrTx import UpyIrTx
from UpyIrRx import UpyIrRx
import time
import neopixel

led1_pin = 0
dip1 = 1
dip2 = 2
dip3 = 3
dip4 = 4

IR_TX_PIN = 19
tx = UpyIrTx(0, Pin(IR_TX_PIN, Pin.OUT))

strip1 = neopixel.NeoPixel(Pin(led1_pin), 8)

#ir
# IR packet constants
IR_HEADER = "10101"
IR_ENDER = "01010"

def encode_ir(packet):

    signal = [2400, 1200]

    for bit in packet:

        # Every bit begins with a 400us mark
        signal.append(400)

        # Zero = 400us space
        # One  = 1200us space
        if bit == "0":
            signal.append(400)
        else:
            signal.append(1200)

    # Final mark
    signal.append(400)

    return tuple(signal)

# Current DMX values to transmit
ir_values = (0, 0, 0, 0)


def update_ir(dmx_values):
    global ir_values

    if len(dmx_values) < 4:
        return

    red = dmx_values[0]
    green = dmx_values[1]
    blue = dmx_values[2]
    motor = dmx_values[3]

    ir_values = (red, green, blue, motor)


def byte_to_binary(value):
    value = max(0, min(255, int(value)))
    return format(value, "08b")


def create_ir_packet(red, green, blue, motor):

    packet = (
        IR_HEADER
        + byte_to_binary(red)
        + byte_to_binary(green)
        + byte_to_binary(blue)
        + byte_to_binary(motor)
        + IR_ENDER
    )

    return packet
##
# Device Customisation
dmx_address = 1  # Our device Base DMX Address
dmx_channels = 4   # How many DMX Channels will get passed to the callback function
apa102_numleds = 3    # How Many LEDs for the APA102 Library to Address

dmxrx_deviceaddress = dmx_address  # Our device Base DMX Address
dmxrx_devicechannels = dmx_channels  # How many channels we care about
apa102_numleds = apa102_numleds

# Constants - do not change otherwise DMX might break
DMX_BAUD = 250000  # DMX512 runs at 250,000 baud
DMX_RXTIMEOUT = const(2)  # Milliseconds to wait otherwise discard RX buffer
DMX_TIMEOUT = 30  # Seconds to wait before turning all outputs off after loss of DMX signal



class DMX:

    def set_updatefunction(self, function=None):
        """ Set the function in the main program to call when our data is updated """
        self.callbackupdate = function

    def set_statusfunction(self, function=None):
        """ Set the function in the main program to call when our status changes """
        self.callbackstatus = function

    def _setdmxstatus(self, status, silent=False):
        """ Set the dmx status and run our callback function """
        self.dmx_status = status
        if not silent:
            if self.dmx_status == 2:
                print("INFO: DMX Network Online")
            elif self.dmx_status == 1:
                print("WARNING: DMX Network Offline")
            elif self.dmx_status == 0:
                print(f"\nWARNING: DMX Offline for {DMX_TIMEOUT} seconds")
            else:
                print(f"ERROR: DMX Status is not valid: {self.dmx_status}")
        if self.callbackstatus:
            self.callbackstatus(self.dmx_status)
        # dmxstatus
        # 0 = Timeout (over 60 seconds since we received data)
        # 1 = Offline
        # 2 = Online

    def secondcounter(self, callback=None):
        """ This runs once per second to report/check our DMX512 network status """
        if self.dmx_status == 2 and self.char_counter < 5:
            # No DMX received in the last 1 second, we are now offline.
            self.dmx_offlinetimer = 0
            self._setdmxstatus(1)
        elif self.dmx_status < 2 and self.char_counter > 0:
            # We were offline/timedout, now we have received something, so we are now online
            self._setdmxstatus(2)
        elif self.dmx_status < 2 and self.char_counter == 0:
            # Whilst we are not receiving DMX, increment offline timer.
            self.dmx_offlinetimer += 1
            print(".", end='')  # Whilst DMX is offline still output a '.' to show we are running
        elif self.dmx_status:
            # Every 1 second - print out some basic info to show we are running
            print(
                f"INFO: DMXpps={self.char_counter} Loops={self.loops} Ch={self.dmxrx_list} TotalCh={self.dmx_packet_length}")
        if self.dmx_offlinetimer >= DMX_TIMEOUT:
            # Ensures a safe/default mode is called every DMX_TIMEOUT seconds if offline
            self.dmx_offlinetimer = 0
            self._setdmxstatus(0)
        self.char_counter = 0
        self.loops = 0

    def loop(self):
        """ Monitors DMX RX and calls update functions if valid """
        if self.dmx_rx.any():
            self.dmx_buff += self.dmx_rx.read(514)
            self.dmxrx_timer = time.ticks_ms()
            self.new_packet = True
        if time.ticks_diff(time.ticks_ms(), self.dmxrx_timer) > DMX_RXTIMEOUT:
            self.dmxrx_timer = time.ticks_ms()
            if len(self.dmx_buff) >= self.dmx_endchannel and self.dmx_buff[
                0] == 0 and self.new_packet:  # and self.dmx_buff[1] == 0
                self.char_counter += 1  # Counts valid packets received (per second).
                # self.dmxrx_list = list(self.dmx_buff[self.dmxrx_base-1:self.dmx_endchannel-1])  # Make a new list with just the channels we care about
                self.dmxrx_list = list(self.dmx_buff[
                                           self.dmxrx_base:self.dmx_endchannel])  # Make a new list with just the channels we care about
                if self.callbackupdate:
                    self.callbackupdate(self.dmxrx_list)
                self.new_packet = False
                self.dmx_packet_length = len(self.dmx_buff) - 2
            self.dmx_buff = b''  # using bytearray() is a lot slower!
        if len(self.dmx_buff) > 600:
            # Catch invalid data to make sure the buffer doesn't overflow
            print(f"ERROR: DMX Buff Length overflow: Length={len(self.dmx_buff)}")
            self.dmx_buff = b''  # using bytearray() is a lot slower!
        self.loops += 1
        return self.dmx_status

    def __init__(self, address, channels, rx_pin=1):
        self.dmxrx_base = address + 1
        # self.dmx_channels = channels
        self.dmx_endchannel = self.dmxrx_base + channels
        self.dmxrx_timer = time.ticks_ms()
        self.dmx_buff = bytearray()
        self.char_counter = 0
        self.dmx_offlinetimer = 0
        self.dmx_packet_length = 0
        self.dmxrx_list = []
        self.new_packet = False
        self.callbackupdate = None
        self.callbackstatus = None
        self.loops = 0
        self._setdmxstatus(2, True)  # By Default we are online
        print(f"INFO: Setting up DMX512 Rx on Channels {self.dmxrx_base - 1}-{self.dmx_endchannel - 2} ...  ", end='')
        dmx_rx_pin = machine.Pin(rx_pin)
        self.dmx_rx = machine.UART(0, baudrate=DMX_BAUD, rx=dmx_rx_pin, bits=8, parity=None, stop=2)
        self.timer_1second = machine.Timer(period=1000, mode=machine.Timer.PERIODIC, callback=self.secondcounter)
        print("Done.")

########################################################################################################################
# Get Our Configuration
dmxrx_deviceaddress = dmx_address  # Our device Base DMX Address
dmxrx_devicechannels = dmx_channels  # How many channels we care about
apa102_numleds = apa102_numleds

# Environment Setup
gc.threshold(16384)  # Run Garbage collection everytime 16KB is allocated
alloc_emergency_exception_buf(512)  # Allocate Emergency Exception Buffer

def update_apa102_simple(grgbw_list):
    global_bright = int(grgbw_list[0] / 8)  # Valid 1-31, 0 = disable
    pixels.customwrite(global_bright, grgbw_list[1], grgbw_list[3], grgbw_list[2], 1, 3)

def update_apa102_complex(grgbw_list):
    # First String
    # print(list(grgbw_list))
    global_bright = int(grgbw_list[0] / 8)  # Valid 1-31, 0 = disable
    pixels.customwrite(global_bright, grgbw_list[1], grgbw_list[3], grgbw_list[2], 1, 1)
    # Second String
    if len(grgbw_list) >= 8:
        global_bright = int(grgbw_list[4] / 8)  # Valid 1-31, 0 = disable
        pixels.customwrite(global_bright, grgbw_list[5], grgbw_list[7], grgbw_list[6], 2, 2)
    # Third String
    if len(grgbw_list) >= 12:
        global_bright = int(grgbw_list[8] / 8)  # Valid 1-31, 0 = disable
        pixels.customwrite(global_bright, grgbw_list[9], grgbw_list[11], grgbw_list[10], 3, 3)

def dmxstatuschange(status):
    if status == 0: # We are offline & timed-out
        print("Turning off LED Output")
        pixels.clear()

# Configuring Modules - LED Outputs
pixels = apa102_thread.PIXELS(apa102_numleds, 18, 19)
pixels.test()
# Configuring Modules - DMX Receiver
dmx = dmx512_rx.DMX(dmxrx_deviceaddress, dmxrx_devicechannels, 1)
dmx.set_updatefunction(update_ir)
# dmx.set_statusfunction(dmxstatuschange)  # Not needed with full rainbow fallback

pixels.fullrainbow_init(2)  # Setup fallback Default if no DMX is received
fullrainbow_refresh_ms = time.ticks_ms() + 20  # 50 Rainbow updates/second (1/20ms)
print("INFO: Starting Main Loop")



##############################################################

print("Starting DMX to IR transmitter")

next_transmission = time.ticks_ms()

while True:

    # Read incoming DMX data
    dmx.loop()

    now = time.ticks_ms()

    # Send IR every 100 milliseconds
    if time.ticks_diff(now, next_transmission) >= 0:

        red, green, blue, motor = ir_values

        packet = create_ir_packet(
            red,
            green,
            blue,
            motor
        )

        signal = encode_ir(packet)

        tx.send(signal)

        next_transmission = time.ticks_add(now, 100)

    time.sleep_ms(1)