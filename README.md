# Python library for instrumenting FleaScope

With this library, you can control and read your [FleaScope(s)](https://rtestardi.github.io/usbte/flea-scope.pdf).

# Usage

Connect to your FleaScope

```python
from pyfleascope.flea_scope import FleaScope

scope = FleaScope() # for default name FleaScope
# scope = FleaScope('scope1')
# scope = FleaScope(port='/dev/ttyACM0')
```
Connecting by name will also take care of resetting the device if necessary.

Get your first reading from the BNC connector
```python
df = scope.probe1.read(timedelta(milliseconds=20))['bnc']
```

## Triggers
Trigger reading on analog edges
```python
from pyfleascope.trigger_config import AnalogTrigger

df = scope.probe1.read(
            timedelta(milliseconds=20),
            trigger=AnalogTrigger.start_capturing_when().rising_edge(volts=2),
)
```

or on digital signals
```python
from pyfleascope.trigger_config import DigitalTrigger, BitState

df = scope.probe1.read(
            timedelta(milliseconds=20),
            trigger=DigitalTrigger.start_capturing_when()
              .bit1(BitState.HIGH)
              .bit7(BitState.LOW)
              .starts_matching(),
)
```

## Delay
Start capturing with a delay.
```python
df = scope.probe1.read(
            timedelta(milliseconds=20),
            trigger=AnalogTrigger.start_capturing_when().rising_edge(volts=2),
            delay=timedelta(milliseconds=0.2),
)
```

## Waveform
Configure the built-in waveform generator.

```python
from pyfleascope.flea_scope import Waveform

scope.set_waveform(Waveform.EKG, hz=1000)
```

## Digital inputs
The digital input is captured in the column `bitmask`.
The function `extract_bits` extracts boolean columns `bit_$i` for each bit.

```python
df = scope.probe1.read(
            timedelta(milliseconds=20),
            trigger=DigitalTrigger.start_capturing_when()
              .bit0(BitState.HIGH)
              .bit1(BitState.HIGH)
              .starts_matching(),
)
df = FleaScope.extract_bits(df)
df['bit_0'] = df['bit_0'].apply(int)
```

## Using multiple FleaScopes

Multiple FleaScopes can be used at the same time.
For exact timing alignment, the trigger signal can be forwarded.

```python
scope1 = FleaScope('/dev/ttyACM0')
scope2 = FleaScope('/dev/ttyACM1')


capture_time = timedelta(microseconds=120)

# Capture data from two FleaScopes at the same time by forwarding the trigger
# TRIGGER_OUT on scope1 is connected to Bit 0 on scope2 via cable

def read_scope1():
    time.sleep(1) # give scope1 time to prepare
    return scope1.probe1.read(
        capture_time,
        AnalogTrigger.start_capturing_when().auto(2),
    )

def read_scope2():
    return scope2.probe1.read(
            capture_time,
            DigitalTrigger.start_capturing_when().bit0(BitState.HIGH).starts_matching(),
    )

with ThreadPoolExecutor(max_workers=8) as executor:
    f1 = executor.submit(read_scope1)
    f2 = executor.submit(read_scope2)
    df1 = f1.result()
    df2 = f2.result()
```
