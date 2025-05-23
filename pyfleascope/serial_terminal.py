import serial

class SerialTerminal:
    def __init__(self, port: str, baudrate: int = 9600, prompt: str = '>'):
        self.serial = serial.Serial(port, baudrate)
        self.port = port
        self.baudrate = baudrate
        self.prompt = prompt

    def exec(self, command: str):
        self.serial.write((command + "\n").encode())
        response = self.serial.read_until(self.prompt.encode())
        return response.decode()[:-2].strip()
    
    def send_ctrl_c(self):
        self.serial.write(b'\x03')
    
    def __del__(self):
        self.serial.close()