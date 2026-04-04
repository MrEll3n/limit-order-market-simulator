import json
import os
import sqlite3
import bcrypt
import tornado


config = json.load(open("../config/server_config.json"))

# Database connection
db_path = os.path.join(os.path.dirname(__file__), "../server/market.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

class MainHandler(tornado.web.RequestHandler):
    """
    Main handler for the Tornado web application.
    """
    def get(self):
        """
        Render the main page of the application if the user is logged in.
        """
        user = self.get_secure_cookie("user")
        if user:
            self.render("static/index.html", host=config["HOST"], user=user.decode())
        else:
            self.redirect("/login")


class LoginHandler(tornado.web.RequestHandler):
    """
    Handler for the login page.
    """
    def get(self):
        """
        Render the login page.
        """
        # If there's an error message, pass it to the template
        error_message = self.get_argument("error", "")
        self.render("static/login.html", error_message=error_message)

    def post(self):
        """
        Handle the login form submission.
        :return:
        """
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")

        # Check if username exists in the database
        cursor.execute("SELECT * FROM users WHERE email=?", (username,))
        if cursor.fetchone() is None:
            # Redirect with an error message to the login page
            self.redirect("/login?error=User not found!")
            return

        # Check if the username is a valid email
        if "@" not in username:
            self.redirect("/login?error=Invalid email address!")
            return

        # Check if the password matches
        cursor.execute("SELECT password FROM users WHERE email=?", (username,))
        result = cursor.fetchone()
        stored_password = result[0]
        if not bcrypt.checkpw(password.encode('utf-8'),
                              stored_password.encode('utf-8')):  # Redirect with an error message to the login page
            self.redirect("/login?error=Incorrect password!")
            return

        # Redirect to dashboard or home page after successful login
        self.set_secure_cookie("user", username)
        self.redirect("/")


class RegisterHandler(tornado.web.RequestHandler):
    """
    Handler for the registration page.
    """
    def get(self):
        """
        Render the registration page.
        """
        # If there's an error message, pass it to the template
        error_message = self.get_argument("error", "")
        self.render("static/register.html", error_message=error_message)

    def post(self):
        """
        Handle the registration form submission.
        """
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")
        confirm_password = self.get_argument("confirm_password", "")

        # Check if the username is a valid email
        if "@" not in username:
            self.redirect("/register?error=Invalid email address!")
            return

        # Check if the username is already taken
        cursor.execute("SELECT * FROM users WHERE email=?", (username,))
        users = cursor.fetchall()
        if username in users:
            self.redirect("/register?error=Email already registered!")
            return

        # Check if the passwords match
        if password != confirm_password:
            self.redirect("/register?error=Passwords do not match!")
            return

        # Create a new user and save it to the database
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (username, hashed_password.decode('utf-8')))
        conn.commit()
        self.redirect("/login")


class LogoutHandler(tornado.web.RequestHandler):
    """
    Handler for the logout page.
    """
    def get(self):
        """
        Handle the logout request.
        """
        self.clear_cookie("user")
        self.redirect("/login")
