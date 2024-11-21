from aiohttp import web
from gpiozero import Robot, PhaseEnableMotor
import asyncio

class ControlServer:
    # HTML content for the webpage (from "index.html")
    HTML = open("index.html", "r").read()

    def __init__(self, dir_left: int, dir_right: int, pwm_left: int, pwm_right: int) -> None:
        left_motor = PhaseEnableMotor(dir_left, pwm_left)
        right_motor = PhaseEnableMotor(dir_right, pwm_right)
        self.robot = Robot(left_motor, right_motor)

    # Handle the root page
    async def handle_index(self, _):
        return web.Response(text=self.HTML, content_type='text/html')

    # Handle joystick input
    async def handle_input(self, request):
        data = await request.json()
        velocity = data.get("velocity", 0.0)
        steering = data.get("steering", 0.0)
        print(f"Received input: Velocity={velocity:.2f}, Steering={steering:.2f}")
        if velocity > 0.0:
            if steering > 0.0:
                self.robot.forward(velocity, curve_right=steering)
            else:
                self.robot.forward(velocity, curve_left=-steering)
        else:
            if steering > 0.0:
                self.robot.backward(-velocity, curve_right=steering)
            else:
                self.robot.backward(-velocity, curve_left=-steering)

        return web.Response(text="Input received")

    # Main function to set up the server
    async def run_server(self):
        app = web.Application()
        app.router.add_get('/', self.handle_index)
        app.router.add_post('/input', self.handle_input)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        print("Server running on http://localhost:8080")
        await site.start()
        # Keep running
        await asyncio.Event().wait()

if __name__ == '__main__':
    control_server = ControlServer(14, 15, 18, 23)
    asyncio.run(control_server.run_server())

