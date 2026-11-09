'''this is the main code that will be utilized for the Raspberry Pico
Important imort files include the neopix repo, IR repo, GPIO repo'''

# ============================================================
# HCDM-1 RECEIVER
# Raspberry Pi Pico / RP2040 / MicroPython
# ============================================================

from machine import Pin
import time
import neopixel
import micropython
from array import array

micropython.alloc_emergency_exception_buf(100)

# ---------------- CONFIGURATION ----------------

LED_PINS = (0, 1, 2, 3)

# CHANGE THESE TO YOUR ACTUAL LED COUNTS

LED_COUNTS = (8, 8, 8, 8)

IR_INPUT_PINS = (4, 5, 6, 7)

MOTOR_GPIO = 8
MODE_GPIO = 9
STATUS_GPIO = 10

SIGNAL_TIMEOUT_MS = 15000

MOTOR_ON_THRESHOLD = 128
MOTOR_ACTIVE_HIGH = True
MOTOR_TEST_MS = 200

GROUP_GAP_THRESHOLD_US = 5000
MIN_EDGE_INTERVAL_US = 1200

RING_SIZE = 256
RING_MASK = RING_SIZE - 1

DEFAULT_BLUE = (0, 0, 255)

# ---------------- HARDWARE SETUP ----------------

strips = [
    neopixel.NeoPixel(
        Pin(pin, Pin.OUT),
        LED_COUNTS[i]
    )
    for i, pin in enumerate(LED_PINS)
]

motor_pin = Pin(
    MOTOR_GPIO,
    Pin.OUT,
    value=0
)

mode_pin = Pin(
    MODE_GPIO,
    Pin.IN,
    Pin.PULL_UP
)

status_led = Pin(
    STATUS_GPIO,
    Pin.OUT,
    value=0
)

ir_pins = [
    Pin(pin, Pin.IN, Pin.PULL_UP)
    for pin in IR_INPUT_PINS
]

# ---------------- IR EDGE BUFFERS ----------------

edge_buffers = [
    array('I', [0] * RING_SIZE)
    for _ in range(4)
]

write_index = [0, 0, 0, 0]
read_index = [0, 0, 0, 0]

ring_overflows = [0, 0, 0, 0]


def make_edge_irq(channel):

    def _edge_irq(pin):

        nxt = (
            write_index[channel] + 1
        ) & RING_MASK

        if nxt != read_index[channel]:

            edge_buffers[channel][
                write_index[channel]
            ] = time.ticks_us()

            write_index[channel] = nxt

        else:

            ring_overflows[channel] += 1

    return _edge_irq


# ---------------- LED COLOR FUNCTIONS ----------------

def wheel(position):

    position &= 255

    if position < 85:

        return (
            255 - position * 3,
            position * 3,
            0
        )

    if position < 170:

        position -= 85

        return (
            0,
            255 - position * 3,
            position * 3
        )

    position -= 170

    return (
        position * 3,
        0,
        255 - position * 3
    )


def fill_strip(strip, color):

    for i in range(len(strip)):

        strip[i] = color

    strip.write()


def set_physical_group(group, color):

    fill_strip(strips[group], color)


def all_groups(color):

    for group in range(4):

        set_physical_group(group, color)


# ---------------- MODE A / MODE B ----------------

def apply_logical_colors(colors):

    # Mode A: Normal order
    # Mode B: Reverse order

    mode_b = (
        mode_pin.value() == 0
    )

    for physical_group in range(4):

        if mode_b:

            source_group = 3 - physical_group

        else:

            source_group = physical_group

        set_physical_group(
            physical_group,
            colors[source_group]
        )


# ---------------- STARTUP RAINBOW ----------------

def startup_rainbow():

    for step in range(64):

        for group, strip in enumerate(strips):

            count = len(strip)

            for pixel in range(count):

                pos = (
                    pixel * 256 // max(1, count)
                    + step * 4
                    + group * 16
                ) & 255

                strip[pixel] = wheel(pos)

            strip.write()

        time.sleep_ms(12)


# ---------------- STARTUP COLOR CHASE ----------------

def startup_color_chase():

    chase_colors = (
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 255)
    )

    for color in chase_colors:

        for active_group in range(4):

            all_groups((0, 0, 0))

            set_physical_group(
                active_group,
                color
            )

            time.sleep_ms(110)

    all_groups((0, 0, 0))


# ---------------- MOTOR TEST ----------------

def motor_test():

    motor_pin.value(
        1 if MOTOR_ACTIVE_HIGH else 0
    )

    time.sleep_ms(MOTOR_TEST_MS)

    motor_pin.value(
        0 if MOTOR_ACTIVE_HIGH else 1
    )


# ---------------- CRC16 ----------------

def crc16_ccitt(data):

    crc = 0xFFFF

    for byte in data:

        crc ^= (byte << 8)

        for _ in range(8):

            if crc & 0x8000:

                crc = (
                    (crc << 1) ^ 0x1021
                ) & 0xFFFF

            else:

                crc = (crc << 1) & 0xFFFF

    return crc


# ---------------- PACKET DECODER ----------------

def symbols_to_packet(symbols):

    if len(symbols) != 64:

        return None

    packet = bytearray(16)

    out_index = 0

    for i in range(0, 64, 4):

        value = (
            ((symbols[i] & 3) << 6)
            | ((symbols[i + 1] & 3) << 4)
            | ((symbols[i + 2] & 3) << 2)
            | (symbols[i + 3] & 3)
        )

        packet[out_index] = value

        out_index += 1

    expected = (
        (packet[14] << 8)
        | packet[15]
    )

    actual = crc16_ccitt(
        packet[0:14]
    )

    if expected != actual:

        return None

    return (
        packet[0:12],
        packet[12],
        packet[13]
    )


# ---------------- IR BURST DECODER ----------------

class BurstDecoder:

    def __init__(self):

        self.last_edge = None

        self.group_count = 0

        self.synced = False

        self.symbols = []


    def reset(self):

        self.last_edge = None

        self.group_count = 0

        self.synced = False

        self.symbols = []


    def finish_group(self):

        count = self.group_count

        self.group_count = 0

        # Eight pulses = packet synchronization

        if count == 8:

            self.symbols = []

            self.synced = True

            return None

        if not self.synced:

            return None

        # Data symbols contain 1-4 pulses

        if 1 <= count <= 4:

            self.symbols.append(
                count - 1
            )

            if len(self.symbols) == 64:

                result = symbols_to_packet(
                    self.symbols
                )

                self.symbols = []

                self.synced = False

                return result

        else:

            self.symbols = []

            self.synced = False

        return None


    def feed_edge(self, timestamp):

        result = None

        if self.last_edge is None:

            self.group_count = 1

            self.last_edge = timestamp

            return None

        delta = time.ticks_diff(
            timestamp,
            self.last_edge
        )

        # Reject excessively close edges

        if delta < MIN_EDGE_INTERVAL_US:

            return None

        self.last_edge = timestamp

        if delta > GROUP_GAP_THRESHOLD_US:

            result = self.finish_group()

            self.group_count = 1

        else:

            self.group_count += 1

        return result


# ---------------- DECODER INSTANCES ----------------

decoders = [
    BurstDecoder()
    for _ in range(4)
]

last_sequence = None

last_valid_ms = 0

fallback_active = False

last_logical_colors = [
    (0, 0, 0),
    (0, 0, 0),
    (0, 0, 0),
    (0, 0, 0)
]

last_mode_value = mode_pin.value()


# ---------------- ACCEPT VALID PACKET ----------------

def accept_packet(packet):

    global last_sequence
    global last_valid_ms
    global fallback_active
    global last_logical_colors

    if packet is None:

        return

    rgb_data, motor_value, sequence = packet

    now = time.ticks_ms()

    # Ignore duplicate broadcasts from other receivers

    if (
        last_sequence == sequence
        and time.ticks_diff(
            now,
            last_valid_ms
        ) < 5000
    ):

        return

    last_sequence = sequence

    last_valid_ms = now

    fallback_active = False

    colors = []

    for i in range(0, 12, 3):

        colors.append(
            (
                rgb_data[i],
                rgb_data[i + 1],
                rgb_data[i + 2]
            )
        )

    last_logical_colors = colors

    apply_logical_colors(colors)

    motor_on = (
        motor_value >= MOTOR_ON_THRESHOLD
    )

    motor_pin.value(
        1 if motor_on == MOTOR_ACTIVE_HIGH else 0
    )


# ---------------- PROCESS RECEIVER INPUTS ----------------

def drain_receiver_edges():

    for channel in range(4):

        buf = edge_buffers[channel]

        while (
            read_index[channel]
            != write_index[channel]
        ):

            timestamp = buf[
                read_index[channel]
            ]

            read_index[channel] = (
                read_index[channel] + 1
            ) & RING_MASK

            packet = decoders[channel].feed_edge(
                timestamp
            )

            if packet is not None:

                accept_packet(packet)


# ---------------- STARTUP ----------------

print("HCDM-1 RECEIVER STARTING")

print("LED COUNTS:", LED_COUNTS)

motor_pin.value(
    0 if MOTOR_ACTIVE_HIGH else 1
)

startup_rainbow()

startup_color_chase()

motor_test()

all_groups((0, 0, 0))

motor_pin.value(
    0 if MOTOR_ACTIVE_HIGH else 1
)

# ---------------- ENABLE IR INTERRUPTS ----------------

for ch in range(4):

    read_index[ch] = write_index[ch]

    decoders[ch].reset()

    ir_pins[ch].irq(
        handler=make_edge_irq(ch),
        trigger=Pin.IRQ_FALLING
    )


# ---------------- MAIN LOOP ----------------

last_valid_ms = time.ticks_ms()

last_mode_value = mode_pin.value()

last_status_toggle = time.ticks_ms()


while True:

    drain_receiver_edges()

    now = time.ticks_ms()

    # -------- MODE SWITCH --------

    current_mode = mode_pin.value()

    if current_mode != last_mode_value:

        last_mode_value = current_mode

        apply_logical_colors(
            last_logical_colors
        )

    # -------- SIGNAL LOSS --------

    if (
        not fallback_active
        and time.ticks_diff(
            now,
            last_valid_ms
        ) >= SIGNAL_TIMEOUT_MS
    ):

        fallback_active = True

        last_logical_colors = [
            DEFAULT_BLUE,
            DEFAULT_BLUE,
            DEFAULT_BLUE,
            DEFAULT_BLUE
        ]

        apply_logical_colors(
            last_logical_colors
        )

        motor_pin.value(
            0 if MOTOR_ACTIVE_HIGH else 1
        )

        print(
            "IR TIMEOUT: BLUE LIGHTS, MOTOR OFF"
        )

    # -------- STATUS LED --------

    if time.ticks_diff(
        now,
        last_status_toggle
    ) >= 500:

        status_led.toggle()

        last_status_toggle = now

    time.sleep_ms(1)
