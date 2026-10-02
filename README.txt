HUMAIA CRAFT PRO STORE V2

Added:
- bKash/Nagad manual payment options with transaction ID
- Cash on Delivery
- Dhaka / Outside Dhaka delivery charge
- Checkout total calculation
- Order payment and delivery information in Admin
- Order detail page
- WhatsApp order button after checkout
- Existing product management and dashboard

IMPORTANT:
Open app.py and replace:
BKASH_NUMBER = "01XXXXXXXXX"
NAGAD_NUMBER = "01XXXXXXXXX"
WHATSAPP_NUMBER = "8801XXXXXXXXX"

Use your own store numbers before going live.

Run:
C:\Users\USER\.venv\Scripts\python.exe -m pip install -r requirements.txt
C:\Users\USER\.venv\Scripts\python.exe app.py

Open:
http://127.0.0.1:5000
Admin:
http://127.0.0.1:5000/admin
