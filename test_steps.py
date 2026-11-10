import unittest
import time

def read_voltage(target_channel):
    time.sleep(0.5)  # Symulacja opóźnienia sprzętowego
    return 12.0  # Zwracamy napięcie 12.0 V

def set_power(state):
    time.sleep(0.3)
    if state == "INVALID":
        raise ValueError("Invalid power state command!")
    return f"Power set to {state}"

# Przykład użycia unittest
class SystemHardwareTests(unittest.TestCase):
    def test_subtraction(self):
        self.assertEqual(10 - 2, 8)