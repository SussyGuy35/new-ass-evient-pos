import os
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

def generate_barcode_sheet(products: list[dict]) -> bytes:
    """Generate a PNG image sheet of products with barcodes."""
    
    # Filter products without barcode
    valid_products = [p for p in products if p.get("barcode")]
    
    if not valid_products:
        # Return an empty 1200x200 image if no products
        img = Image.new("RGB", (1200, 200), "white")
        draw = ImageDraw.Draw(img)
        font_path = os.path.join(os.path.dirname(__file__), "assets", "Roboto-Regular.ttf")
        try:
            font = ImageFont.truetype(font_path, 24)
        except IOError:
            font = ImageFont.load_default()
        draw.text((50, 80), "Không có sản phẩm nào có mã vạch.", fill="black", font=font)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    # Layout dimensions
    WIDTH = 1200
    COL_WIDTHS = [500, 300, 400]
    ROW_HEIGHT = 160
    HEADER_HEIGHT = 60
    PADDING = 20

    # Calculate total height
    HEIGHT = HEADER_HEIGHT + ROW_HEIGHT * len(valid_products)

    # Create main image
    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    # Load font
    font_path = os.path.join(os.path.dirname(__file__), "assets", "Roboto-Regular.ttf")
    try:
        font_header = ImageFont.truetype(font_path, 24)
        font_text = ImageFont.truetype(font_path, 20)
    except IOError:
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()

    # Draw header
    headers = ["Tên sản phẩm", "Giá tiền", "Mã vạch"]
    x_offset = 0
    for i, h in enumerate(headers):
        draw.rectangle([x_offset, 0, x_offset + COL_WIDTHS[i], HEADER_HEIGHT], fill="#f0f0f0", outline="black")
        draw.text((x_offset + PADDING, (HEADER_HEIGHT - 24) // 2), h, fill="black", font=font_header)
        x_offset += COL_WIDTHS[i]

    # Draw rows
    y_offset = HEADER_HEIGHT
    for p in valid_products:
        x_offset = 0
        
        # Draw cells outline
        for w in COL_WIDTHS:
            draw.rectangle([x_offset, y_offset, x_offset + w, y_offset + ROW_HEIGHT], outline="#ccc")
            x_offset += w
        
        # Col 1: Name
        name_text = str(p.get("name", ""))
        # Simple truncation if too long
        if len(name_text) > 40:
            name_text = name_text[:37] + "..."
        draw.text((PADDING, y_offset + (ROW_HEIGHT - 20) // 2), name_text, fill="black", font=font_text)
        
        # Col 2: Price
        price_val = p.get("price", 0)
        price_text = f"{price_val:,.0f}".replace(",", ".") + " \u20ab"
        draw.text((COL_WIDTHS[0] + PADDING, y_offset + (ROW_HEIGHT - 20) // 2), price_text, fill="black", font=font_text)
        
        # Col 3: Barcode
        bc_val = p.get("barcode")
        try:
            bc_class = barcode.get_barcode_class('code128')
            bc = bc_class(bc_val, writer=ImageWriter())
            # Configure writer options for better fit
            options = {
                'module_width': 0.3,
                'module_height': 10.0,
                'font_size': 8,
                'text_distance': 3.0,
                'quiet_zone': 2.0
            }
            bc_io = io.BytesIO()
            bc.write(bc_io, options=options)
            bc_io.seek(0)
            bc_img = Image.open(bc_io)
            
            # Resize if it's too big
            bc_max_width = COL_WIDTHS[2] - 2 * PADDING
            bc_max_height = ROW_HEIGHT - 2 * PADDING
            
            # Calculate ratio
            ratio = min(bc_max_width / bc_img.width, bc_max_height / bc_img.height)
            if ratio < 1:
                new_size = (int(bc_img.width * ratio), int(bc_img.height * ratio))
                bc_img = bc_img.resize(new_size, Image.Resampling.LANCZOS)
                
            # Paste image centered in cell
            paste_x = COL_WIDTHS[0] + COL_WIDTHS[1] + (COL_WIDTHS[2] - bc_img.width) // 2
            paste_y = y_offset + (ROW_HEIGHT - bc_img.height) // 2
            
            img.paste(bc_img, (paste_x, paste_y))
        except Exception as e:
            draw.text((COL_WIDTHS[0] + COL_WIDTHS[1] + PADDING, y_offset + (ROW_HEIGHT - 20) // 2), f"(Lỗi tạo barcode: {bc_val})", fill="red", font=font_text)

        y_offset += ROW_HEIGHT

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
