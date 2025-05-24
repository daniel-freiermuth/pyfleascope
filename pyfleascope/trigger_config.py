from enum import Enum, auto
from collections.abc import Callable

class BitState(Enum):
    HIGH = auto()
    LOW = auto()
    DONT_CARE = auto() 

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
    _bit_states = [
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
        BitState.DONT_CARE,
    ]

    def _set_bit(self, bit: int, state: BitState):
        if bit < 0 or bit > len(self._bit_states):
            raise ValueError(f"Bit must be between 0 and {len(self._bit_states) - 1}")
        self._bit_states[bit] = state
        return self
    
    def bit0(self, state: BitState):
        return self._set_bit(0, state)
    def bit1(self, state: BitState):
        return self._set_bit(1, state)
    def bit2(self, state: BitState):
        return self._set_bit(2, state)
    def bit3(self, state: BitState):
        return self._set_bit(3, state)
    def bit4(self, state: BitState):
        return self._set_bit(4, state)
    def bit5(self, state: BitState):
        return self._set_bit(5, state)
    def bit6(self, state: BitState):
        return self._set_bit(6, state)
    def bit7(self, state: BitState):
        return self._set_bit(7, state)
    def bit8(self, state: BitState):
        return self._set_bit(8, state)

    def is_matching(self):
        return DigitalTrigger(self._bit_states, DigitalTriggerBehavior.WHILE)

    def starts_matching(self):
        return DigitalTrigger(self._bit_states, DigitalTriggerBehavior.START)

    def stops_matching(self):
        return DigitalTrigger(self._bit_states, DigitalTriggerBehavior.STOP)
    
    def auto(self):
        """Same as is_matching, but will also trigger when the bits did not match within 100ms."""
        return DigitalTrigger(self._bit_states, DigitalTriggerBehavior.AUTO)
    
class DigitalTrigger:
    def __init__(self, bit_states: list[BitState], behavior: DigitalTriggerBehavior):
        self.bit_states = bit_states
        self.behavior = behavior
    
    @staticmethod
    def start_capturing_when():
        return BitTriggerBuilder()
    
    def into_trigger_fields(self):
        relevant_bits = 0
        for i, state in enumerate(self.bit_states):
            if state != BitState.DONT_CARE:
                relevant_bits |= (1 << i)
        active_bits = 0
        for i, state in enumerate(self.bit_states):
            if state == BitState.HIGH:
                active_bits |= (1 << i)
        trigger_behavior_flag = self.behavior.value

        return f"{trigger_behavior_flag}0x{active_bits:02x} 0x{relevant_bits:02x}"

class AnalogTriggerBuilder:
    def rising_edge(self, volts: float):
        return AnalogTrigger(volts, AnalogTriggerBehavior.RISING)
    def falling_edge(self, volts: float):
        return AnalogTrigger(volts, AnalogTriggerBehavior.FALLING)
    def level(self, volts: float):
        return AnalogTrigger(volts, AnalogTriggerBehavior.LEVEL)
    def auto(self, volts: float):
        """Same as level, but will also trigger when the voltage did not match within 100ms."""
        return AnalogTrigger(volts, AnalogTriggerBehavior.AUTO)

class AnalogTrigger:
    def __init__(self, level: float, behavior: AnalogTriggerBehavior):
        self.level = level
        self.behavior = behavior

    @staticmethod
    def start_capturing_when():
        return AnalogTriggerBuilder()
    
    def into_trigger_fields(self, voltage_to_raw: Callable[[float], float]):
        trigger_behavior_flag = self.behavior.value
        raw_level = int(voltage_to_raw(self.level)/4 + 0.5)
        return f"{trigger_behavior_flag}{raw_level} 0"