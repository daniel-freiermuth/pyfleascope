from datetime import timedelta
from enum import Enum
import functools
import logging
import pandas as pd
import io
from pyfleascope.serial_terminal import SerialTerminal
from pyfleascope.trigger_config import AnalogTrigger, AnalogTriggerBehavior, DigitalTrigger

logging.basicConfig(level=logging.INFO)

class Waveform(Enum):
    SINE= "sine"
    SQUARE= "square"
    TRIANGLE= "triangle"
    EKG = "ekg"

class FleaScope():
    _MSPS = 18  # Million samples per second. approximate target sample rate = 3.6*5. Up to 3.75*5 possible

    def __init__(self, port: str, baud: int=9600, read_calibrations: bool=True):
        self.serial = SerialTerminal(port, baud, prompt="> ")
        self.serial.send_ctrl_c()
        self.serial.exec("prompt on")
        self.serial.exec("echo off")

        # TODO check for usb vendor ids
        # { usbVendorId: 0x0403, usbProductId: 0xA660 },
        # { usbVendorId: 0x1b4f, usbProductId: 0xA660 },
        # { usbVendorId: 0x1b4f, usbProductId: 0xE66E },
        # { usbVendorId: 0x04D8, usbProductId: 0xE66E },

        # TODO try to gear up to 115200 baud

        # TODO add resetting logic when device is not responding

        self.ver = self.serial.exec("ver")
        logging.debug(f"FleaScope version: {self.ver}")
        # TODO check if version is compatible

        self.hostname = self.serial.exec("hostname")
        logging.debug(f"FleaScope hostname: {self.hostname}")
        self.probe1 = FleaProbe(self, 1)
        self.probe10 = FleaProbe(self, 10)

        if read_calibrations:
            self.probe1.read_calibration_from_flash()
            self.probe10.read_calibration_from_flash()
    
    def set_waveform(self, waveform: Waveform, hz: int):
        self.serial.exec(f"wave {waveform.value} {hz}")
        
    def _timedelta_to_ticks(self, time_frame: timedelta):
        return time_frame.microseconds * self._MSPS + time_frame.seconds * 1_000_000 * self._MSPS

    def raw_read(self, time_frame: timedelta, trigger_fields: str, delay: timedelta = timedelta(milliseconds=0)):
        if time_frame.total_seconds() < 0:
            raise ValueError("Time frame cannot be negative.")
        if time_frame.total_seconds() > 2:
            raise ValueError("Time frame too large. Max 2 seconds.")
        if time_frame.seconds == 0 and time_frame.microseconds < 111:
            raise ValueError("Time frame too small. Min 111 microseconds.")

        if delay.total_seconds() < 0:
            raise ValueError("Delay cannot be negative.")
        if delay.total_seconds() > 1:
            raise ValueError("Delay too large. Max 1 second.")

        ticks_per_sample = int(self._timedelta_to_ticks(time_frame) / 2000.0 + 0.5)
        assert ticks_per_sample > 0, "Ticks per sample must be greater than 0"
        delay_ticks = self._timedelta_to_ticks(delay)
        delay_samples = int(delay_ticks / ticks_per_sample)
        return self._raw_read(ticks_per_sample, trigger_fields, delay_samples)

    def _raw_read(self, tick_amount: int, trigger_fields: str, delay: int):
        logging.debug(f"Reading with {tick_amount} tick resolution with trigger {trigger_fields} and delay {delay}")
        data = self.serial.exec(f"scope {tick_amount} {trigger_fields} {delay}")
        data = pd.read_csv(
            io.StringIO(data),
            names=["bnc", "bitmap"],
            sep=",",
            header=None,
            dtype={0: float, 1: str})
        # data['bnc'] = data['bnc'] / 4
        return data

    @staticmethod
    def extract_bits(data: pd.DataFrame):
        data['bitmap'] = data['bitmap'].apply(functools.partial(int, base=16))
        for bit in range(10):
            data[f'bit_{bit}'] = data['bitmap'].apply(lambda x: bool((x >> bit) & 1))
        return data.drop(columns=['bitmap'])
    
    def unblock(self):
        self.serial.send_ctrl_c()

    def __del__(self):
        self.serial.exec("echo on")
        self.serial.exec("prompt on")


class FleaProbe():
    scope: FleaScope
    multiplier: int
    cal_zero: float | None = None
    cal_3v3: float | None = None

    def __init__(self, scope: FleaScope, multiplier: int):
        self.scope = scope
        self.multiplier = multiplier

    def read_calibration_from_flash(self):
        self.scope.serial.exec(f"dim cal_zero_x{self.multiplier} as flash, cal_3v3_x{self.multiplier} as flash")
        self.cal_zero = (int(self.scope.serial.exec(f"print cal_zero_x{self.multiplier}")) - 1000) + 2048
        self.cal_3v3 = (int(self.scope.serial.exec(f"print cal_3v3_x{self.multiplier}")) - 1000) / self.multiplier

        logging.debug(f"Probe x{self.multiplier} calibration: cal_zero={self.cal_zero}, cal_3v3={self.cal_3v3}")
        if (self.cal_zero == self.cal_3v3):
            raise ValueError(f"Calibration values for probe x{self.multiplier} are equal ({self.cal_zero}).")

    def set_calibration(self, offset_0: float, offset_3v3: float):
        self.cal_zero = offset_0
        self.cal_3v3 = offset_3v3

    def write_calibration_to_flash(self):
        if self.cal_zero is None or self.cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        self.scope.serial.exec(f"cal_zero_x{self.multiplier} = {int(self.cal_zero - 2048 + 1000 + 0.5)}")
        self.scope.serial.exec(f"cal_3v3_x{self.multiplier} = {int(self.cal_3v3 * self.multiplier + 1000 + 0.5)}")

    def read_stable_value_for_calibration(self):
        data = self.scope.raw_read(timedelta(milliseconds=20), 0)
        bnc_data = data['bnc']
        if bnc_data.max() - bnc_data.min() > 14:
            raise ValueError("Signal is not stable enough for calibration. Values ranged from "
                             f"{bnc_data.min()} to {bnc_data.max()}.")
        return bnc_data.mean()

    def _raw_to_voltage(self, raw_value: float):
        if self.cal_zero is None or self.cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        return (raw_value - self.cal_zero) / self.cal_3v3 * 3.3

    def _voltage_to_raw(self, voltage: float):
        if self.cal_zero is None or self.cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        return (voltage / 3.3 * self.cal_3v3) + self.cal_zero

    def calibrate_0(self):
        # should be within ([2028, 2140]) for x1. default 2104
        # should be within ([2028, 2208]) for x10. default 2160
        self.cal_zero = self.read_stable_value_for_calibration()
        return self.cal_zero

    def calibrate_3v3(self):
        # should be within [940, 1100] for x1. default 1036
        # should be within [88, 120] for x10. default 108
        if self.cal_zero is None:
            raise ValueError("Zero-Calibration needs to be done first.")
        self.cal_3v3 = self.read_stable_value_for_calibration() - self.cal_zero
        return self.cal_3v3

    def read(self, time_frame: timedelta, trigger: DigitalTrigger | AnalogTrigger | None = None, delay: timedelta = timedelta(milliseconds=0)):
        if trigger is None:
            trigger = AnalogTrigger(0, AnalogTriggerBehavior.AUTO)
        if isinstance(trigger, DigitalTrigger):
            trigger_fields = trigger.into_trigger_fields()
        else:
            trigger_fields = trigger.into_trigger_fields(self._voltage_to_raw)
        df = self.scope.raw_read(time_frame, trigger_fields, delay)
        df['bnc'] = self._raw_to_voltage(df['bnc'])
        return df
