from aiohttp import web
import asyncio

class ControlServer:
    # HTML content for the webpage (from "index.html")
    HTML = open("index.html", "r").read()

    # Handle the root page
    async def handle_index(self, _):
        return web.Response(text=self.HTML, content_type='text/html')

    # Handle joystick input
    async def handle_input(self, request):
        data = await request.json()
        velocity = data.get("velocity", 0.0)
        steering = data.get("steering", 0.0)
        print(f"Received input: Velocity={velocity:.2f}, Steering={steering:.2f}")
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
    control_server = ControlServer()
    asyncio.run(control_server.run_server())

