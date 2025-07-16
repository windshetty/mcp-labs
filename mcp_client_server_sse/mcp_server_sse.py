import datetime
import os
from zoneinfo import ZoneInfo
import requests

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("MCP Server Streaming HTTP", host="0.0.0.0", port=8100)

@mcp.tool()
def TimeTool(input_timezone):
    "Provides the current time for a given city's timezone like Asia/Kolkata, America/New_York etc. If no timezone is provided, it returns the local time."
    format = "%Y-%m-%d %H:%M:%S %Z%z"
    current_time = datetime.datetime.now()    
    if input_timezone:
        print("TimeZone", input_timezone)
        current_time =  current_time.astimezone(ZoneInfo(input_timezone))
    return f"The current time is {current_time}."

@mcp.tool()
def weather_tool(location: str):
    """Provides weather information for a given location"""
        
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    response = requests.get(url)
    data = response.json()
    if data["cod"] == 200:
        temp = data["main"]["temp"]
        description = data["weather"][0]["description"]
        return f"The weather in {location} is currently {description} with a temperature of {temp}°C."
    else:
        return f"Sorry, I couldn't find weather information for {location}."



if __name__ == "__main__":
    mcp.run(transport="streamable-http")