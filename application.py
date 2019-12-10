import os
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash


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
    user = session["user_id"]
    stocks = db.execute("SELECT * FROM transactions WHERE id = :user", user=user)
    cash = db.execute("SELECT cash FROM users WHERE id = :user", user=user)[0]['cash']
    nav = cash
    portfolio = set()
    for stock in stocks:
        if stock["symbol"] in portfolio:
            continue
        portfolio.add(stock["symbol"])
        symbol = stock["symbol"]
        stock["name"] = lookup(symbol)["name"]
        stock["quantity"] = db.execute("SELECT SUM(shares) FROM transactions WHERE symbol = :symb AND id = :user",
                                       symb=stock["symbol"], user=user)[0]['SUM(shares)']
        stock['price'] = lookup(symbol)["price"]
        stock['price1'] = usd(stock['price'])
        stock["total"] = usd(stock['price'] * stock["quantity"])
        stock["nav"] = stock['price'] * stock['quantity']
        nav += (stock["nav"])
    return render_template("index.html", stocks=stocks, nav=usd(nav), cash=usd(cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("Symbol invalid", 400)
        if not request.form.get("shares").isdigit():
            return apology("Shares must be a positive integer")
        if int(request.form.get("shares")) < 1:
            return apology("Shares must be a positive integer")

        cost = float(stock["price"]) * int(request.form.get("shares"))
        user = session["user_id"]
        cash0 = db.execute("SELECT cash FROM users WHERE id = :user", user=user)[0]["cash"]
        if cost > cash0:
            return apology("Not enough cash")
        newcash = cash0 - cost

        db.execute("INSERT INTO transactions (id, dir, symbol, shares, price) VALUES(:ident, :dire, :symb, :sharez, :pric)",
                   ident=user, dire="buy", symb=stock["symbol"], sharez=int(request.form.get("shares")), pric=stock["price"])
        db.execute("UPDATE users SET cash = :newcash WHERE id = :user", newcash=newcash, user=user)
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if len(username) > 0:
        if db.execute("SELECT * FROM users WHERE username = :user", user=username):
            return jsonify(False)
    return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = session["user_id"]
    stocks = db.execute("SELECT * FROM transactions WHERE id = :user", user=user)
    return render_template("history.html", stocks=stocks)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        user = session["user_id"]
        cash0 = db.execute("SELECT cash FROM users WHERE id = :user", user=user)[0]["cash"]
        if cash0 > 1000000:
            return apology("Cash balance too high")
        if not request.form.get("amount"):
            return apology("please enter deposit amount")
        if not request.form.get("amount").isdigit():
            return apology("amount must be a number")
        deposit = int(request.form.get("amount"))
        if deposit < 0:
            return apology("amount must be positive")
        if deposit > 100000:
            return apology("deposit amount too high")

        newcash = cash0 + deposit
        db.execute("UPDATE users SET cash = :newcash WHERE id = :user", newcash=newcash, user=user)
        return redirect("/")
    else:
        return render_template("/deposit.html")


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
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Symbol invalid", 400)
        return render_template("quoted.html", name=stock["name"], symbol=stock["symbol"], price=usd(stock["price"]))
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username:
            return apology("must provide username", 400)
        elif not password:
            return apology("must provide password", 400)
        elif not (request.form.get("confirmation") == password):
            return apology("passwords do not match", 400)

        hashedword = generate_password_hash(password)
        result = db.execute("INSERT INTO users (username, hash) VALUES(:name, :hashed)", name=username, hashed=hashedword)
        if not result:
            return apology("username already exists", 400)

        session.clear()
        session["user_id"] = result

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user = session["user_id"]
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not request.form.get("shares").isdigit():
            return apology("Shares must be a positive integer")
        if int(request.form.get("shares")) < 1:
            return apology("Shares must be a positive integer")
        if not symbol:
            return apology("No stock selected")

        shares = int(request.form.get("shares"))
        shares0 = db.execute("SELECT SUM(shares) FROM transactions WHERE symbol = :symb AND id = :user",
                             symb=symbol, user=user)[0]['SUM(shares)']
        if shares0 < shares:
            return apology("Not enough shares to sell")

        stock = lookup(symbol)
        proceeds = float(stock['price']) * shares
        cash0 = db.execute("SELECT cash FROM users WHERE id = :user", user=user)[0]['cash']
        cash = cash0 + proceeds

        db.execute("UPDATE users SET cash = :newcash WHERE id = :user", newcash=cash, user=user)
        db.execute("INSERT INTO transactions (id, dir, symbol, shares, price) VALUES(:ident, :dire, :symb, :sharez, :pric)",
                   ident=user, dire="sell", symb=symbol, sharez=-1 * shares, pric=stock["price"])
        return redirect("/")
    else:
        portfolio = set()
        stocks = db.execute("SELECT * FROM transactions WHERE id = :user", user=user)
        for stock in stocks:
            if stock['symbol'] in portfolio:
                continue
            portfolio.add(stock["symbol"])
            stock['quantity'] = db.execute("SELECT SUM(shares) FROM transactions WHERE symbol = :symb AND id = :user",
                                           symb=stock["symbol"], user=user)[0]['SUM(shares)']
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
