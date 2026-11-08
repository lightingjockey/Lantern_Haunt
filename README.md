# Lantern_Haunt
This is the code repository for the lanterns for use at eulogy collective


Hello, if you are reading this, you are either searching for it or sent this repository.
In either case you are here and are reading this. 

The primary infor for how the hell this thing works is the lanters are going to contain one shaker motor, 4 sets of WS2812b neo pixel tape
and 4 IR sensors all trying to take in info for the lantern to display. 

The Transmitter side will be a dip switch device reading DMX. Additionally, we can have some standard dmx fail settings that are hard coded. 

Build for that is a singular WS2812b neo pixel bulb, one DMX in out device, and one IR transmitter/ Flasher.

The computers for each device a is a RP pico using micropython. For further details, see wiring diagram in later files. 
