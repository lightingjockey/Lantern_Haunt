'''No imports, just floating variables and sudo inputs that will be used to check the flow of the code.
from machine import Pin
from micropython import const
from gc import collect
import json
from UpyIrTx import UpyIrTx
from UpyIrRx import UpyIrRx'''
import time

from time import sleep





led_ct = [8,8,8,8]
led1_pin = 0
led2_pin = 1
led3_pin = 2
led4_pin = 3
status_led = 4
status_dip = 5
motor = 6
IR1 = 7

HEADER = "10101"
ENDER = "01010"
previous_values = None

timeout = 150000
'''
#ir setup
# RP2040 RX=Pin18, TX=Pin19
_GROVE_PIN = {'ATOM':  (32, 26),
              'CORE2': (33, 32),
              'BASIC': (22, 21),
              'GRAY':  (22, 21),
              'FIRE':  (22, 21),
              'GO':    (22, 21),
              'Stick': (33, 32),
              'Else':  (26, 19)}
_DEVICE = 'Else'

_RX_IDLE_LEVEL = const(1)
_RX_SIZE = const(1023)

rx_pin = Pin(_GROVE_PIN[_DEVICE][0], Pin.IN)
rx = UpyIrRx(rx_pin, 100, _RX_IDLE_LEVEL)

tx_pin = Pin(_GROVE_PIN[_DEVICE][1], Pin.OUT)
tx = UpyIrTx(0, tx_pin, _TX_FREQ, _TX_DUTY, _TX_IDLE_LEVEL)

#decode code v
def decode_ir(signal):

    # 2 leader pulses + 84 data pulses + 1 ending pulse
    if len(signal) != 87:
        return None

    # Validate leader
    if not (1800 <= signal[0] <= 3000):
        return None

    if not (800 <= signal[1] <= 1600):
        return None

    binary = ""

    for i in range(42):

        mark = signal[2 + (i * 2)]
        space = signal[3 + (i * 2)]

        # Validate mark duration
        if not (200 <= mark <= 700):
            return None

        # Decode space duration
        if 200 <= space <= 700:
            binary += "0"

        elif 800 <= space <= 1500:
            binary += "1"

        else:
            return None

    return binary


#pixel setup
IR_INPUT_PINS = [IR1]
strip1 = neopixel.NeoPixel(
    led1_pin, led_ct[0], brightness=1, auto_write=False, pixel_order=ORDER)
strip2 = neopixel.NeoPixel(
    led2_pin, led_ct[0], brightness=1, auto_write=False, pixel_order=ORDER)
strip3 = neopixel.NeoPixel(
    led3_pin, led_ct[0], brightness=1, auto_write=False, pixel_order=ORDER)
strip4 = neopixel.NeoPixel(
    led4_pin, led_ct[0], brightness=1, auto_write=False, pixel_order=ORDER)
pixel = neopixel.NeoPixel(
    status_led, 1, brightness=1, auto_write=False, pixel_order=ORDER)
    
pixels = [strip1,strip2,strip3,strip4]
motor_pin = Pin(motor,Pin.OUT,value=0)

status = Pin(
    status_dip,
    Pin.IN,
    Pin.PULL_UP
)

statusled = Pin(
    status_led,
    Pin.OUT,
    value=0
)

ir_pins = [
    Pin(pin, Pin.IN, Pin.PULL_UP)
    for pin in IR_INPUT_PINS
]
def wheel(pos):
    # Input a value 0 to 255 to get a color value.
    # The colours are a transition r - g - b - back to r.
    if pos < 0 or pos > 255:
        r = g = b = 0
    elif pos < 85:
        r = int(pos * 3)
        g = int(255 - pos * 3)
        b = 0
    elif pos < 170:
        pos -= 85
        r = int(255 - pos * 3)
        g = 0
        b = int(pos * 3)
    else:
        pos -= 170
        r = 0
        g = int(pos * 3)
        b = int(255 - pos * 3)
    return (r, g, b) if ORDER in {neopixel.RGB, neopixel.GRB} else (r, g, b, 0)
pixels = [strip1, strip2, strip3, strip4]
'''
def value(binary):
    return int(binary, 2)

def decode(data):
    data = str(data[5:len(data)-5])
    print(data)
    channel = 0
    while channel < 5:
        print(f"ch:{channel}")

        variable = value(data[0:8])
        if channel == 0:
            print(data[0:8])

            input(">")
            print(variable)
            red = variable
            print(f"red:{red}")
            input(">")

        if channel == 1:
            print(data[0:8])
            green = variable
            print(f"green:{green}")
            input(">")

        if channel == 2:
            print(data[0:8])
            blue = variable
            print(f"blue:{blue}")
            input(">")
        if channel == 3:
            print(data[0:8])
            motor = variable
            print(f"motor:{motor}")
            input(">")

        data = data[8:len(data)]
        channel = channel + 1
    if channel == 5:
        color(red,green,blue)
        shake(motor)

def color(red,green,blue):

    print(red, green, blue)
    '''
    for i in pixels:
        i.fill((red,green,blue))
        i.show'''


def status_blink():
    pass
'''
if number == 1
    pixel.fill((0,0,255))
    pixel.show()
    number = 0'''


def startup():
    pass
'''
    pixels.fill((255, 0, 0))
    # Uncomment this line if you have RGBW/GRBW NeoPixels
    # pixels.fill((255, 0, 0, 0))
    pixels.show()
    time.sleep(1)

    # Comment this line out if you have RGBW/GRBW NeoPixels
    pixels.fill((0, 255, 0))
    # Uncomment this line if you have RGBW/GRBW NeoPixels
    # pixels.fill((0, 255, 0, 0))
    pixels.show()
    time.sleep(1)

    # Comment this line out if you have RGBW/GRBW NeoPixels
    pixels.fill((0, 0, 255))
    # Uncomment this line if you have RGBW/GRBW NeoPixels
    # pixels.fill((0, 0, 255, 0))
    pixels.show()
    time.sleep(1)

    rainbow_cycle(0.001)  # rainbow cycle with 1ms delay per step'''
'''


def rainbow_cycle(wait):
    for j in range(255):
        for i in range(num_pixels):
            pixel_index = (i * 256 // num_pixels) + j
            pixels[i] = wheel(pixel_index & 255)
        pixels.show()
        time.sleep(wait)

'''
def ir_receive():
    pass

def translate():
    pass

def shake(motor):
    if motor == 0:
        print("still")

    if motor == 1:
        print("shake")
def dark():
    pass

def Sig_loss():
    led_color = [0,0,255]
    return led_color

while True:

    ''' 
    
    # Wait for a packet.
    # 15 ms quiet time separates consecutive packets.
    result = rx.record(250, 15)

    if result == UpyIrRx.ERROR_NONE:

        signal = rx.get_calibrate_list()

        binary = decode_ir(signal)

        if binary is not None:

            values = decode_packet(binary)
            
            if values is not None:

                if values != previous_values:

                    red, green, blue, motor = values

                    print("Packet received!")
                    print("Red:", red)
                    print("Green:", green)
                    print("Blue:", blue)
                    print("Motor:", motor)

                    # Connect your existing functions here:
                    # color(red, green, blue)
                    # shake(motor)

                    previous_values = values

        else:
            print("Invalid IR signal")

    elif result != UpyIrRx.ERROR_NO_DATA:
        print("IR reception error:", result)
            
    '''


    data_input = "00000111111110000000011111111000000001111111100000"
    if data_input[0:5] == "00000":
        if data_input[len(data_input)-5:len(data_input) ] == "00000":
            if len(data_input) == 50:
                print("good code")
                decode(data_input)
            else:
                print("bad code")
        else:
            '''pixel.fill(Sig_loss())
            pixel.show()'''
            print("last five")
    else:
        '''pixel.fill(Sig_loss())
        pixel.show()'''
        print("first 5")







