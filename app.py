from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os
from werkzeug.utils import secure_filename
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "store.db")
UPLOAD = os.path.join(BASE, "static", "uploads")
os.makedirs(UPLOAD, exist_ok=True)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "change-me-123")

# ===== STORE SETTINGS =====
STORE_NAME = "Humaia Craft"
BKASH_NUMBER = "01752285231"       # Replace with your bKash number
NAGAD_NUMBER = "01752285231"       # Replace with your Nagad number
WHATSAPP_NUMBER = "01752285231" # Replace with your WhatsApp number, e.g. 8801712345678

# Delivery charges (৳)
DELIVERY_DHAKA = 80
DELIVERY_OUTSIDE_DHAKA = 130


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0, image TEXT, description TEXT,
        active INTEGER DEFAULT 1)""")

    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL, phone TEXT NOT NULL,
        address TEXT NOT NULL, payment TEXT NOT NULL,
        delivery_area TEXT DEFAULT 'Dhaka',
        delivery_charge REAL DEFAULT 0,
        subtotal REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL,
        transaction_id TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    # Upgrade an older database safely.
    columns = {r["name"] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
    upgrades = {
        "delivery_area": "ALTER TABLE orders ADD COLUMN delivery_area TEXT DEFAULT 'Dhaka'",
        "delivery_charge": "ALTER TABLE orders ADD COLUMN delivery_charge REAL DEFAULT 0",
        "subtotal": "ALTER TABLE orders ADD COLUMN subtotal REAL DEFAULT 0",
        "transaction_id": "ALTER TABLE orders ADD COLUMN transaction_id TEXT",
    }
    for col, sql in upgrades.items():
        if col not in columns:
            c.execute(sql)

    c.execute("""CREATE TABLE IF NOT EXISTS order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER,
        product_id INTEGER, product_name TEXT, quantity INTEGER, price REAL)""")

    if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        sample = [
            ("Rose Pearl Necklace","Jewelry",850,20,"📿","Beautiful handmade pearl necklace."),
            ("Pink Handmade Bracelet","Jewelry",450,30,"💎","Beautiful handmade pink bracelet."),
            ("Elegant Fashion Saree","Fashion",1650,15,"👗","Beautiful fashion saree."),
            ("Premium Gift Box","Gift",750,12,"🎁","Beautiful gift box for special occasions."),
            ("Cute Handbag","Fashion",990,10,"👜","Stylish everyday handbag."),
            ("Decorative Flower","Lifestyle",380,25,"🌸","Beautiful decorative flower.")
        ]
        c.executemany("""INSERT INTO products
            (name,category,price,stock,image,description) VALUES (?,?,?,?,?,?)""", sample)

    c.commit()
    c.close()


def get_cart():
    cart = session.get("cart", {})
    items, subtotal = [], 0
    c = db()

    for pid, qty in cart.items():
        p = c.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()
        if p:
            qty = int(qty)
            sub = p["price"] * qty
            items.append({"product": p, "quantity": qty, "subtotal": sub})
            subtotal += sub

    c.close()
    return items, subtotal


def delivery_charge(area):
    return DELIVERY_DHAKA if area == "Dhaka" else DELIVERY_OUTSIDE_DHAKA


@app.route("/")
def home():
    c = db()
    products = c.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    c.close()
    return render_template("home.html", products=products)


@app.route("/product/<int:pid>")
def product(pid):
    c = db()
    p = c.execute(
        "SELECT * FROM products WHERE id=? AND active=1", (pid,)
    ).fetchone()
    c.close()

    if not p:
        return "Product not found", 404

    return render_template("product.html", product=p)


@app.post("/cart/add/<int:pid>")
def add_cart(pid):
    c = db()
    p = c.execute(
        "SELECT * FROM products WHERE id=? AND active=1", (pid,)
    ).fetchone()
    c.close()

    if not p or p["stock"] < 1:
        flash("Product is out of stock.")
        return redirect(request.referrer or url_for("home"))

    cart = session.get("cart", {})
    cart[str(pid)] = min(int(cart.get(str(pid), 0)) + 1, p["stock"])
    session["cart"] = cart
    flash("Product added to cart.")
    return redirect(request.referrer or url_for("home"))


@app.get("/cart")
def cart():
    items, subtotal = get_cart()
    return render_template(
        "cart.html",
        items=items,
        subtotal=subtotal,
        delivery_dhaka=DELIVERY_DHAKA,
        delivery_outside=DELIVERY_OUTSIDE_DHAKA
    )


@app.post("/cart/update")
def update_cart():
    new = {}
    for k, v in request.form.items():
        if k.startswith("quantity_"):
            try:
                q = max(0, int(v))
            except ValueError:
                q = 0
            if q:
                new[k[9:]] = q

    session["cart"] = new
    flash("Cart updated.")
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, subtotal = get_cart()

    if not items:
        flash("Your cart is empty.")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        area = request.form.get("delivery_area", "Dhaka")
        payment = request.form.get("payment", "Cash on Delivery")
        transaction_id = request.form.get("transaction_id", "").strip()

        if area not in ["Dhaka", "Outside Dhaka"]:
            area = "Dhaka"

        if payment not in ["Cash on Delivery", "bKash", "Nagad"]:
            payment = "Cash on Delivery"

        if not name or not phone or not address:
            flash("Please fill all required fields.")
            return render_template(
                "checkout.html",
                items=items,
                subtotal=subtotal,
                delivery=delivery_charge(area),
                total=subtotal + delivery_charge(area),
                bkash=BKASH_NUMBER,
                nagad=NAGAD_NUMBER
            )

        if payment in ["bKash", "Nagad"] and not transaction_id:
            flash("Please enter your payment Transaction ID.")
            return render_template(
                "checkout.html",
                items=items,
                subtotal=subtotal,
                delivery=delivery_charge(area),
                total=subtotal + delivery_charge(area),
                bkash=BKASH_NUMBER,
                nagad=NAGAD_NUMBER
            )

        charge = delivery_charge(area)
        total = subtotal + charge

        c = db()

        for x in items:
            stock = c.execute(
                "SELECT stock FROM products WHERE id=?",
                (x["product"]["id"],)
            ).fetchone()

            if not stock or stock["stock"] < x["quantity"]:
                c.close()
                flash(f"Not enough stock for {x['product']['name']}.")
                return redirect(url_for("cart"))

        cur = c.execute("""
            INSERT INTO orders
            (customer_name,phone,address,payment,delivery_area,delivery_charge,
             subtotal,total,transaction_id)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            name, phone, address, payment, area, charge,
            subtotal, total, transaction_id
        ))

        oid = cur.lastrowid

        for x in items:
            p = x["product"]

            c.execute("""
                INSERT INTO order_items
                (order_id,product_id,product_name,quantity,price)
                VALUES(?,?,?,?,?)
            """, (
                oid, p["id"], p["name"], x["quantity"], p["price"]
            ))

            c.execute(
                "UPDATE products SET stock=stock-? WHERE id=?",
                (x["quantity"], p["id"])
            )

        c.commit()
        c.close()

        session["cart"] = {}

        wa_text = (
            f"New Humaia Craft Order #{oid}%0A"
            f"Customer: {name}%0A"
            f"Phone: {phone}%0A"
            f"Payment: {payment}%0A"
            f"Total: ৳{total:.0f}"
        )
        whatsapp_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(wa_text)}"

        return render_template(
            "success.html",
            order_id=oid,
            subtotal=subtotal,
            delivery=charge,
            total=total,
            whatsapp_url=whatsapp_url
        )

    default_delivery = DELIVERY_DHAKA

    return render_template(
        "checkout.html",
        items=items,
        subtotal=subtotal,
        delivery=default_delivery,
        total=subtotal + default_delivery,
        bkash=BKASH_NUMBER,
        nagad=NAGAD_NUMBER
    )


def admin_ok():
    return session.get("admin") is True


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (
            request.form.get("username") == ADMIN_USER
            and request.form.get("password") == ADMIN_PASS
        ):
            session["admin"] = True
            return redirect(url_for("admin"))

        flash("Invalid login.")

    return render_template("admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.get("/admin")
def admin():
    if not admin_ok():
        return redirect(url_for("admin_login"))

    c = db()

    products = c.execute(
        "SELECT * FROM products ORDER BY id DESC"
    ).fetchall()

    orders = c.execute(
        "SELECT * FROM orders ORDER BY id DESC"
    ).fetchall()

    stats = {
        "products": c.execute(
            "SELECT COUNT(*) FROM products WHERE active=1"
        ).fetchone()[0],
        "stock": c.execute(
            "SELECT COALESCE(SUM(stock),0) FROM products WHERE active=1"
        ).fetchone()[0],
        "orders": c.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0],
        "pending": c.execute(
            "SELECT COUNT(*) FROM orders WHERE status='Pending'"
        ).fetchone()[0],
        "revenue": c.execute(
            "SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled'"
        ).fetchone()[0],
    }

    c.close()

    return render_template(
        "admin.html",
        products=products,
        orders=orders,
        stats=stats
    )


@app.post("/admin/product/add")
def add_product():
    if not admin_ok():
        return redirect(url_for("admin_login"))

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    price = float(request.form.get("price", 0))
    stock = int(request.form.get("stock", 0))
    desc = request.form.get("description", "").strip()
    image = request.form.get("image", "").strip()

    f = request.files.get("photo")
    if f and f.filename:
        fn = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD, fn))
        image = fn

    c = db()
    c.execute("""
        INSERT INTO products
        (name,category,price,stock,image,description,active)
        VALUES(?,?,?,?,?,?,1)
    """, (name, category, price, stock, image, desc))
    c.commit()
    c.close()

    flash("Product added successfully.")
    return redirect(url_for("admin") + "#products")


@app.route("/admin/product/edit/<int:pid>", methods=["GET", "POST"])
def edit_product(pid):
    if not admin_ok():
        return redirect(url_for("admin_login"))

    c = db()
    p = c.execute(
        "SELECT * FROM products WHERE id=?", (pid,)
    ).fetchone()

    if not p:
        c.close()
        return "Product not found", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        desc = request.form.get("description", "").strip()
        image = request.form.get("image", "").strip() or p["image"]

        f = request.files.get("photo")
        if f and f.filename:
            fn = secure_filename(f.filename)
            f.save(os.path.join(UPLOAD, fn))
            image = fn

        c.execute("""
            UPDATE products
            SET name=?,category=?,price=?,stock=?,image=?,description=?
            WHERE id=?
        """, (name, category, price, stock, image, desc, pid))

        c.commit()
        c.close()

        flash("Product updated successfully.")
        return redirect(url_for("admin") + "#products")

    c.close()
    return render_template("product_edit.html", product=p)


@app.post("/admin/product/toggle/<int:pid>")
def toggle_product(pid):
    if not admin_ok():
        return redirect(url_for("admin_login"))

    c = db()
    c.execute("""
        UPDATE products
        SET active=CASE WHEN active=1 THEN 0 ELSE 1 END
        WHERE id=?
    """, (pid,))
    c.commit()
    c.close()

    return redirect(url_for("admin") + "#products")


@app.post("/admin/product/delete/<int:pid>")
def delete_product(pid):
    if not admin_ok():
        return redirect(url_for("admin_login"))

    c = db()
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    c.commit()
    c.close()

    flash("Product permanently deleted.")
    return redirect(url_for("admin") + "#products")


@app.post("/admin/order/status/<int:oid>")
def change_status(oid):
    if not admin_ok():
        return redirect(url_for("admin_login"))

    status = request.form.get("status", "Pending")
    allowed = [
        "Pending", "Confirmed", "Processing",
        "Shipped", "Delivered", "Cancelled"
    ]

    if status not in allowed:
        status = "Pending"

    c = db()
    c.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status, oid)
    )
    c.commit()
    c.close()

    return redirect(url_for("admin") + "#orders")


@app.get("/admin/order/<int:oid>")
def order_detail(oid):
    if not admin_ok():
        return redirect(url_for("admin_login"))

    c = db()

    order = c.execute(
        "SELECT * FROM orders WHERE id=?", (oid,)
    ).fetchone()

    items = c.execute(
        "SELECT * FROM order_items WHERE order_id=?",
        (oid,)
    ).fetchall()

    c.close()

    if not order:
        return "Order not found", 404

    return render_template(
        "order_detail.html",
        order=order,
        items=items
    )


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
