import serial

class SerialTerminal:
    def __init__(self, port: str, baudrate: int = 9600, prompt: str = '>'):
        self._serial = serial.Serial(port, baudrate)
        self._port = port
        self._baudrate = baudrate
        self._prompt = prompt
        self._flush()
    
    def _flush(self):
        self._serial.timeout = 0
        self._serial.read_all()

    def exec(self, command: str, timeout: float | None = None):
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