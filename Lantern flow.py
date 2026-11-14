'''No imports, just floating variables and sudo inputs that will be used to check the flow of the code.'''
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

timeout = 150000
'''led_pins = [led1_pin,led2_pin,led3_pin,led4_pin]
IR_INPUT_PINS = [IR1,IR2,IR3,IR4]
strips = [
    neopixel.NeoPixel(
        Pin(pin, Pin.OUT),
        led_ct[i]
    )
    for i, pin in enumerate(led_pins)
]
motor_pin = Pin(
    motor,
    Pin.OUT,
    value=0
)

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
]'''
def decode(data):
    data = data.split()
    for i in data:
        if i == 0:
            red = data[i]
        if i == 1:
            green = data[i]
        if i == 2:
            blue = data[i]
        if i == 3:
            motor = data[i]
        if i == 4:
            effect = data[i]

    color(red,green,blue)
    shake(motor)

def color(red,green,blue):
    pass
    ''''''

def status_blink():
    pass
def effect_ws2812():
    pass

def startup():
    pass
def ir_receive():
    pass

def translate():
    pass

def shake():
    pass

def dark():
    pass

def Sig_loss():
    led_color = [0,0,255]
    return led_color

while True:

    data_input = input(">")
    if len(data_input) < 20:
        Sig_loss()

    elif len(data_input) > 20:
    decode(data_input)


