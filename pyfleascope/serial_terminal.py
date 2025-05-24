import serial

class SerialTerminal:
    def __init__(self, port: str, baudrate: int = 9600, prompt: str = '>'):
        self.serial = serial.Serial(port, baudrate)
        self.port = port
        self.baudrate = baudrate
        self.prompt = prompt

    def exec(self, command: str, timeout: float | None = None):
        self.serial.write((command + "\n").encode())
        self.serial.timeout = timeout
        response = self.serial.read_until(self.prompt.encode()).decode()
        if response[-2:] != self.prompt:
            raise TimeoutError(f"Expected prompt '{self.prompt}' but got '{response[-2:]}'. Likely due to a timeout.")
        return response[:-2].strip()
    
    def send_ctrl_c(self):
        self.serial.write(b'\x03')

    def send_reset(self):
        self.serial.write(b'reset\n')
    
    def __del__(self):
        self.serial.close()