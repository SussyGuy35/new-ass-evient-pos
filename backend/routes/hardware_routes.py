"""
EViENT POS - Hardware Routes

Endpoints:
    POST /hardware/drawer - Opens the cash drawer via the server's serial port.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_current_user
from config import settings

router = APIRouter(prefix="/hardware", tags=["Hardware"])


class DrawerResponse(BaseModel):
    message: str
    success: bool


@router.post("/drawer", response_model=DrawerResponse)
async def open_drawer(current_user: dict = Depends(get_current_user)):
    """Open the cash drawer connected to the server.
    
    Requires SERVER_SERIAL_PORT to be configured in the environment.
    Uses the pyserial library to communicate with the hardware.
    """
    if not settings.SERVER_SERIAL_PORT:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Server serial port is not configured. Please set SERVER_SERIAL_PORT in .env.",
        )

    try:
        import serial
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="pyserial library is not installed on the server.",
        )

    try:
        # Open serial port
        ser = serial.Serial(
            port=settings.SERVER_SERIAL_PORT,
            baudrate=settings.BAUD_RATE,
            timeout=2
        )
        
        # Send command
        command_bytes = settings.CASH_DRAWER_COMMAND.encode('latin1')
        ser.write(command_bytes)
        
        # Close connection
        ser.close()
        
        return DrawerResponse(message="Cash drawer opened successfully.", success=True)
    except serial.SerialException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Serial port error: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open cash drawer: {e}",
        )
