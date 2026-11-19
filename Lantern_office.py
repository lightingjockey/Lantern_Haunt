'''this is the main code that will be utilized for the Raspberry Pico
Important imort files include the neopix repo, IR repo, GPIO repo'''

from machine import Pin
from micropython import const
from gc import collect
import json
from UpyIrTx import UpyIrTx
from UpyIrRx import UpyIrRx
import time
import neopixel

from time import sleep
number = 0

led_ct = [8, 8, 8, 8]
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

timeout = 1500

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
strip1 = neopixel.NeoPixel(Pin(led1_pin), 8)
strip2 = neopixel.NeoPixel(Pin(led2_pin), 8)
strip3 = neopixel.NeoPixel(Pin(led3_pin), 8)
strip4 = neopixel.NeoPixel(Pin(led4_pin), 8)

pixels = [strip1, strip2, strip3, strip4]

motor_pin = Pin(motor,Pin.OUT,value=0)

status = Pin(
    status_dip,
    Pin.IN,
    Pin.PULL_UP
)

statusled = neopixel.NeoPixel(Pin(status_led), 1)
pixel = [statusled]

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



def value(binary):
    return int(binary, 2)


def decode_packet(binary):

    if len(binary) != 42:
        print("Incorrect packet length")
        return None

    if binary[0:5] != HEADER:
        print("Invalid header")
        return None

    if binary[37:42] != ENDER:
        print("Invalid ender")
        return None

    red = int(binary[5:13], 2)
    green = int(binary[13:21], 2)
    blue = int(binary[21:29], 2)
    motor_value = int(binary[29:37], 2)

    return red, green, blue, motor_value

def color(red, green, blue):

    for strip in pixels:
        strip.fill((red,green,blue))
        strip.show


def status_blink(number):

    if number < 200:
        for strip in pixel:
            strip.fill((0,0,255))
            strip.write


    if number > 200:
        for strip in pixel:
            strip.fill((0,0,0))
            strip.write
        if number == 300:
            number = 0
    return number


def startup():
    for strip in pixels:
        strip.fill((255, 0, 0))
        strip.write()

    time.sleep(1)

    for strip in pixels:
        strip.fill((0, 255, 0))
        strip.write()

    time.sleep(1)

    for strip in pixels:
        strip.fill((0, 0, 255))
        strip.write()

    time.sleep(1)





def rainbow_cycle(wait):
    for j in range(255):
        for i in range(num_pixels):
            pixel_index = (i * 256 // num_pixels) + j
            pixels[i] = wheel(pixel_index & 255)
        pixels.show()
        time.sleep(wait)




def ir_receive():
    pass


def translate():
    pass


def shake(motor):
    if motor_value == 0:
        motor_pin.value(0)

    else:
        motor_pin.value(1)



def dark():
    for strip in pixels:
        strip.fill((0, 0, 0))
        strip.write()

def Sig_loss():
    led_color = [0, 0, 255]
    return led_color
print("wait")
time.sleep(10)
print("go")

missing = 0
startup()
dark()
while True:
    status_blink(number)
    result = rx.record(250, 15)

    if result == UpyIrRx.ERROR_NONE:

        signal = rx.get_calibrate_list()

        print("Received pulse count:", len(signal))
        print("Received pulses:", signal)

        binary = decode_ir(signal)

        if binary is None:
            print("Invalid IR waveform")
            continue

        print("Binary packet:", binary)

        values = decode_packet(binary)

        if values is None:
            print("Invalid packet")
            continue

        if values != previous_values:

            red, green, blue, motor_value = values

            print("Packet received!")
            print("Red:", red)
            print("Green:", green)
            print("Blue:", blue)
            print("Motor:", motor_value)

            color(red, green, blue)
            shake(motor_value)

            previous_values = values

    elif result == UpyIrRx.ERROR_NO_DATA:
        pass

    else:
        print("IR reception error:", result)
        missing = missing + 1
        print(missing)

    if missing == timeout:
        for strip in pixels:
            strip.fill((255, 0, 0))
            strip.write()
        input(">")
        for strip in pixels:
            strip.fill((0, 255, 0))
            strip.write()
        time.sleep(5)
        dark()
        missing = 0
    number = number +1
    time.sleep(0.05)