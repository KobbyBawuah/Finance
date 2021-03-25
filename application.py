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
    """Show portfolio of stocks"""
    rows = db.execute("SELECT symbol,SUM(shares) as total_shares FROM trade WHERE user_id =:user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])
    overall_total = 0
    holdings = []
    for row in rows:
        stock = lookup(row["symbol"])
        holdings.append({ "symbol": stock["symbol"], "name": stock["name"], "shares": row["total_shares"], "price": usd(stock["price"]), "total": usd(stock["price"] * row["total_shares"])})

        overall_total=overall_total + stock ["price"] * row["total_shares"]

    rows = db.execute("SELECT cash FROM users WHERE  id =:user_id", user_id=session["user_id"])
    current_cash = rows[0]["cash"]
    overall_total = overall_total + current_cash

    return render_template("index.html", holdings=holdings,current_cash = usd(current_cash), overall_total= usd(overall_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        result_checks = isFilled("symbol") or isFilled("shares")
        if result_checks:
            return result_checks
        elif not request.form.get("shares").isdigit():
            return apology ("Number of shares has to be a whole integer")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid Symbol")
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]
        remainingCash = cash - shares * stock['price']
        if remainingCash < 0:
            return apology("Not enough money")
        db.execute("UPDATE users SET cash=:remainingCash WHERE id=:id", remainingCash=remainingCash, id=session["user_id"])

        """ADD the trade to the trade table """
        db.execute("INSERT INTO trade (user_id,symbol,shares,price) VALUES(:user_id, :symbol, :shares, :price)",
            user_id=session["user_id"], symbol = stock["symbol"], shares = shares, price = stock["price"]),
        return redirect("/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    trades = db.execute("SELECT symbol, shares, price, traded FROM trade WHERE user_id =:user_id", user_id=session["user_id"])
    for i in range(len(trades)):
        trades[i]["price"] = usd(trades[i]["price"])
    return render_template("history.html", trades = trades)


def isFilled(field):
    if not request.form.get(field):
         return apology(f"must provide {field}", 403)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username and password was submitted
        result_checks = isFilled("username") or isFilled("password")
        if result_checks is not None:
            return result_checks

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
    if request.method == "GET":
        return render_template("quote.html")
    else:
        result_checks = isFilled("symbol")
        if result_checks is not None:
            return result_checks
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid Company Symbol",400)
        return render_template("quoted.html", stocksName ={
            'name': stock['name'],
            'symbol': stock['symbol'],
            'price': usd(stock['price'])
        })


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        result_checks = isFilled("username") or isFilled("password") or isFilled("confirmation")
        if result_checks is not None:
            return result_checks
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match")
        #reference from Deliberate Think
        try:
            primary = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username = request.form.get("username"), hash=generate_password_hash(request.form.get("password")))
        except:
            return apology("User name is already in use", 403)
        if primary is None:
            return apology("registration error", 403)

        session["user_id"] = primary
        return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        rows = db.execute("SELECT symbol FROM trade WHERE user_id =:user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])
        return render_template("sell.html", symbols=[row["symbol"] for row in rows])
    else:
        result_checks = isFilled("symbol") or isFilled("shares")
        if result_checks:
            return result_checks
        elif not request.form.get("shares").isdigit():
            return apology ("Number of shares has to be a whole integer")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid Symbol")

        rows = db.execute("SELECT symbol, SUM(shares) as total_shares FROM trade WHERE user_id=:user_id GROUP BY symbol HAVING total_shares >0; ", user_id=session["user_id"])

        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["total_shares"]:
                    return apology("You have less than the requested ammount of shares")

        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]

        remainingCash = cash + shares * stock['price']
        db.execute("UPDATE users SET cash=:remainingCash WHERE id=:id", remainingCash=remainingCash, id=session["user_id"])

        """ADD the trade to the trade table """
        db.execute("INSERT INTO trade (user_id,symbol,shares,price) VALUES(:user_id, :symbol, :shares, :price)",
            user_id=session["user_id"], symbol = stock["symbol"], shares = -1 * shares, price = stock["price"]),

        return redirect("/")

@app.route("/add_money", methods=["GET", "POST"])
@login_required
def add_money():
    if request.method == "POST":
        db.execute("UPDATE users SET cash=cash+:amount WHERE id=:user_id", amount = request.form.get("money"), user_id=session["user_id"])
        return (redirect("/"))
    else:
        return render_template("add_money.html")

@app.route("/remove_money", methods=["GET", "POST"])
@login_required
def remove_money():
    if request.method == "POST":
        db.execute("UPDATE users SET cash=cash-:amount WHERE id=:user_id", amount = request.form.get("money"), user_id=session["user_id"])
        return (redirect("/"))
    else:
        return render_template("remove_money.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
