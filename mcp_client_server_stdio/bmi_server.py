from mcp.server.fastmcp import FastMCP
from loguru import logger

mcp = FastMCP("BMI Server")

logger.info(f"Starting server {mcp.name}")

@mcp.tool()
def calculate_bmi(weight_kg:float, height_m:float) -> float:    
    """
    Calculate BMI given weight in kg and height in meters.
    """
    logger.info("Client is running the calculate_bmi tool")
    
    if height_m <= 0:
        raise ValueError("Height must be greater than zero.")
    result = weight_kg / (height_m ** 2)
    return f"{int(result)}"
    # return f"The BMI is {result:.2f}."


if __name__ == "__main__":
    mcp.run(transport="stdio")