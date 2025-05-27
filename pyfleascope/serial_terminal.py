import logging
import serial

class FleaTerminal:
    def __init__(self, port: str, baudrate: int = 9600):
        self._serial = serial.Serial(port, baudrate)
        self._port = port
        self._baudrate = baudrate
        self._prompt = '> '
        self._initialized = False
        self._flush()
    
    def initialize(self):
        logging.debug("Connected to FleaScope. Sending CTRL-C to reset.")
        self.send_ctrl_c()
        logging.debug("Turning on prompt")
        self._exec("prompt on", timeout=1.0)
        self._initialized = True
    
    def _flush(self):
        self._serial.timeout = 0
        self._serial.read_all()

    def exec(self, command: str, timeout: float | None = None):
        assert self._initialized, f"FleaTerminal {self._port} not initialized. Value: {self._initialized} Call initialize() first."
        return self._exec(command, timeout)

    def _exec(self, command: str, timeout: float | None):
        self._serial.write((command + "\n").encode())
        self._serial.timeout = timeout
        response = self._serial.read_until(self._prompt.encode()).decode()
        if response[-2:] != self._prompt:
            raise TimeoutError(f"Expected prompt '{self._prompt}' but got '{response[-2:]}'. Likely due to a timeout.")
        return response[:-2].strip()
    
    def send_ctrl_c(self):
        self._serial.write(b'\x03')
        self._flush()

    def send_reset(self):
        self._serial.write(b'reset\n')
    
    def __del__(self):
        self._serial.close()