from gpiozero import PhaseEnableMotor
import time

class ControlTest:
    def __init__(self) -> None:
        self.lf_motor = PhaseEnableMotor(7, 8)
        self.rf_motor = PhaseEnableMotor(6, 13)
        self.lr_motor = PhaseEnableMotor(24, 23)
        self.rr_motor = PhaseEnableMotor(19, 26)
        self.lf_motor.enable_device.frequency = 500
        self.rf_motor.enable_device.frequency = 500
        self.lr_motor.enable_device.frequency = 500
        self.rr_motor.enable_device.frequency = 500

    def move(self, lf_spd, lr_spd, rf_spd, rr_spd, duration):
        t0 = time.time()
        self.lf_motor.value = lf_spd
        self.rf_motor.value = rf_spd
        self.lr_motor.value = lr_spd
        self.rr_motor.value = rr_spd
        while time.time() - t0 < duration:
            pass

if __name__ == '__main__':
    control_server = ControlTest()
    control_server.move(0.5, 0.5, 1.0, 1.0, 2)
    control_server.move(0.0, 0.0, 0.0, 0.0, 0.5)

