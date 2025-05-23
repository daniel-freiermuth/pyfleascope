from enum import Enum, auto
from collections.abc import Callable

class BitState(Enum):
    POSITIVE = auto()
    NEGATIVE = auto()
    IGNORE = auto() 

class DigitalTriggerBehavior(Enum):
    AUTO = "~"
    WHILE = ""
    START = "+"
    STOP = "-" 

class AnalogTriggerBehavior(Enum):
    AUTO = "~"
    LEVEL = ""
    RISING = "+"
    FALLING = "-" 

class BitTriggerBuilder:
    bit_states = [
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
        BitState.IGNORE,
    ]

    def set_bit(self, bit: int, state: BitState):
        if bit < 0 or bit > len(self.bit_states):
            raise ValueError(f"Bit must be between 0 and {len(self.bit_states) - 1}")
        self.bit_states[bit] = state
        return self
    
    def set_bit0(self, state: BitState):
        return self.set_bit(0, state)
    def set_bit1(self, state: BitState):
        return self.set_bit(1, state)
    def set_bit2(self, state: BitState):
        return self.set_bit(2, state)
    def set_bit3(self, state: BitState):
        return self.set_bit(3, state)
    def set_bit4(self, state: BitState):
        return self.set_bit(4, state)
    def set_bit5(self, state: BitState):
        return self.set_bit(5, state)
    def set_bit6(self, state: BitState):
        return self.set_bit(6, state)
    def set_bit7(self, state: BitState):
        return self.set_bit(7, state)

    def while_matching(self):
        return BitTrigger(self.bit_states, DigitalTriggerBehavior.WHILE)

    def when_start_matching(self):
        return BitTrigger(self.bit_states, DigitalTriggerBehavior.START)

    def when_stop_matching(self):
        return BitTrigger(self.bit_states, DigitalTriggerBehavior.STOP)
    
    def auto(self):
        return BitTrigger(self.bit_states, DigitalTriggerBehavior.AUTO)
    
class BitTrigger:
    def __init__(self, bit_states: list[BitState], behavior: DigitalTriggerBehavior):
        self.bit_states = bit_states
        self.behavior = behavior
    
    def into_trigger_fields(self):
        relevant_bits = 0
        for i, state in enumerate(self.bit_states):
            if state != BitState.IGNORE:
                relevant_bits |= (1 << i)
        active_bits = 0
        for i, state in enumerate(self.bit_states):
            if state == BitState.POSITIVE:
                active_bits |= (1 << i)
        trigger_behavior_flag = self.behavior.value

        return f"{trigger_behavior_flag}0x{active_bits:02x} 0x{relevant_bits:02x}"

class AnalogTriggerBuilder:
    def __init__(self, level: float):
        self._level = level

    def rising_edge(self):
        return AnalogTrigger(self._level, AnalogTriggerBehavior.RISING)
    def falling_edge(self):
        return AnalogTrigger(self._level, AnalogTriggerBehavior.FALLING)
    def level(self):
        return AnalogTrigger(self._level, AnalogTriggerBehavior.LEVEL)
    def auto(self):
        return AnalogTrigger(self._level, AnalogTriggerBehavior.AUTO)

class AnalogTrigger:
    def __init__(self, level: float, behavior: AnalogTriggerBehavior):
        self.level = level
        self.behavior = behavior
    
    def into_trigger_fields(self, voltage_to_raw: Callable[[float], float]):
        trigger_behavior_flag = self.behavior.value
        raw_level = int(voltage_to_raw(self.level)/4 + 0.5)
        return f"{trigger_behavior_flag}{raw_level} 0"