import os
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from email.message import EmailMessage
from email.utils import make_msgid
import aiosmtplib
import logging
import ssl
from config import settings

logger = logging.getLogger(__name__)

def generate_barcode_image(code: str) -> bytes:
    """Generate a Code128 barcode PNG image bytes for the given code."""
    code128 = barcode.get('code128', code, writer=ImageWriter())
    buffer = BytesIO()
    code128.write(buffer)
    return buffer.getvalue()

def _fmt_price(val: float) -> str:
    return f"{val:,.0f}".replace(",", ".") + " \u20ab"

async def send_preorder_email(
    to_email: str,
    customer_name: str,
    barcode_code: str,
    items: list[dict],
    subtotal: float,
    vat_amount: float,
    total: float,
) -> bool:
    """Send pre-order confirmation email with barcode image."""
    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST is not configured. Skipping email sending.")
        return False
        
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Xác nhận đặt hàng trước - {barcode_code}"
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>"
        msg['To'] = to_email
        
        image_bytes = generate_barcode_image(barcode_code)
        image_cid = make_msgid(domain="evient.pos")
        
        items_html = ""
        for item in items:
            items_html += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{item['product_name']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right;">{item['quantity']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right;">{_fmt_price(item['price'])}</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right;">{_fmt_price(item['price'] * item['quantity'])}</td>
            </tr>
            """
            
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Xin chào {customer_name},</h2>
                <p>Cảm ơn bạn đã đặt hàng trước. Dưới đây là thông tin đơn hàng của bạn:</p>
                
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Sản phẩm</th>
                            <th style="padding: 8px; text-align: right; border-bottom: 2px solid #ddd;">SL</th>
                            <th style="padding: 8px; text-align: right; border-bottom: 2px solid #ddd;">Đơn giá</th>
                            <th style="padding: 8px; text-align: right; border-bottom: 2px solid #ddd;">Thành tiền</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                    <tfoot>
                        <tr>
                            <td colspan="3" style="padding: 8px; text-align: right; font-weight: bold;">Tạm tính:</td>
                            <td style="padding: 8px; text-align: right;">{_fmt_price(subtotal)}</td>
                        </tr>
                        <tr>
                            <td colspan="3" style="padding: 8px; text-align: right; font-weight: bold;">VAT:</td>
                            <td style="padding: 8px; text-align: right;">{_fmt_price(vat_amount)}</td>
                        </tr>
                        <tr>
                            <td colspan="3" style="padding: 8px; text-align: right; font-weight: bold; font-size: 1.2em;">Tổng cộng:</td>
                            <td style="padding: 8px; text-align: right; font-weight: bold; font-size: 1.2em; color: #e74c3c;">{_fmt_price(total)}</td>
                        </tr>
                    </tfoot>
                </table>
                
                <div style="text-align: center; margin: 30px 0; padding: 20px; background-color: #f8f9fa; border-radius: 8px;">
                    <p style="margin-bottom: 10px; font-weight: bold;">Vui lòng xuất trình mã vạch này khi đến nhận hàng:</p>
                    <img src="cid:{image_cid[1:-1]}" alt="Barcode" style="max-width: 100%; height: auto;" />
                    <p style="margin-top: 10px; font-family: monospace; font-size: 1.2em;">{barcode_code}</p>
                </div>
                
                <p>Trân trọng,<br>Kessoku Event</p>
            </div>
        </body>
        </html>
        """
        
        msg.add_alternative(html_content, subtype='html')
        msg.get_payload()[0].add_related(
            image_bytes,
            'image',
            'png',
            cid=image_cid
        )
        
        use_tls = settings.SMTP_PORT == 465
        start_tls = settings.SMTP_PORT == 587 or (not use_tls and settings.SMTP_USE_TLS)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=use_tls,
            start_tls=start_tls,
            tls_context=context
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send pre-order email: {e}")
        return False
