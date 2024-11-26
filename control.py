from aiohttp import web
from gpiozero import PhaseEnableMotor
import asyncio
import pose_estimate

class ControlServer:
    # HTML content for the webpage (from "index.html")
    HTML = open("index.html", "r").read()

    def __init__(self, pose_estimator: pose_estimate.PoseEstimator) -> None:
        self.autonomous = False
        self.lf_motor = PhaseEnableMotor(7, 8)
        self.rf_motor = PhaseEnableMotor(6, 13)
        self.lr_motor = PhaseEnableMotor(24, 23)
        self.rr_motor = PhaseEnableMotor(19, 26)
        self.lf_motor.enable_device.frequency = 500
        self.rf_motor.enable_device.frequency = 500
        self.lr_motor.enable_device.frequency = 500
        self.rr_motor.enable_device.frequency = 500
        self.pose_estimator = pose_estimator

    async def handle_abort(self, _):
        self.lf_motor.stop()
        self.rf_motor.stop()
        self.lr_motor.stop()
        self.rr_motor.stop()

        # Exit the program
        loop = asyncio.get_event_loop()
        loop.stop()

        return web.Response(text="Aborted")

    # Handle the root page
    async def handle_index(self, _):
        return web.Response(text=self.HTML, content_type='text/html')

    def control(self, velocity, steering):
        left_throttle = velocity + steering
        right_throttle = velocity - steering

        self.lf_motor.value = left_throttle
        self.rf_motor.value = right_throttle
        self.lr_motor.value = left_throttle
        self.rr_motor.value = right_throttle

    # Handle joystick input
    async def handle_input(self, request):
        data = await request.json()
        velocity = data.get("velocity", 0.0)
        steering = data.get("steering", 0.0)
        print(f"Received input: Velocity={velocity:.2f}, Steering={steering:.2f}")

        if not self.autonomous:
            self.control(velocity, steering)
        else:
            pose_info = await self.pose_estimator.get_current_pose()
            if pose_info:
                direction = pose_info.get("direction", None)
                distance = pose_info.get("distance", None)

                if distance > 1.5:
                    velocity = 0.2
                else:
                    velocity = 0.0
                if direction > 0.3:
                    steering  = -0.1
                elif direction < -0.3:
                    steering = 0.1
                else:
                    steering = 0.0
                print(f"Received input: Velocity={velocity:.2f}, Steering={steering:.2f}")
                self.control(velocity, steering)


        return web.Response(text="Input received")

    async def handle_autonomous(self, request):
        self.autonomous = request.json().get("autonomous", False)
        print(f"Autonomous mode updated: {self.autonomous}")
        return web.Response(text="Autonomous mode updated")

    # Main function to set up the server
    async def run_server(self):
        app = web.Application()
        app.router.add_get('/', self.handle_index)
        app.router.add_post('/input', self.handle_input)
        app.router.add_post('/abort', self.handle_abort)
        app.router.add_post('/autonomous', self.handle_autonomous)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        print("Server running on http://localhost:8080")
        await site.start()
        # Keep running
        await asyncio.Event().wait()

async def main():
    import cv2
    stream = cv2.VideoCapture(0)
    pose_estimator = pose_estimate.PoseEstimator(stream)
    control_server = ControlServer(pose_estimator)
    server_task = asyncio.create_task(control_server.run_server())

    await asyncio.gather(server_task, pose_estimator.task)


if __name__ == "__main__":
    asyncio.run(main())
