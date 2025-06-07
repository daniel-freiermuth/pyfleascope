from datetime import timedelta
from enum import Enum
import functools
import logging
import pandas as pd
import io
import time
import pyudev
from pyfleascope.serial_terminal import FleaTerminal
from pyfleascope.trigger_config import AnalogTrigger, AnalogTriggerBehavior, DigitalTrigger

logging.basicConfig(level=logging.INFO)

class Waveform(Enum):
    SINE= "sine"
    SQUARE= "square"
    TRIANGLE= "triangle"
    EKG = "ekg"

class FleaConnector():
    @staticmethod
    def connect(name : str | None, port: str | None, baud: int, read_calibrations: bool):
        if port is None:
            name = 'FleaScope' if name is None else name
            serial = FleaConnector._get_working_serial(name, baud)
        else:
            logging.debug(f"Connecting to FleaScope on port {port} with baud rate {baud}")
            FleaConnector._validate_port(name, port)
            serial = FleaTerminal(port, baud)
            serial.initialize()
        return FleaScope(serial, read_calibrations)

    @staticmethod
    def _validate_port(name: str | None, port: str):
        context = pyudev.Context()
        device = pyudev.Devices.from_device_file(context, port)
        if not FleaConnector._validate_device(name, device):
            raise ValueError(f"Port {port} is not the FleaScope device you're looking for.")

    @staticmethod
    def _validate_device(name: str | None, device: pyudev.Device):
        valid_vendor_model_variants = [
          [ '0403', 'a660' ],
          [ '1b4f', 'a660' ],
          [ '1b4f', 'e66e' ],
          [ '04d8', 'e66e' ],
        ]

        if 'ID_MODEL' not in device.properties or \
            'ID_VENDOR_ID' not in device.properties or \
            'ID_MODEL_ID' not in device.properties or \
            [device.properties['ID_VENDOR_ID'], device.properties['ID_MODEL_ID']] not in valid_vendor_model_variants:
                return False
        if name is not None and device.properties['ID_MODEL'] != name:
                return False
        return True

    @staticmethod
    def _get_device_port(name: str) -> str:
        logging.debug(f"Searching for FleaScope device with name {name}")
        context = pyudev.Context()
        try:
            return next(
                     filter(
                         lambda d: FleaConnector._validate_device(name, d),
                         context.list_devices(subsystem='tty')
                   )).device_node
        except StopIteration:
            raise ValueError(f"No FleaScope device {name} found. Please connect a FleaScope or specify the port manually.")

    @staticmethod
    def _get_working_serial(name: str, baud:int):
        while True:
            port_candidate = FleaConnector._get_device_port(name)
            serial = FleaTerminal(port_candidate, baud)
            try:
                serial.initialize()
                break
            except TimeoutError:
                serial.send_reset()
                time.sleep(1)
        return serial

class FleaScope():
    _MSPS = 18 # Million samples per second. target sample rate
    _MCU_MHZ = 120 # MCU clock frequency in MHz, used for calculations
    _INTERLEAVE = 5 # number of ADCs interleaved
    _TOTAL_SAMPLES = 2000

    serial : FleaTerminal

    @staticmethod
    def connect(name : str | None = None, port: str | None = None, baud: int=9600, read_calibrations: bool=True):
        return FleaConnector.connect(name, port, baud, read_calibrations)

    def __init__(self, serial: FleaTerminal, read_calibrations: bool):
        self.serial = serial
        logging.debug("Turning off echo")
        self.serial.exec("echo off")

        # TODO try to gear up to 115200 baud

        self.ver = self.serial.exec("ver")
        logging.debug(f"FleaScope version: {self.ver}")
        # TODO check if version is compatible

        self.hostname = self.serial.exec("hostname")
        logging.debug(f"FleaScope hostname: {self.hostname}")
        # TODO check if hostname is correct
        self.x1 = FleaProbe(self, 1)
        self.x10 = FleaProbe(self, 10)

        if read_calibrations:
            self.x1.read_calibration_from_flash()
            self.x10.read_calibration_from_flash()
    
    def set_waveform(self, waveform: Waveform, hz: int):
        self.serial.exec(f"wave {waveform.value} {hz}")
    
    def _timedelta_to_us(self, time_frame: timedelta):
        return time_frame.microseconds + time_frame.seconds * 1000_000

    def _number1_to_prescaler(self, number1: int):
        ps = 16 if number1 > 1000 else 1
        t = int(self._MCU_MHZ * number1 * self._INTERLEAVE / ps / self._MSPS + 0.5) # mimics firmware calculation
        assert t > 0, "Prescaler must be greater than 0"
        assert t <= 65535, "Prescaler must be less than 65536"
        return ps*t
    
    def _prescaler_to_effective_msps(self, prescaler: int):
        return self._MCU_MHZ * self._INTERLEAVE / prescaler
        
    def raw_read(self, time_frame: timedelta, trigger_fields: str, delay: timedelta = timedelta(milliseconds=0)):
        if time_frame.total_seconds() < 0:
            raise ValueError("Time frame cannot be negative.")
        if time_frame.total_seconds() > 3.49:
            raise ValueError("Time frame too large.")
        if time_frame.seconds == 0 and time_frame.microseconds < 111:
            raise ValueError("Time frame too small. Min 111 microseconds.")

        if delay.total_seconds() < 0:
            raise ValueError("Delay cannot be negative.")
        # TODO: Check how delay is handled in firmware and adapt limit calculation
        if delay.total_seconds() > 1:
            raise ValueError("Delay too large. Max 1 second.")

        number1 = int(self._MSPS*self._timedelta_to_us(time_frame)/(self._TOTAL_SAMPLES + 0.0))
        assert number1 > 0, "Ticks per sample must be greater than 0"

        prescaler = self._number1_to_prescaler(number1)
        effective_msps = self._prescaler_to_effective_msps(prescaler)

        delay_samples = int(self._timedelta_to_us(delay) * effective_msps)
        assert delay_samples <= 1000_000

        logging.debug(f"Reading with {number1} tick resolution with trigger {trigger_fields} and delay {delay_samples}")
        data = self.serial.exec(f"scope {number1} {trigger_fields} {delay_samples}")
        data = pd.read_csv(
            io.StringIO(data),
            names=["bnc", "bitmap"],
            sep=",",
            header=None,
            dtype={0: float, 1: str})
        # TODO label jitter correctly
        data.set_index(
            pd.RangeIndex(start=0, stop=len(data), step=1) / 1_000_000 / effective_msps,
            inplace=True)
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
    _scope: FleaScope
    _multiplier: int
    _cal_zero: float | None = None # value for 0V
    _cal_3v3: float | None = None # value-diff 0V - 3.3V

    def __init__(self, scope: FleaScope, multiplier: int):
        self._scope = scope
        self._multiplier = multiplier
    
    def read_calibration_from_flash(self):
        dim_result = self._scope.serial.exec(f"dim cal_zero_x{self._multiplier} as flash, cal_3v3_x{self._multiplier} as flash")
        if dim_result == f"var 'cal_zero_x{self._multiplier}' already declared at this scope\r\nvar 'cal_3v3_x{self._multiplier}' already declared at this scope":
            logging.debug("Variables for calibration already declared. Reading values.")
        self._cal_zero = (int(self._scope.serial.exec(f"print cal_zero_x{self._multiplier}")) - 1000) + 2048
        self._cal_3v3 = (int(self._scope.serial.exec(f"print cal_3v3_x{self._multiplier}")) - 1000) / self._multiplier

        logging.debug(f"Probe x{self._multiplier} calibration: cal_zero={self._cal_zero}, cal_3v3={self._cal_3v3}")
        if (self._cal_zero == self._cal_3v3):
            raise ValueError(f"Calibration values for probe x{self._multiplier} are equal ({self._cal_zero}).")

    def set_calibration(self, offset_0: float, offset_3v3: float):
        self._cal_zero = offset_0
        self._cal_3v3 = offset_3v3

    def write_calibration_to_flash(self):
        if self._cal_zero is None or self._cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        self._scope.serial.exec(f"cal_zero_x{self._multiplier} = {int(self._cal_zero - 2048 + 1000 + 0.5)}")
        self._scope.serial.exec(f"cal_3v3_x{self._multiplier} = {int(self._cal_3v3 * self._multiplier + 1000 + 0.5)}")

    def read_stable_value_for_calibration(self):
        data = self._scope.raw_read(
            timedelta(milliseconds=20),
            DigitalTrigger.start_capturing_when().is_matching().into_trigger_fields())
        bnc_data = data['bnc']
        if bnc_data.max() - bnc_data.min() > 14:
            raise ValueError("Signal is not stable enough for calibration. Values ranged from "
                             f"{bnc_data.min()} to {bnc_data.max()}.")
        return bnc_data.mean()

    def _raw_to_voltage(self, raw_value: float):
        if self._cal_zero is None or self._cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        return (raw_value - self._cal_zero) / self._cal_3v3 * 3.3

    def _voltage_to_raw(self, voltage: float):
        if self._cal_zero is None or self._cal_3v3 is None:
            raise ValueError("Calibration values are not set.")
        return (voltage / 3.3 * self._cal_3v3) + self._cal_zero

    def calibrate_0(self):
        # should be within ([2028, 2140]) for x1. default 2104
        # should be within ([2028, 2208]) for x10. default 2160

        # TODO Things would become easier, if the 3v3 raw values
        # were stored directly and not as offset. But still stay
        # compatible to the flash values.
        
        try:
            raw_value_3v3 = self._voltage_to_raw(3.3)
        except ValueError:
            raw_value_3v3 = None
        self._cal_zero = self.read_stable_value_for_calibration()
        if raw_value_3v3 is not None:
            self._cal_3v3 = raw_value_3v3 - self._cal_zero
        return self._cal_zero

    def calibrate_3v3(self):
        # should be within [940, 1100] for x1. default 1036
        # should be within [88, 120] for x10. default 108
        if self._cal_zero is None:
            raise ValueError("Zero-Calibration needs to be done first.")
        self._cal_3v3 = self.read_stable_value_for_calibration() - self._cal_zero
        return self._cal_3v3

    def read(self, time_frame: timedelta, trigger: DigitalTrigger | AnalogTrigger | None = None, delay: timedelta = timedelta(milliseconds=0)):
        if trigger is None:
            trigger = AnalogTrigger(0, AnalogTriggerBehavior.AUTO)
        if isinstance(trigger, DigitalTrigger):
            trigger_fields = trigger.into_trigger_fields()
        else:
            trigger_fields = trigger.into_trigger_fields(self._voltage_to_raw)
        df = self._scope.raw_read(time_frame, trigger_fields, delay)
        df['bnc'] = self._raw_to_voltage(df['bnc'])
        return df
