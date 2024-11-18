from aiohttp import web
import asyncio

# HTML content for the webpage (from "index.html")
HTML = open("index.html", "r").read()
print(HTML)

# Handle the root page
async def handle_index(_):
    return web.Response(text=HTML, content_type='text/html')

# Handle joystick input
async def handle_input(request):
    data = await request.json()
    velocity = data.get("velocity", 0.0)
    steering = data.get("steering", 0.0)
    print(f"Received input: Velocity={velocity:.2f}, Steering={steering:.2f}")
    return web.Response(text="Input received")

# Main function to set up the server
async def run_server():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_post('/input', handle_input)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    print("Server running on http://localhost:8080")
    await site.start()
    # Keep running
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(run_server())

