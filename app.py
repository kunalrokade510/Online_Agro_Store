from flask import Flask, render_template, request, redirect, session, flash, jsonify, send_file
import sqlite3, os, re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import secrets
from flask_mail import Mail, Message
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import csv

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # More secure secret key

# File upload configuration
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Email configuration (you'll need to add your SMTP details)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'jspmbsiotr23@gmail.com'  # Change this
app.config['MAIL_PASSWORD'] = 'Agro@510'      # Change this
app.config['MAIL_DEFAULT_SENDER'] = 'jspmbsiotr23@gmail.com'

mail = Mail(app)

DB = "database.db"

# ================= HELPER FUNCTIONS =================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Password must be at least 6 characters"""
    return len(password) >= 6

# ================= DATABASE =================
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, 
        email TEXT UNIQUE NOT NULL, 
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, 
        password TEXT NOT NULL);

    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, 
        category TEXT NOT NULL, 
        price REAL NOT NULL,
        image TEXT, 
        description TEXT,
        stock INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

    CREATE TABLE IF NOT EXISTS cart(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, 
        product_id INTEGER NOT NULL, 
        quantity INTEGER DEFAULT 1,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id));

    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, 
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL, 
        total_price REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id));

    CREATE TABLE IF NOT EXISTS user_profile(
        user_id INTEGER PRIMARY KEY,
        name TEXT, 
        dob TEXT, 
        gender TEXT, 
        image TEXT,
        phone TEXT,
        address TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id));

    CREATE TABLE IF NOT EXISTS admin_profile(
        admin_id INTEGER PRIMARY KEY,
        name TEXT, 
        dob TEXT, 
        gender TEXT, 
        image TEXT);

    CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(product_id) REFERENCES products(id),
        FOREIGN KEY(user_id) REFERENCES users(id));

    CREATE TABLE IF NOT EXISTS wishlist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id));

    CREATE TABLE IF NOT EXISTS password_reset(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0);
    """)

    # Create default admin with hashed password
    if not cur.execute("SELECT * FROM admin").fetchone():
        hashed = generate_password_hash("admin123")
        cur.execute("INSERT INTO admin VALUES(NULL,'admin',?)", (hashed,))

    conn.commit()
    conn.close()

init_db()

# ================= DECORATORS =================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            flash("Admin access required", "danger")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ================= AUTH =================
@app.route("/")
def home():
    if session.get("admin"):
        return redirect("/admin/dashboard")
    elif session.get("user_id"):
        return redirect("/products")
    return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        role = request.form.get("role")
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("All fields are required", "danger")
            return render_template("login.html")

        conn = db()

        if role == "admin":
            admin = conn.execute(
                "SELECT * FROM admin WHERE username=?", (email,)
            ).fetchone()
            
            if admin and check_password_hash(admin["password"], password):
                session.clear()
                session["admin"] = True
                session["admin_id"] = admin["id"]
                flash("Welcome Admin!", "success")
                conn.close()
                return redirect("/admin/dashboard")
        else:
            if not validate_email(email):
                flash("Invalid email format", "danger")
                conn.close()
                return render_template("login.html")

            user = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()
            
            if user and check_password_hash(user["password"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                flash(f"Welcome back, {user['name']}!", "success")
                conn.close()
                return redirect("/products")

        flash("Invalid credentials", "danger")
        conn.close()
        
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not all([name, email, password, confirm_password]):
            flash("All fields are required", "danger")
            return render_template("register.html")

        if not validate_email(email):
            flash("Invalid email format", "danger")
            return render_template("register.html")

        if not validate_password(password):
            flash("Password must be at least 6 characters", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html")

        conn = db()
        
        # Check if email already exists
        if conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone():
            flash("Email already registered", "danger")
            conn.close()
            return render_template("register.html")

        # Hash password and insert user
        hashed = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users(name, email, password) VALUES(?,?,?)",
            (name, email, hashed)
        )
        conn.commit()
        conn.close()
        
        flash("Registration successful! Please login.", "success")
        return redirect("/login")
        
    return render_template("register.html")

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not validate_email(email):
            flash("Invalid email format", "danger")
            return render_template("forgot_password.html")

        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        
        if user:
            # Generate reset token
            token = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=1)
            
            conn.execute(
                "INSERT INTO password_reset(email, token, expires_at) VALUES(?,?,?)",
                (email, token, expires)
            )
            conn.commit()
            
            # Send email (you need to configure SMTP)
            try:
                msg = Message("Password Reset Request", recipients=[email])
                reset_link = f"http://localhost:5000/reset_password/{token}"
                msg.body = f"""
Hello,

You requested a password reset. Click the link below to reset your password:

{reset_link}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.
                """
                mail.send(msg)
                flash("Password reset link sent to your email", "success")
            except:
                flash("Email service not configured. Contact admin.", "warning")
        else:
            # Don't reveal if email exists or not (security)
            flash("If the email exists, a reset link has been sent", "info")
        
        conn.close()
        return redirect("/login")
        
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = db()
    reset_req = conn.execute(
        "SELECT * FROM password_reset WHERE token=? AND used=0 AND expires_at > ?",
        (token, datetime.now())
    ).fetchone()
    
    if not reset_req:
        flash("Invalid or expired reset link", "danger")
        conn.close()
        return redirect("/login")
    
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        
        if not validate_password(password):
            flash("Password must be at least 6 characters", "danger")
            return render_template("reset_password.html", token=token)
        
        if password != confirm:
            flash("Passwords do not match", "danger")
            return render_template("reset_password.html", token=token)
        
        hashed = generate_password_hash(password)
        conn.execute("UPDATE users SET password=? WHERE email=?", 
                    (hashed, reset_req["email"]))
        conn.execute("UPDATE password_reset SET used=1 WHERE id=?", 
                    (reset_req["id"],))
        conn.commit()
        conn.close()
        
        flash("Password reset successful! Please login.", "success")
        return redirect("/login")
    
    conn.close()
    return render_template("reset_password.html", token=token)

# ================= USER PRODUCTS =================
@app.route("/products")
@login_required
def products():
    conn = db()
    
    # Get filter parameters
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")
    sort = request.args.get("sort", "newest")
    
    # Base query
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    # Apply filters
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    if category:
        query += " AND category=?"
        params.append(category)
    
    if min_price:
        query += " AND price >= ?"
        params.append(float(min_price))
    
    if max_price:
        query += " AND price <= ?"
        params.append(float(max_price))
    
    # Apply sorting
    if sort == "price_low":
        query += " ORDER BY price ASC"
    elif sort == "price_high":
        query += " ORDER BY price DESC"
    elif sort == "name":
        query += " ORDER BY name ASC"
    else:  # newest
        query += " ORDER BY created_at DESC"
    
    products = conn.execute(query, params).fetchall()
    
    # Get all categories for filter dropdown
    categories = conn.execute(
        "SELECT DISTINCT category FROM products ORDER BY category"
    ).fetchall()
    
    # Get wishlist items for current user
    wishlist_ids = [row["product_id"] for row in conn.execute(
        "SELECT product_id FROM wishlist WHERE user_id=?", 
        (session["user_id"],)
    ).fetchall()]
    
    conn.close()
    
    return render_template("products.html", 
                         products=products, 
                         categories=categories,
                         wishlist_ids=wishlist_ids,
                         search=search,
                         category=category,
                         min_price=min_price,
                         max_price=max_price,
                         sort=sort)

@app.route("/product/<int:pid>")
@login_required
def product_details(pid):
    conn = db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    
    if not product:
        flash("Product not found", "danger")
        conn.close()
        return redirect("/products")
    
    # Get reviews for this product
    reviews = conn.execute("""
        SELECT reviews.*, users.name as user_name
        FROM reviews
        JOIN users ON reviews.user_id = users.id
        WHERE reviews.product_id = ?
        ORDER BY reviews.created_at DESC
    """, (pid,)).fetchall()
    
    # Calculate average rating
    avg_rating = conn.execute(
        "SELECT AVG(rating) as avg FROM reviews WHERE product_id=?", (pid,)
    ).fetchone()["avg"]
    
    avg_rating = round(avg_rating, 1) if avg_rating else 0
    
    # Check if user already reviewed
    user_review = conn.execute(
        "SELECT * FROM reviews WHERE product_id=? AND user_id=?",
        (pid, session["user_id"])
    ).fetchone()
    
    # Check if in wishlist
    in_wishlist = conn.execute(
        "SELECT * FROM wishlist WHERE product_id=? AND user_id=?",
        (pid, session["user_id"])
    ).fetchone() is not None
    
    conn.close()
    
    return render_template("product_details.html", 
                         product=product, 
                         reviews=reviews,
                         avg_rating=avg_rating,
                         user_review=user_review,
                         in_wishlist=in_wishlist)

@app.route("/add_review/<int:pid>", methods=["POST"])
@login_required
def add_review(pid):
    rating = request.form.get("rating")
    comment = request.form.get("comment", "").strip()
    
    if not rating or int(rating) not in range(1, 6):
        flash("Invalid rating", "danger")
        return redirect(f"/product/{pid}")
    
    conn = db()
    
    # Check if already reviewed
    existing = conn.execute(
        "SELECT * FROM reviews WHERE product_id=? AND user_id=?",
        (pid, session["user_id"])
    ).fetchone()
    
    if existing:
        flash("You have already reviewed this product", "warning")
        conn.close()
        return redirect(f"/product/{pid}")
    
    conn.execute(
        "INSERT INTO reviews(product_id, user_id, rating, comment) VALUES(?,?,?,?)",
        (pid, session["user_id"], int(rating), comment)
    )
    conn.commit()
    conn.close()
    
    flash("Review added successfully", "success")
    return redirect(f"/product/{pid}")

# ================= WISHLIST =================
@app.route("/wishlist")
@login_required
def wishlist():
    conn = db()
    items = conn.execute("""
        SELECT products.*, wishlist.id as wishlist_id
        FROM wishlist
        JOIN products ON wishlist.product_id = products.id
        WHERE wishlist.user_id = ?
        ORDER BY wishlist.added_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    
    return render_template("wishlist.html", items=items)

@app.route("/add_to_wishlist/<int:pid>")
@login_required
def add_to_wishlist(pid):
    conn = db()
    
    existing = conn.execute(
        "SELECT * FROM wishlist WHERE user_id=? AND product_id=?",
        (session["user_id"], pid)
    ).fetchone()
    
    if existing:
        flash("Product already in wishlist", "info")
    else:
        conn.execute(
            "INSERT INTO wishlist(user_id, product_id) VALUES(?,?)",
            (session["user_id"], pid)
        )
        conn.commit()
        flash("Added to wishlist", "success")
    
    conn.close()
    return redirect(request.referrer or "/products")

@app.route("/remove_from_wishlist/<int:wid>")
@login_required
def remove_from_wishlist(wid):
    conn = db()
    conn.execute("DELETE FROM wishlist WHERE id=? AND user_id=?", 
                (wid, session["user_id"]))
    conn.commit()
    conn.close()
    
    flash("Removed from wishlist", "success")
    return redirect("/wishlist")

# ================= CART =================
@app.route("/add_to_cart/<int:pid>")
@login_required
def add_to_cart(pid):
    conn = db()
    
    # Check stock
    product = conn.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()
    
    if not product or product["stock"] <= 0:
        flash("Product out of stock", "danger")
        conn.close()
        return redirect(request.referrer or "/products")
    
    row = conn.execute(
        "SELECT * FROM cart WHERE user_id=? AND product_id=?",
        (session["user_id"], pid)
    ).fetchone()

    if row:
        if row["quantity"] >= product["stock"]:
            flash("Cannot add more, stock limit reached", "warning")
        else:
            conn.execute(
                "UPDATE cart SET quantity=quantity+1 WHERE id=?", (row["id"],)
            )
            conn.commit()
            flash("Cart updated", "success")
    else:
        conn.execute(
            "INSERT INTO cart(user_id, product_id, quantity) VALUES(?,?,1)", 
            (session["user_id"], pid)
        )
        conn.commit()
        flash("Added to cart", "success")

    conn.close()
    return redirect(request.referrer or "/cart")

@app.route("/buy_now/<int:pid>")
@login_required
def buy_now(pid):
    conn = db()
    
    # Check stock
    product = conn.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()
    
    if not product or product["stock"] <= 0:
        flash("Product out of stock", "danger")
        conn.close()
        return redirect(f"/product/{pid}")

    conn.execute("DELETE FROM cart WHERE user_id=?", (session["user_id"],))
    conn.execute(
        "INSERT INTO cart(user_id, product_id, quantity) VALUES(?,?,1)",
        (session["user_id"], pid)
    )
    conn.commit()
    conn.close()
    
    return redirect("/payment")

@app.route("/cart")
@login_required
def cart():
    conn = db()
    cart_items = conn.execute("""
        SELECT cart.id, products.id as product_id, products.name, 
               products.price, products.image, products.stock, cart.quantity
        FROM cart 
        JOIN products ON cart.product_id=products.id
        WHERE cart.user_id=?
    """, (session["user_id"],)).fetchall()
    
    total = sum(item["price"] * item["quantity"] for item in cart_items)
    
    conn.close()
    return render_template("cart.html", cart=cart_items, total=total)

@app.route("/update_cart/<int:cid>/<action>")
@login_required
def update_cart(cid, action):
    conn = db()
    
    if action == "inc":
        cart_item = conn.execute("""
            SELECT cart.quantity, products.stock 
            FROM cart 
            JOIN products ON cart.product_id = products.id
            WHERE cart.id=?
        """, (cid,)).fetchone()
        
        if cart_item and cart_item["quantity"] < cart_item["stock"]:
            conn.execute("UPDATE cart SET quantity=quantity+1 WHERE id=?", (cid,))
            flash("Quantity updated", "success")
        else:
            flash("Stock limit reached", "warning")
    elif action == "dec":
        conn.execute("UPDATE cart SET quantity=quantity-1 WHERE id=?", (cid,))
        conn.execute("DELETE FROM cart WHERE id=? AND quantity<=0", (cid,))
        flash("Quantity updated", "success")
    elif action == "remove":
        conn.execute("DELETE FROM cart WHERE id=?", (cid,))
        flash("Item removed from cart", "success")
    
    conn.commit()
    conn.close()
    return redirect("/cart")

# ================= PAYMENT & ORDERS =================
@app.route("/payment", methods=["GET","POST"])
@login_required
def payment():
    if request.method == "POST":
        payment_method = request.form.get("payment_method")
        
        if not payment_method:
            flash("Please select a payment method", "danger")
            return redirect("/payment")
        
        conn = db()
        
        # Get cart items
        items = conn.execute("""
            SELECT cart.product_id, cart.quantity, products.price, products.stock
            FROM cart 
            JOIN products ON cart.product_id=products.id
            WHERE cart.user_id=?
        """, (session["user_id"],)).fetchall()
        
        if not items:
            flash("Your cart is empty", "warning")
            conn.close()
            return redirect("/cart")
        
        # Validate stock availability
        for item in items:
            if item["quantity"] > item["stock"]:
                flash(f"Insufficient stock for some items", "danger")
                conn.close()
                return redirect("/cart")
        
        # Create orders and update stock
        for item in items:
            conn.execute(
                "INSERT INTO orders(user_id, product_id, quantity, total_price, status) VALUES(?,?,?,?,?)",
                (session["user_id"], item["product_id"], item["quantity"], 
                 item["quantity"] * item["price"], "confirmed")
            )
            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id=?",
                (item["quantity"], item["product_id"])
            )
        
        # Clear cart
        conn.execute("DELETE FROM cart WHERE user_id=?", (session["user_id"],))
        conn.commit()
        
        # Send order confirmation email
        user = conn.execute("SELECT email, name FROM users WHERE id=?", 
                          (session["user_id"],)).fetchone()
        
        try:
            msg = Message("Order Confirmation", recipients=[user["email"]])
            msg.body = f"""
Hello {user["name"]},

Your order has been confirmed!

Payment Method: {payment_method}
Total Items: {len(items)}

Thank you for shopping with us!
            """
            mail.send(msg)
        except:
            pass  # Email service not configured
        
        conn.close()
        flash("Order placed successfully!", "success")
        return redirect("/payment_success")
    
    # GET request - show payment page
    conn = db()
    cart_items = conn.execute("""
        SELECT products.name, products.price, cart.quantity
        FROM cart 
        JOIN products ON cart.product_id=products.id
        WHERE cart.user_id=?
    """, (session["user_id"],)).fetchall()
    
    total = sum(item["price"] * item["quantity"] for item in cart_items)
    conn.close()
    
    return render_template("payment.html", cart_items=cart_items, total=total)

@app.route("/payment_success")
@login_required
def payment_success():
    return render_template("payment_success.html")

@app.route("/orders")
@login_required
def orders():
    conn = db()
    orders = conn.execute("""
        SELECT orders.id, products.name, products.image, orders.quantity, 
               orders.total_price, orders.status, orders.order_date
        FROM orders 
        JOIN products ON orders.product_id=products.id
        WHERE orders.user_id=?
        ORDER BY orders.order_date DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    
    return render_template("orders.html", orders=orders)

@app.route("/download_invoice/<int:order_id>")
@login_required
def download_invoice(order_id):
    conn = db()
    order = conn.execute("""
        SELECT orders.*, products.name as product_name, users.name as user_name, users.email
        FROM orders
        JOIN products ON orders.product_id = products.id
        JOIN users ON orders.user_id = users.id
        WHERE orders.id=? AND orders.user_id=?
    """, (order_id, session["user_id"])).fetchone()
    
    if not order:
        flash("Order not found", "danger")
        conn.close()
        return redirect("/orders")
    
    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Header
    p.setFont("Helvetica-Bold", 24)
    p.drawString(1*inch, 10*inch, "INVOICE")
    
    p.setFont("Helvetica", 12)
    p.drawString(1*inch, 9.5*inch, f"Order ID: #{order['id']}")
    p.drawString(1*inch, 9.3*inch, f"Date: {order['order_date']}")
    
    # Customer details
    p.setFont("Helvetica-Bold", 14)
    p.drawString(1*inch, 8.8*inch, "Customer Details:")
    p.setFont("Helvetica", 12)
    p.drawString(1*inch, 8.5*inch, f"Name: {order['user_name']}")
    p.drawString(1*inch, 8.3*inch, f"Email: {order['email']}")
    
    # Order details
    p.setFont("Helvetica-Bold", 14)
    p.drawString(1*inch, 7.8*inch, "Order Details:")
    p.setFont("Helvetica", 12)
    p.drawString(1*inch, 7.5*inch, f"Product: {order['product_name']}")
    p.drawString(1*inch, 7.3*inch, f"Quantity: {order['quantity']}")
    p.drawString(1*inch, 7.1*inch, f"Status: {order['status'].upper()}")
    
    # Total
    p.setFont("Helvetica-Bold", 16)
    p.drawString(1*inch, 6.6*inch, f"Total: ₹{order['total_price']:.2f}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    conn.close()
    
    return send_file(buffer, as_attachment=True, 
                    download_name=f"invoice_{order_id}.pdf",
                    mimetype='application/pdf')

# ================= USER PROFILE =================
@app.route("/user/profile", methods=["GET","POST"])
@login_required
def user_profile():
    uid = session["user_id"]
    conn = db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        dob = request.form.get("dob", "")
        gender = request.form.get("gender", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        
        img = request.files.get("image")
        filename = None
        
        if img and img.filename:
            if allowed_file(img.filename):
                filename = secure_filename(img.filename)
                # Add timestamp to filename to avoid conflicts
                filename = f"{int(datetime.now().timestamp())}_{filename}"
                img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                flash("Invalid file type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                conn.close()
                return redirect("/user/profile")

        conn.execute("""
            INSERT OR REPLACE INTO user_profile(user_id, name, dob, gender, image, phone, address) 
            VALUES(?,?,?,?,?,?,?)
        """, (uid, name, dob, gender, filename, phone, address))
        conn.commit()
        flash("Profile updated successfully", "success")

    profile = conn.execute("SELECT * FROM user_profile WHERE user_id=?", (uid,)).fetchone()
    user = conn.execute("SELECT name, email FROM users WHERE id=?", (uid,)).fetchone()

    conn.close()
    return render_template("user_profile.html", profile=profile, user=user)

@app.route("/user/change_password", methods=["GET","POST"])
@login_required
def user_change_password():
    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        
        if not all([old, new, confirm]):
            flash("All fields are required", "danger")
            return render_template("user_change_password.html")
        
        if not validate_password(new):
            flash("New password must be at least 6 characters", "danger")
            return render_template("user_change_password.html")
        
        if new != confirm:
            flash("New passwords do not match", "danger")
            return render_template("user_change_password.html")
        
        conn = db()
        user = conn.execute("SELECT password FROM users WHERE id=?", 
                          (session["user_id"],)).fetchone()
        
        if not check_password_hash(user["password"], old):
            flash("Current password is incorrect", "danger")
        else:
            hashed = generate_password_hash(new)
            conn.execute("UPDATE users SET password=? WHERE id=?", 
                        (hashed, session["user_id"]))
            conn.commit()
            flash("Password changed successfully", "success")
        
        conn.close()
        
    return render_template("user_change_password.html")

# ================= ADMIN DASHBOARD =================
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = db()
    
    # Get statistics
    total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()["count"]
    total_orders = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()["count"]
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
    total_revenue = conn.execute("SELECT SUM(total_price) as total FROM orders").fetchone()["total"] or 0
    
    # Recent orders
    recent_orders = conn.execute("""
        SELECT orders.id, users.name as user_name, products.name as product_name, 
               orders.quantity, orders.total_price, orders.status, orders.order_date
        FROM orders
        JOIN users ON orders.user_id = users.id
        JOIN products ON orders.product_id = products.id
        ORDER BY orders.order_date DESC
        LIMIT 10
    """).fetchall()
    
    # Low stock products
    low_stock = conn.execute("""
        SELECT * FROM products WHERE stock < 10 ORDER BY stock ASC LIMIT 5
    """).fetchall()
    
    # Sales data for chart (last 7 days)
    sales_data = conn.execute("""
        SELECT DATE(order_date) as date, SUM(total_price) as revenue, COUNT(*) as orders
        FROM orders
        WHERE order_date >= date('now', '-7 days')
        GROUP BY DATE(order_date)
        ORDER BY date
    """).fetchall()
    
    # Category-wise sales
    category_sales = conn.execute("""
        SELECT products.category, SUM(orders.total_price) as revenue
        FROM orders
        JOIN products ON orders.product_id = products.id
        GROUP BY products.category
        ORDER BY revenue DESC
    """).fetchall()
    
    conn.close()
    
    return render_template("admin_dashboard.html",
                         total_products=total_products,
                         total_orders=total_orders,
                         total_users=total_users,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders,
                         low_stock=low_stock,
                         sales_data=sales_data,
                         category_sales=category_sales)

# ================= ADMIN PRODUCTS =================
@app.route("/admin/products")
@admin_required
def admin_products():
    conn = db()
    
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    
    if category:
        query += " AND category=?"
        params.append(category)
    
    query += " ORDER BY created_at DESC"
    
    products = conn.execute(query, params).fetchall()
    categories = conn.execute("SELECT DISTINCT category FROM products").fetchall()
    
    conn.close()
    return render_template("admin_products.html", products=products, categories=categories)

@app.route("/admin/add_product", methods=["GET","POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price = request.form.get("price", "")
        stock = request.form.get("stock", "0")
        description = request.form.get("description", "").strip()
        
        if not all([name, category, price]):
            flash("Name, category, and price are required", "danger")
            return render_template("admin_add_product.html")
        
        try:
            price = float(price)
            stock = int(stock)
            
            if price < 0 or stock < 0:
                raise ValueError
        except:
            flash("Invalid price or stock value", "danger")
            return render_template("admin_add_product.html")
        
        img = request.files.get("image")
        filename = None
        
        if img and img.filename:
            if allowed_file(img.filename):
                filename = secure_filename(img.filename)
                filename = f"{int(datetime.now().timestamp())}_{filename}"
                img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                flash("Invalid file type", "danger")
                return render_template("admin_add_product.html")
        
        conn = db()
        conn.execute(
            "INSERT INTO products(name, category, price, image, description, stock) VALUES(?,?,?,?,?,?)",
            (name, category, price, filename, description, stock)
        )
        conn.commit()
        conn.close()
        
        flash("Product added successfully", "success")
        return redirect("/admin/products")
        
    return render_template("admin_add_product.html")

@app.route("/admin/edit_product/<int:pid>", methods=["GET","POST"])
@admin_required
def admin_edit_product(pid):
    conn = db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    
    if not product:
        flash("Product not found", "danger")
        conn.close()
        return redirect("/admin/products")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price = request.form.get("price", "")
        stock = request.form.get("stock", "0")
        description = request.form.get("description", "").strip()
        
        if not all([name, category, price]):
            flash("Name, category, and price are required", "danger")
            return render_template("admin_edit_product.html", product=product)
        
        try:
            price = float(price)
            stock = int(stock)
            
            if price < 0 or stock < 0:
                raise ValueError
        except:
            flash("Invalid price or stock value", "danger")
            return render_template("admin_edit_product.html", product=product)
        
        filename = product["image"]
        
        if request.files.get("image") and request.files["image"].filename:
            img = request.files["image"]
            if allowed_file(img.filename):
                filename = secure_filename(img.filename)
                filename = f"{int(datetime.now().timestamp())}_{filename}"
                img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                flash("Invalid file type", "danger")
                return render_template("admin_edit_product.html", product=product)

        conn.execute("""
            UPDATE products 
            SET name=?, category=?, price=?, image=?, description=?, stock=?
            WHERE id=?
        """, (name, category, price, filename, description, stock, pid))
        conn.commit()
        conn.close()
        
        flash("Product updated successfully", "success")
        return redirect("/admin/products")

    conn.close()
    return render_template("admin_edit_product.html", product=product)

@app.route("/delete/<int:pid>")
@admin_required
def delete_product(pid):
    conn = db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    
    flash("Product deleted successfully", "success")
    return redirect("/admin/products")

# ================= ADMIN ORDERS =================
@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = db()
    
    status_filter = request.args.get("status", "")
    
    query = """
        SELECT orders.id, users.name as user_name, users.email, 
               products.name as product_name, orders.quantity, 
               orders.total_price, orders.status, orders.order_date
        FROM orders
        JOIN users ON orders.user_id = users.id
        JOIN products ON orders.product_id = products.id
        WHERE 1=1
    """
    params = []
    
    if status_filter:
        query += " AND orders.status=?"
        params.append(status_filter)
    
    query += " ORDER BY orders.order_date DESC"
    
    orders = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template("admin_orders.html", orders=orders, status_filter=status_filter)

@app.route("/admin/update_order_status/<int:order_id>", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status = request.form.get("status")
    
    if status not in ["pending", "confirmed", "shipped", "delivered", "cancelled"]:
        flash("Invalid status", "danger")
        return redirect("/admin/orders")
    
    conn = db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    
    # Get user email for notification
    order = conn.execute("""
        SELECT users.email, users.name, orders.id
        FROM orders
        JOIN users ON orders.user_id = users.id
        WHERE orders.id=?
    """, (order_id,)).fetchone()
    
    # Send email notification
    try:
        msg = Message("Order Status Update", recipients=[order["email"]])
        msg.body = f"""
Hello {order["name"]},

Your order #{order['id']} status has been updated to: {status.upper()}

Thank you for shopping with us!
        """
        mail.send(msg)
    except:
        pass
    
    conn.close()
    flash("Order status updated", "success")
    return redirect("/admin/orders")

@app.route("/admin/export_orders")
@admin_required
def export_orders():
    conn = db()
    orders = conn.execute("""
        SELECT orders.id, users.name as user_name, users.email,
               products.name as product_name, orders.quantity,
               orders.total_price, orders.status, orders.order_date
        FROM orders
        JOIN users ON orders.user_id = users.id
        JOIN products ON orders.product_id = products.id
        ORDER BY orders.order_date DESC
    """).fetchall()
    conn.close()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Order ID', 'Customer Name', 'Email', 'Product', 
                    'Quantity', 'Total Price', 'Status', 'Order Date'])
    
    # Data
    for order in orders:
        writer.writerow([order['id'], order['user_name'], order['email'],
                        order['product_name'], order['quantity'], 
                        order['total_price'], order['status'], order['order_date']])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'orders_{datetime.now().strftime("%Y%m%d")}.csv'
    )

# ================= ADMIN PROFILE =================
@app.route("/admin/profile", methods=["GET","POST"])
@admin_required
def admin_profile():
    conn = db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        dob = request.form.get("dob", "")
        gender = request.form.get("gender", "")
        
        img = request.files.get("image")
        filename = None
        
        if img and img.filename:
            if allowed_file(img.filename):
                filename = secure_filename(img.filename)
                filename = f"{int(datetime.now().timestamp())}_{filename}"
                img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                flash("Invalid file type", "danger")
                conn.close()
                return redirect("/admin/profile")

        conn.execute(
            "INSERT OR REPLACE INTO admin_profile VALUES(1,?,?,?,?)",
            (name, dob, gender, filename)
        )
        conn.commit()
        flash("Profile updated successfully", "success")

    profile = conn.execute("SELECT * FROM admin_profile WHERE admin_id=1").fetchone()
    admin = conn.execute("SELECT username FROM admin WHERE id=1").fetchone()

    conn.close()
    return render_template("admin_profile.html", profile=profile, admin=admin)

@app.route("/admin/change_password", methods=["GET","POST"])
@admin_required
def admin_change_password():
    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")

        if not all([old, new, confirm]):
            flash("All fields are required", "danger")
            return render_template("admin_change_password.html")
        
        if not validate_password(new):
            flash("New password must be at least 6 characters", "danger")
            return render_template("admin_change_password.html")

        if new != confirm:
            flash("New passwords do not match", "danger")
            return render_template("admin_change_password.html")

        conn = db()
        admin = conn.execute("SELECT password FROM admin WHERE id=1").fetchone()

        if not check_password_hash(admin["password"], old):
            flash("Current password is incorrect", "danger")
        else:
            hashed = generate_password_hash(new)
            conn.execute("UPDATE admin SET password=? WHERE id=1", (hashed,))
            conn.commit()
            flash("Password changed successfully", "success")

        conn.close()

    return render_template("admin_change_password.html")

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect("/login")

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)