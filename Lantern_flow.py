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

    data_input = "00000111111110000000011111111000000001111111100000"
    if data_input[0:5] == "00000":
        if data_input[len(data_input)-5:len(data_input) ] == "00000":
            if len(data_input) == 50:
                print("good code")
                decode(data_input)
            else:
                print("bad code")
        else:
            Sig_loss()
            print("last five")
    else:
        Sig_loss()
        print("first 5")







