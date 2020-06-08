import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import time

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get user info
    user_id = session["user_id"]
    user_info = list(db.execute("SELECT * FROM users WHERE id = (?)", user_id))
    cash = float(user_info[0]["cash"])
    username = user_info[0]["username"]

    # If transactions table exists
    table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
    if table:

        # Get total shares from transaction history
        shares = db.execute("SELECT symbol, SUM(shares * buy_sell) AS 'shares' FROM transactions WHERE user_id = (?) GROUP BY symbol HAVING SUM(shares * buy_sell) > 0", user_id)

        # Get name and current share price from IXE and put everything into one table
        rows = len(shares)
        table = [[0]*5]*rows
        total_assets = cash
        for i in range(rows):
            stock = lookup(shares[i]["symbol"])
            table[i] = [shares[i]["symbol"], stock["name"], usd(float(stock["price"])), shares[i]["shares"], usd(float(stock["price"]) * shares[i]["shares"])]

            # Keep track of total assets
            total_assets += float(stock["price"]) * shares[i]["shares"]

        return render_template("index.html", username = username, table = table, cash = usd(cash), total_assets = usd(total_assets))

    # If transactions table does not exist, just display cash
    else:
        return render_template("index.html", username = username, cash = usd(cash), total_assets = usd(cash))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        shares_t = request.form.get("shares")

        # Apologize if stock is null or shares is blank
        if not stock:
            return apology("stock not found", 404)
        if not shares_t:
            return apology("specify number of shares", 402)


        # Apoligize if shares is not a positive integer
        n = len(shares_t)
        for i in range(n):
            if not shares_t[i].isdigit():
                return apology("shares must be a positive integer", 400)
        shares = float(shares_t)
        if shares % 1 > 0:
            return apology("shares must be a positive integer", 400)
        if shares < 1:
            return apology("shares must be a positive integer", 400)


        # Get user info from table
        user_id = session["user_id"]
        user_info = list(db.execute("SELECT * FROM users WHERE id = (?)", user_id))
        cash = float(user_info[0]["cash"])
        username = user_info[0]["username"]


        # Apologize if too poor
        price = float(stock["price"])
        if cash < shares * price:
            return apology("you're too poor", 400)

        # Create transactions table if it does not already exist
        table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if not table:
            db.execute("CREATE TABLE 'transactions' ('id' INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, 'user_id' INTEGER NOT NULL, 'symbol' TEXT NOT NULL, 'price' NUMERIC NOT NULL, 'shares' INTEGER NOT NULL, 'buy_sell' INTEGER NOT NULL, 'time' TIMESTAMP NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")

        # Store transaction
        buy_time = time.time()
        db.execute("INSERT INTO transactions (user_id, symbol, price, shares, buy_sell, time) VALUES (?, ?, ?, ?, ?, ?)", user_id, stock["symbol"], price, shares, 1, buy_time)

        # Update cash
        cash = cash - (shares * price)
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", cash, user_id)

        # Display successful transaction
        return render_template("bought.html", symbol = stock["symbol"], name = stock["name"], price = usd(price), shares = int(shares), total = usd(shares * price), cash = usd(cash), username = username)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get user info
    user_id = session["user_id"]
    user_info = list(db.execute("SELECT * FROM users WHERE id = (?)", user_id))
    username = user_info[0]["username"]

    # If transactions table exists
    table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
    if table:

        # Query transactions table
        transactions = db.execute("SELECT symbol, price, shares, buy_sell, time FROM transactions WHERE user_id = (?)", user_id)

        # Format data
        for transaction in transactions:
            transaction["price"] = usd(transaction["price"])
            transaction["time"] = time.ctime(transaction["time"])
            if transaction["buy_sell"] == 1:
               transaction["buy_sell"] = "BOUGHT"
            else:
                transaction["buy_sell"] = "SOLD"


        return render_template("history.html", transactions = transactions, username = username)

    # If transactions does not exist
    else:
        return render_template("history.html", username = username)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Do nothing if no symbol
        if not request.form.get("symbol"):
            return render_template("quote.html")

        # Lookup symbol
        stock = lookup(request.form.get("symbol"))

        # If symbol does not exist:
        if not stock:
            return render_template("quotef.html")

        # If symbol does exist:
        else:
            return render_template("quoted.html", name = stock["name"], symbol = stock["symbol"], price = usd(stock["price"]))


    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)
        else:
            username = request.form.get("username")

        # Ensure username does not already exist
        if len(db.execute("SELECT * FROM users WHERE username = (?)", username)) != 0:
            return apology("username already exists", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password matches confirmation
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 403)

        # Insert username and password hash into users
        password = request.form.get("password")
        phash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, phash)

        # Log user in
        rows = db.execute("SELECT id FROM users WHERE username = (?)", username)
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get user info
    user_id = session["user_id"]
    user_info = list(db.execute("SELECT * FROM users WHERE id = (?)", user_id))

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Get submit info
        stock_sell = lookup(request.form.get("symbol"))
        shares_sell_t = request.form.get("shares")

        # Apologize if blank
        if not stock_sell:
            return apology("stock not found", 404)
        if not shares_sell_t:
            return apology("specify number of shares", 402)

        # Apologize if shares is not a positive integer
        n = len(shares_sell_t)
        for i in range(n):
            if not shares_sell_t[i].isdigit():
                return apology("shares must be a positive integer", 400)
        shares_sell = float(shares_sell_t)
        if shares_sell % 1 > 0:
            return apology("shares must be a positive integer", 400)
        if shares_sell < 1:
            return apology("shares must be a positive integer", 400)

        # Get user info
        cash = float(user_info[0]["cash"])
        username = user_info[0]["username"]
        owned = db.execute("SELECT SUM(shares * buy_sell) AS 'shares' FROM transactions WHERE user_id = (?) AND symbol = (?)", user_id, stock_sell["symbol"])
        shares_own = owned[0]["shares"]

        # Apologize if user does not own that number of shows
        if shares_sell > shares_own:
            return apology("you don't own these shares", 400)

        # Store transaction
        sell_time = time.time()
        db.execute("INSERT INTO transactions (user_id, symbol, price, shares, buy_sell, time) VALUES (?, ?, ?, ?, ?, ?)", user_id, stock_sell["symbol"], stock_sell["price"], shares_sell, -1, sell_time)

        # Update cash
        cash = cash + (shares_sell * stock_sell["price"])
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", cash, user_id)

        # Display successful transaction
        if shares_sell == 1:
            plural = "share"
        else:
            plural = "shares"
        return render_template("sold.html", symbol = stock_sell["symbol"], name = stock_sell["name"], price = usd(stock_sell["price"]), shares = int(shares_sell), total = usd(shares_sell * stock_sell["price"]), cash = usd(cash), username = username, plural = plural)



    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # If transactions table exists
        table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if table:

            # Get user's assets
            assets = db.execute("SELECT symbol FROM transactions WHERE user_id = (?) GROUP BY symbol HAVING SUM(shares * buy_sell) > 0", user_id)

            # Load page
            return render_template("sell.html", assets = assets)

        # If transactions does not exist
        else:
            return render_template("sell.html")



@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add Cash to Account"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Get user info
        user_id = session["user_id"]
        user_info = list(db.execute("SELECT * FROM users WHERE id = (?)", user_id))
        username = user_info[0]["username"]
        cash = float(user_info[0]["cash"])

        # Get submit info
        add_t = request.form.get("amount")

        # Apologize if blank
        if not add_t:
            return apology("specify amount", 402)

        # Apologize if negative
        add = float(add_t)
        if add < 0:
            return apology("why would you want to add negative cash?", 400)

        # Add cash
        cash = cash + add
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", cash, user_id)

        # Display success
        return render_template("added.html", cash = usd(cash), username = username, amount = usd(add))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("add.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
