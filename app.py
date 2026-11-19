import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
)
from mysql.connector import Error
from werkzeug.security import generate_password_hash
from flask_wtf.csrf import CSRFProtect

from database.db import get_db_connection
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

app = Flask(__name__)

load_dotenv()

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing from the .env file.")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
)
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)



def record_audit_log(cursor, user_id, action, description):
    """
    Record a user activity in the audit_log table.
    The calling route manages the transaction and commit.
    """

    cursor.execute(
        """
        INSERT INTO audit_log (
            user_id,
            action,
            description
        )
        VALUES (%s, %s, %s)
        """,
        (user_id, action, description)
    )

@app.route("/about")
def about():
    return render_template("about.html")



@app.route("/contact", methods=["GET", "POST"])
def contact():

    if request.method == "POST":

        # Collect and clean form data
        sender_name = request.form.get("sender_name", "").strip()
        sender_email = request.form.get("sender_email", "").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()

        # Identify the logged-in customer, if any
        customer_id = session.get("customer_id")

        # Validate required fields
        if not all([sender_name, sender_email, subject, description]):
            flash("Please complete all the required fields.", "error")
            return redirect(url_for("contact"))

        # Validate field lengths
        if len(sender_name) > 150 or len(sender_email) > 255 or len(subject) > 200:
            flash("One or more fields exceed the allowed length.", "error")
            return redirect(url_for("contact"))

        # Basic email validation
        if "@" not in sender_email or "." not in sender_email.rsplit("@", 1)[-1]:
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("contact"))

        db_conn = None
        cursor = None

        try:
            db_conn = get_db_connection()
            cursor = db_conn.cursor()

            cursor.execute(
                """
                INSERT INTO support_request (
                    customer_id,
                    sender_name,
                    sender_email,
                    subject,
                    description
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    customer_id,
                    sender_name,
                    sender_email,
                    subject,
                    description
                )
            )

            db_conn.commit()

            flash("Your message has been submitted successfully.", "success")
            return redirect(url_for("contact"))

        except Error:
            if db_conn:
                db_conn.rollback()

            app.logger.exception("Failed to submit contact request.")
            flash("We could not submit your message. Please try again.", "error")
            return redirect(url_for("contact"))

        finally:
            if cursor:
                cursor.close()

            if db_conn:
                db_conn.close()

    
    # Retrieve support requests for the logged-in customer
    support_requests = []

    if session.get("customer_id"):
        history_conn = None
        history_cursor = None

        try:
            history_conn = get_db_connection()
            history_cursor = history_conn.cursor(dictionary=True)

            history_cursor.execute("""
                SELECT
                    request_id,
                    subject,
                    status,
                    created_at
                FROM support_request
                WHERE customer_id = %s
                ORDER BY created_at DESC, request_id DESC
            """, (session["customer_id"],))

            support_requests = history_cursor.fetchall()

        except Exception:
            app.logger.exception(
                "Failed to retrieve customer support requests."
            )

        finally:
            if history_cursor is not None:
                history_cursor.close()

            if history_conn is not None and history_conn.is_connected():
                history_conn.close()

    return render_template(
        "contact.html",
        support_requests=support_requests
    )




@app.route("/")
def home():
    connection = None
    cursor = None
    movie_list = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
    SELECT
        movie_id,
        title,
        genre,
        duration,
        release_date,
        description,
        rating
    FROM movie
    WHERE movie_type = 'REAL'
    ORDER BY movie_id DESC
""")

        movie_list = cursor.fetchall()

    except Error:
        app.logger.exception(
            "Unable to retrieve homepage movies."
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "index.html",
        movies=movie_list
    )



@app.route("/movies")
def movies():
    connection = None
    cursor = None
    movie_list = []

    # Get the search term from the URL
    search_query = request.args.get("search", "").strip()

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if search_query:
            cursor.execute("""
                SELECT
                    movie_id,
                    title,
                    genre,
                    duration,
                    release_date,
                    description,
                    rating
                FROM movie
                WHERE movie_type = 'REAL'
                  AND LOWER(title) LIKE LOWER(%s)
                ORDER BY title
            """, (f"%{search_query}%",))

        else:
            cursor.execute("""
                SELECT
                    movie_id,
                    title,
                    genre,
                    duration,
                    release_date,
                    description,
                    rating
                FROM movie
                WHERE movie_type = 'REAL'
                ORDER BY title
            """)

        movie_list = cursor.fetchall()

    except Error:
        app.logger.exception("Unable to retrieve movies from the database.")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "movies.html",
        movies=movie_list,
        search_query=search_query
    )


@app.route("/movies/<int:movie_id>")
def movie_details(movie_id):
    connection = None
    cursor = None
    movie = None
    showtimes = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the selected movie.
        cursor.execute("""
            SELECT
                movie_id,
                title,
                genre,
                duration,
                release_date,
                description,
                rating
            FROM movie
            WHERE movie_id = %s
        """, (movie_id,))

        movie = cursor.fetchone()

        # Retrieve this movie's showtimes and their cinema details.
        if movie is not None:
            cursor.execute("""
                SELECT
                    st.showtime_id,
                    st.movie_id,
                    st.show_date,
                    st.start_time,
                    st.end_time,
                    s.screen_id,
                    s.screen_name,
                    s.capacity,
                    c.cinema_id,
                    c.name AS cinema_name,
                    c.location AS cinema_location
                FROM showtime AS st
                JOIN screen AS s
                    ON st.screen_id = s.screen_id
                JOIN cinema AS c
                    ON s.cinema_id = c.cinema_id
                WHERE st.movie_id = %s
                ORDER BY
                    st.show_date,
                    c.name,
                    st.start_time
            """, (movie_id,))

            showtimes = cursor.fetchall()

    except Error:
        app.logger.exception("Unable to retrieve movie details or showtimes.")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    if movie is None:
        return render_template("movie_not_found.html"), 404

    return render_template(
        "movie_details.html",
        movie=movie,
        showtimes=showtimes
    )



@app.route("/showtimes/<int:showtime_id>/seats")
def seat_selection(showtime_id):
    connection = None
    cursor = None
    showtime = None
    seats = []

    # Read seat IDs passed back from the booking summary.
    raw_selected_ids = request.args.getlist("seat_ids")
    try:
        selected_seat_ids = {
            int(seat_id)
            for seat_id in raw_selected_ids
        }
    except (TypeError, ValueError):
        selected_seat_ids = set()

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Get the selected screening details.
        cursor.execute("""
            SELECT
                st.showtime_id,
                st.movie_id,
                st.show_date,
                st.start_time,
                st.end_time,
                m.title AS movie_title,
                s.screen_id,
                s.screen_name,
                c.name AS cinema_name,
                c.location AS cinema_location
            FROM showtime AS st
            JOIN movie AS m
                ON st.movie_id = m.movie_id
            JOIN screen AS s
                ON st.screen_id = s.screen_id
            JOIN cinema AS c
                ON s.cinema_id = c.cinema_id
            WHERE st.showtime_id = %s
        """, (showtime_id,))

        showtime = cursor.fetchone()

        if showtime is not None:
            # Determine seat availability for this specific screening.
            cursor.execute("""
                SELECT
                    seat.seat_id,
                    seat.seat_number,
                    seat.seat_type,
                    seat.status,
                    CASE
                        WHEN seat.status = 'UNAVAILABLE'
                            THEN 0
                        WHEN EXISTS (
                            SELECT 1
                            FROM booking_seat AS bs
                            JOIN booking AS b
                                ON bs.booking_id = b.booking_id
                            WHERE bs.seat_id = seat.seat_id
                              AND b.showtime_id = %s
                              AND b.booking_status IN (
                                'PENDING', 'CONFIRMED'
                            )
AND (
    b.booking_status = 'CONFIRMED'
    OR b.customer_id != %s
)
                        )
                            THEN 0
                        ELSE 1
                    END AS is_available
                FROM seat
                WHERE seat.screen_id = %s
                ORDER BY seat.seat_number
                       """, (
                showtime_id,
                session.get("customer_id", -1),
                showtime["screen_id"]
            ))

            seats = cursor.fetchall()

    except Error:
        app.logger.exception(
            "Unable to retrieve seat availability for showtime %s.",
            showtime_id
        )
        return "Unable to load seat availability. Please try again.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    if showtime is None:
        return "Showtime not found.", 404

    return render_template(
    "seat_selection.html",
    showtime=showtime,
    seats=seats,
    selected_seat_ids=selected_seat_ids
)

@app.route("/showtimes/<int:showtime_id>/booking-summary", methods=["POST"])
def booking_summary(showtime_id):
    connection = None
    cursor = None

    try:
        # Read the submitted seat IDs.
        submitted_ids = request.form.getlist("seat_ids")

        if not submitted_ids:
            return "Please select at least one seat.", 400

        # Validate that every submitted ID is a positive integer.
        try:
            seat_ids = [int(seat_id) for seat_id in submitted_ids]

            if any(seat_id <= 0 for seat_id in seat_ids):
                raise ValueError

        except (ValueError, TypeError):
            return "Invalid seat selection.", 400

        # Reject duplicate IDs rather than silently charging twice.
        if len(seat_ids) != len(set(seat_ids)):
            return "Duplicate seats were submitted.", 400

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the screening and cinema information.
        cursor.execute("""
            SELECT
                st.showtime_id,
                st.movie_id,
                st.show_date,
                st.start_time,
                st.end_time,
                m.title AS movie_title,
                s.screen_id,
                s.screen_name,
                c.name AS cinema_name,
                c.location AS cinema_location
            FROM showtime AS st
            JOIN movie AS m
                ON st.movie_id = m.movie_id
            JOIN screen AS s
                ON st.screen_id = s.screen_id
            JOIN cinema AS c
                ON s.cinema_id = c.cinema_id
            WHERE st.showtime_id = %s
        """, (showtime_id,))

        showtime = cursor.fetchone()

        if showtime is None:
            return "Showtime not found.", 404

        # Retrieve the selected seats and check their current status.
        placeholders = ", ".join(["%s"] * len(seat_ids))

        cursor.execute(f"""
            SELECT
                seat.seat_id,
                seat.seat_number,
                seat.seat_type,
                seat.status
            FROM seat
            WHERE seat.seat_id IN ({placeholders})
              AND seat.screen_id = %s
            ORDER BY seat.seat_number
        """, (*seat_ids, showtime["screen_id"]))

        selected_seats = cursor.fetchall()

        # Every submitted ID must belong to this screening's screen.
        if len(selected_seats) != len(seat_ids):
            return "One or more selected seats are invalid.", 400

        # Reject seats marked unavailable in the database.
        if any(seat["status"] != "AVAILABLE" for seat in selected_seats):
            return "One or more selected seats are unavailable.", 409

        # Check whether another pending or confirmed booking has taken
        # any selected seat for this particular showtime.
        cursor.execute(f"""
            SELECT DISTINCT bs.seat_id
            FROM booking_seat AS bs
            JOIN booking AS b
                ON bs.booking_id = b.booking_id
            WHERE b.showtime_id = %s
              AND b.booking_status IN ('PENDING', 'CONFIRMED')
              AND bs.seat_id IN ({placeholders})
        """, (showtime_id, *seat_ids))

        unavailable_ids = cursor.fetchall()

        if unavailable_ids:
            return (
                "One or more selected seats have just been reserved. "
                "Please return to seat selection and choose again.",
                409
            )

        # Calculate the price on the server using database seat types.
        standard_price = 350
        vip_price = 500
        total_amount = 0

        for seat in selected_seats:
            if seat["seat_type"] == "VIP":
                seat["price"] = vip_price
            else:
                seat["price"] = standard_price

            total_amount += seat["price"]

    except Error:
        app.logger.exception(
            "Unable to prepare booking summary for showtime %s.",
            showtime_id
        )
        return "Unable to prepare the booking summary. Please try again.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

        start_time_display = str(showtime["start_time"])
    end_time_display = str(showtime["end_time"])

    # MySQL TIME values may be returned as timedelta objects.
    if hasattr(showtime["start_time"], "total_seconds"):
        start_seconds = int(showtime["start_time"].total_seconds())
        start_time_display = (
            f"{start_seconds // 3600:02d}:"
            f"{(start_seconds % 3600) // 60:02d}"
        )

    if hasattr(showtime["end_time"], "total_seconds"):
        end_seconds = int(showtime["end_time"].total_seconds())
        end_time_display = (
            f"{end_seconds // 3600:02d}:"
            f"{(end_seconds % 3600) // 60:02d}"
        )

    return render_template(
        "booking_summary.html",
        showtime=showtime,
        selected_seats=selected_seats,
        total_amount=total_amount,
        start_time_display=start_time_display,
        end_time_display=end_time_display
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template(
                "login.html",
                error="Please enter both your username and password."
            ), 400

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    u.user_id,
                    u.username,
                    u.password,
                    u.role,
                    u.account_status,
                    c.customer_id,
                    c.name AS customer_name,
                    e.employee_id,
                    e.name AS employee_name,
                    e.role AS employee_position,
                    m.manager_id,
                    m.name AS manager_name

                FROM users AS u

                LEFT JOIN customer AS c
                    ON c.user_id = u.user_id

                LEFT JOIN employee AS e
                    ON e.user_id = u.user_id

                LEFT JOIN manager AS m
                    ON m.user_id = u.user_id

                WHERE u.username = %s
                LIMIT 1
            """, (username,))

            user = cursor.fetchone()

            from werkzeug.security import check_password_hash

            if (
                user
                and user["account_status"] == "ACTIVE"
                and check_password_hash(user["password"], password)
            ):

                # Customer authentication
                if (
                    user["role"] == "CUSTOMER"
                    and user["customer_id"] is not None
                ):
                    session.clear()

                    session["user_id"] = user["user_id"]
                    session["customer_id"] = user["customer_id"]
                    session["username"] = user["username"]
                    session["customer_name"] = user["customer_name"]

                    return redirect("/")

                # Employee authentication
                elif (
                    user["role"] == "EMPLOYEE"
                    and user["employee_id"] is not None
                ):
                    session.clear()

                    session["user_id"] = user["user_id"]
                    session["employee_id"] = user["employee_id"]
                    session["username"] = user["username"]
                    session["employee_name"] = user["employee_name"]
                    session["employee_role"] = user["employee_position"]

                    return redirect(
                        url_for("employee_dashboard")
                    )

                    # Manager authentication
                elif (
                    user["role"] == "MANAGER"
                    and user["manager_id"] is not None
                ):
                    session.clear()

                    session["user_id"] = user["user_id"]
                    session["manager_id"] = user["manager_id"]
                    session["username"] = user["username"]
                    session["manager_name"] = user["manager_name"]
                    session["manager_role"] = user["role"]

                    return redirect(
                        url_for("manager_dashboard")
                    )

            return render_template(
                "login.html",
                error="Invalid username or password, or the account is unavailable."
            ), 401

        except Exception:
            app.logger.exception("Login failed.")
            return "Unable to log in right now. Please try again later.", 500

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("login.html")



@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validate required fields
        if not all([name, username, email, password, confirm_password]):
            return render_template(
                "register.html",
                error="Please fill in all required fields."
            ), 400

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Your passwords do not match."
            ), 400

        if len(name) > 100 or len(username) > 50 or len(email) > 100 or len(phone) > 20:
            return render_template(
                "register.html",
                error="One or more fields exceed the allowed length."
            ), 400

        if len(password) < 8:
            return render_template(
                "register.html",
                error="Your password must contain at least 8 characters."
            ), 400

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            # Check whether username or email already exists
            cursor.execute("""
                SELECT u.username, c.email
                FROM users AS u
                LEFT JOIN customer AS c
                    ON c.user_id = u.user_id
                WHERE u.username = %s
                   OR c.email = %s
                LIMIT 1
            """, (username, email))

            existing_user = cursor.fetchone()

            if existing_user:
                if existing_user["username"] == username:
                    error = "That username is already taken."
                else:
                    error = "An account with that email already exists."

                return render_template(
                    "register.html",
                    error=error
                ), 409

            # Create the login account
            hashed_password = generate_password_hash(password)

            cursor.execute("""
                INSERT INTO users (
                    username,
                    password,
                    role,
                    account_status
                )
                VALUES (%s, %s, 'CUSTOMER', 'ACTIVE')
            """, (username, hashed_password))

            user_id = cursor.lastrowid

            # Create the customer profile
            cursor.execute("""
                INSERT INTO customer (
                    user_id,
                    name,
                    email,
                    phone
                )
                VALUES (%s, %s, %s, %s)
            """, (
                user_id,
                name,
                email,
                phone if phone else None
            ))

            connection.commit()

            return redirect(url_for("login"))

        except Exception:
            if connection is not None:
                connection.rollback()

            app.logger.exception("Customer registration failed.")

            return render_template(
                "register.html",
                error="Registration could not be completed. Please try again."
            ), 500

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("register.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@app.route(
    "/showtimes/<int:showtime_id>/confirm-booking",
    methods=["POST"]
)
def confirm_booking(showtime_id):
    # Only logged-in customers can create bookings.
    customer_id = session.get("customer_id")
    if not customer_id:
        return redirect(url_for("login"))

    # Read the selected seat IDs from the submitted form.
    raw_seat_ids = request.form.getlist("seat_ids")

    if not raw_seat_ids:
        return "No seats were selected. Please select seats again.", 400

    try:
        seat_ids = [int(seat_id) for seat_id in raw_seat_ids]
    except (TypeError, ValueError):
        return "Invalid seat selection.", 400

    if any(seat_id <= 0 for seat_id in seat_ids):
        return "Invalid seat selection.", 400

    if len(seat_ids) != len(set(seat_ids)):
        return "Duplicate seats were submitted.", 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Confirm that this showtime exists and obtain its screen.
        cursor.execute(
            """
            SELECT showtime_id, screen_id
            FROM showtime
            WHERE showtime_id = %s
            FOR UPDATE
            """,
            (showtime_id,)
        )
        showtime = cursor.fetchone()

        if not showtime:
            connection.rollback()
            return "The selected showtime does not exist.", 404

        # Check that every seat belongs to this screen and is available.
        placeholders = ", ".join(["%s"] * len(seat_ids))

        cursor.execute(
            f"""
            SELECT seat_id, seat_number, seat_type, status
            FROM seat
            WHERE screen_id = %s
              AND seat_id IN ({placeholders})
            FOR UPDATE
            """,
            (showtime["screen_id"], *seat_ids)
        )
        seats = cursor.fetchall()

        if len(seats) != len(seat_ids):
            connection.rollback()
            return "One or more seats do not belong to this screen.", 400

        if any(seat["status"] != "AVAILABLE" for seat in seats):
            connection.rollback()
            return "One or more seats are unavailable. Please select again.", 409

               # Recheck seats reserved by other customers or confirmed bookings.
        cursor.execute(
            f"""
            SELECT DISTINCT bs.seat_id
            FROM booking_seat bs
            JOIN booking b ON b.booking_id = bs.booking_id
            WHERE b.showtime_id = %s
              AND b.booking_status IN ('PENDING', 'CONFIRMED')
              AND (
                  b.booking_status = 'CONFIRMED'
                  OR b.customer_id != %s
              )
              AND bs.seat_id IN ({placeholders})
            """,
            (showtime_id, customer_id, *seat_ids)
        )
        occupied_seats = cursor.fetchall()

        if occupied_seats:
            connection.rollback()
            return (
                "One or more selected seats have already been reserved. "
                "Please return to seat selection.",
                409
            )

        
        # Calculate the total on the server, not from browser input.
        total_amount = sum(
            500 if seat["seat_type"].upper() == "VIP" else 350
            for seat in seats
        )

        # Find this customer's existing pending booking for this showtime.
        cursor.execute(
            """
            SELECT booking_id
            FROM booking
            WHERE customer_id = %s
              AND showtime_id = %s
              AND booking_status = 'PENDING'
            ORDER BY booking_date DESC, booking_id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (customer_id, showtime_id)
        )
        existing_booking = cursor.fetchone()

        if existing_booking:
            booking_id = existing_booking["booking_id"]

            # Replace its seat selections with the newly submitted seats.
            cursor.execute(
                "DELETE FROM booking_seat WHERE booking_id = %s",
                (booking_id,)
            )

            cursor.execute(
                """
                UPDATE booking
                SET total_amount = %s
                WHERE booking_id = %s
                """,
                (total_amount, booking_id)
            )
        else:
            # Create a pending booking; payment has not been processed.
            cursor.execute(
                """
                INSERT INTO booking
                    (customer_id, showtime_id, total_amount, booking_status)
                VALUES (%s, %s, %s, 'PENDING')
                """,
                (customer_id, showtime_id, total_amount)
            )
            booking_id = cursor.lastrowid

        # Link the selected seats to this booking.
        for seat_id in seat_ids:
            cursor.execute(
                """
                INSERT INTO booking_seat (booking_id, seat_id)
                VALUES (%s, %s)
                """,
                (booking_id, seat_id)
            )

        connection.commit()

        return redirect(url_for("payment_page", booking_id=booking_id))


    except Error:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Could not create the pending booking.")
        return (
            "The booking could not be created. Please try again.",
            500
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Unexpected error creating a booking.")
        return "An unexpected error occurred.", 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()



@app.route("/payment/<int:booking_id>")
def payment_page(booking_id):
    # Only logged-in customers can access payment.
    customer_id = session.get("customer_id")

    if not customer_id:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the booking belonging to this customer.
        cursor.execute(
            """
            SELECT
                booking_id,
                customer_id,
                showtime_id,
                total_amount,
                booking_status
            FROM booking
            WHERE booking_id = %s
              AND customer_id = %s
            """,
            (booking_id, customer_id)
        )

        booking = cursor.fetchone()

        if not booking:
            return "Booking not found.", 404

        if booking["booking_status"] != "PENDING":
            return "This booking is not awaiting payment.", 400

        cursor.execute(
                        """
                        SELECT seat_id
                        FROM booking_seat
                        WHERE booking_id = %s
                        ORDER BY seat_id
                        """,
                        (booking_id,)
)
        selected_seats = cursor.fetchall()
        

        booking["seat_ids"] = [
        seat["seat_id"] for seat in selected_seats
]

        return render_template(
            "payment.html",
            booking=booking
        )

    except Error:
        app.logger.exception("Unable to load the payment page.")
        return "Unable to load payment details.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()




@app.route(
    "/payment/<int:booking_id>/process",
    methods=["POST"]
)
def process_payment(booking_id):
    # Only logged-in customers can make payments.
    customer_id = session.get("customer_id")

    if not customer_id:
        return redirect(url_for("login"))

    payment_method = request.form.get("payment_method")

    if payment_method not in ("MOBILE_MONEY", "CARD", "OTHER"):
        return "Invalid payment method.", 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Retrieve and lock the customer's pending booking.
        cursor.execute(
            """
            SELECT booking_id, total_amount, booking_status
            FROM booking
            WHERE booking_id = %s
              AND customer_id = %s
            FOR UPDATE
            """,
            (booking_id, customer_id)
        )

        booking = cursor.fetchone()

        if not booking:
            connection.rollback()
            return "Booking not found.", 404

        if booking["booking_status"] != "PENDING":
            connection.rollback()
            return "This booking is not awaiting payment.", 400

        # Check whether a payment record already exists.
        cursor.execute(
            """
            SELECT payment_id, payment_status
            FROM payment
            WHERE booking_id = %s
            FOR UPDATE
            """,
            (booking_id,)
        )

        existing_payment = cursor.fetchone()

        if existing_payment:
            if existing_payment["payment_status"] == "SUCCESSFUL":
                connection.rollback()
                return "This booking has already been paid.", 400

            cursor.execute(
                """
                UPDATE payment
                SET amount = %s,
                    payment_method = %s,
                    payment_status = 'SUCCESSFUL',
                    payment_date = CURRENT_TIMESTAMP,
                    transaction_reference = NULL
                WHERE payment_id = %s
                """,
                (
                    booking["total_amount"],
                    payment_method,
                    existing_payment["payment_id"]
                )
            )

        else:
            cursor.execute(
                """
                INSERT INTO payment
                    (booking_id, amount, payment_method,
                     payment_status)
                VALUES (%s, %s, %s, 'SUCCESSFUL')
                """,
                (
                    booking_id,
                    booking["total_amount"],
                    payment_method
                )
            )

        # Confirm the booking after successful simulated payment.
        cursor.execute(
            """
            UPDATE booking
            SET booking_status = 'CONFIRMED'
            WHERE booking_id = %s
            """,
            (booking_id,)
        )

        # Check whether a ticket already exists.
        cursor.execute(
            """
            SELECT ticket_id
            FROM ticket
            WHERE booking_id = %s
            FOR UPDATE
            """,
            (booking_id,)
        )

        existing_ticket = cursor.fetchone()

        if not existing_ticket:
            # Generate a unique ticket code.
            ticket_code = (
                f"ICCTMS-{booking_id}-"
                f"{__import__('uuid').uuid4().hex[:12].upper()}"
            )

            cursor.execute(
                """
                INSERT INTO ticket
                    (booking_id, ticket_code, ticket_status)
                VALUES (%s, %s, 'ACTIVE')
                """,
                (booking_id, ticket_code)
            )

        connection.commit()

        return redirect(
            url_for("ticket_page", booking_id=booking_id)
        )

    except Error:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Payment processing failed.")
        return "Payment processing failed. Please try again.", 500

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Unexpected payment processing error.")
        return "An unexpected error occurred.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


@app.route("/ticket/<int:booking_id>")
def ticket_page(booking_id):
    # Only logged-in customers can access their tickets.
    customer_id = session.get("customer_id")

    if not customer_id:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the customer's confirmed booking and ticket.
        cursor.execute(
            """
            SELECT
                b.booking_id,
                b.total_amount,
                b.booking_status,

                p.payment_method,
                p.payment_status,
                p.payment_date,

                t.ticket_code,
                t.issue_date,
                t.ticket_status,

                m.title AS movie_title,
                m.genre,
                m.duration,

                st.show_date,
                st.start_time,
                st.end_time,

                s.screen_name,

                c.name AS cinema_name,
                c.location AS cinema_location,

                GROUP_CONCAT(
                    CONCAT(seat.seat_number, ' (', seat.seat_type, ')')
                    ORDER BY seat.seat_number
                    SEPARATOR ', '
                ) AS booked_seats

            FROM booking b

            JOIN payment p
                ON b.booking_id = p.booking_id

            JOIN ticket t
                ON b.booking_id = t.booking_id

            JOIN showtime st
                ON b.showtime_id = st.showtime_id

            JOIN movie m
                ON st.movie_id = m.movie_id

            JOIN screen s
                ON st.screen_id = s.screen_id

            JOIN cinema c
                ON s.cinema_id = c.cinema_id

            JOIN booking_seat bs
                ON b.booking_id = bs.booking_id

            JOIN seat
                ON bs.seat_id = seat.seat_id

            WHERE b.booking_id = %s
              AND b.customer_id = %s
              AND b.booking_status = 'CONFIRMED'
              AND p.payment_status = 'SUCCESSFUL'

            GROUP BY
                b.booking_id,
                b.total_amount,
                b.booking_status,
                p.payment_method,
                p.payment_status,
                p.payment_date,
                t.ticket_code,
                t.issue_date,
                t.ticket_status,
                m.title,
                m.genre,
                m.duration,
                st.show_date,
                st.start_time,
                st.end_time,
                s.screen_name,
                c.name,
                c.location
            """,
            (booking_id, customer_id)
        )

        ticket = cursor.fetchone()

        if not ticket:
            return "Ticket not found or not available.", 404

        # Convert MySQL TIME values into readable strings.
        ticket["start_time_display"] = str(
            ticket["start_time"]
        )[:5]

        ticket["end_time_display"] = str(
            ticket["end_time"]
        )[:5]

        return render_template(
            "ticket.html",
            ticket=ticket
        )

    except Error:
        app.logger.exception("Unable to load the digital ticket.")
        return "Unable to load your ticket.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()



@app.route("/manager/staff")
def manager_staff():

    # Only authenticated managers can access staff management.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    account_status = request.args.get("account_status", "").strip()

    valid_statuses = ["ACTIVE", "INACTIVE", "SUSPENDED"]

    if account_status not in valid_statuses:
        account_status = ""

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                e.employee_id,
                e.name,
                e.email,
                e.role AS employee_position,
                u.username,
                u.account_status
            FROM employee e
            INNER JOIN users u
                ON e.user_id = u.user_id
            WHERE u.role = 'EMPLOYEE'
        """

        params = []

        if search:
            search_pattern = f"%{search}%"

            query += """
                AND (
                    CAST(e.employee_id AS CHAR) LIKE %s
                    OR e.name LIKE %s
                    OR e.email LIKE %s
                    OR e.role LIKE %s
                    OR u.username LIKE %s
                )
            """

            params.extend([
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern
            ])

        if account_status:
            query += " AND u.account_status = %s"
            params.append(account_status)

        query += " ORDER BY e.employee_id DESC"

        cursor.execute(query, params)
        staff = cursor.fetchall()

        return render_template(
            "manager_staff.html",
            staff=staff,
            search=search,
            account_status=account_status
        )

    except Exception:
        app.logger.exception("Manager staff list failed.")
        return "Unable to load staff records. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/staff/<int:employee_id>/status", methods=["POST"])
def update_staff_status(employee_id):

    # Only authenticated managers can manage employee accounts.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    new_status = request.form.get("account_status", "").strip().upper()

    valid_statuses = ["ACTIVE", "INACTIVE", "SUSPENDED"]

    if new_status not in valid_statuses:
        flash("Invalid employee account status.", "error")
        return redirect(url_for("manager_staff"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()

        cursor = connection.cursor(dictionary=True)

        # Confirm that the employee and their login account exist.
        cursor.execute(
            """
            SELECT
                e.employee_id,
                u.user_id,
                u.account_status
            FROM employee e
            INNER JOIN users u
                ON e.user_id = u.user_id
            WHERE e.employee_id = %s
              AND u.role = 'EMPLOYEE'
            FOR UPDATE
            """,
            (employee_id,)
        )

        employee = cursor.fetchone()

        if not employee:
            connection.rollback()
            flash("Employee record not found.", "error")
            return redirect(url_for("manager_staff"))

        cursor.execute(
            """
            UPDATE users
            SET account_status = %s
            WHERE user_id = %s
              AND role = 'EMPLOYEE'
            """,
            (new_status, employee["user_id"])
        )
        # Record the status change only when the status actually changes.
        if employee["account_status"] != new_status:
            record_audit_log(
                cursor,
                session["user_id"],
                "UPDATE_STAFF_STATUS",
                (
                    f"Manager changed employee #{employee_id} "
                    f"account status from "
                    f"{employee['account_status']} to {new_status}."
                )
            )

        connection.commit()

        flash(
            f"Employee account status updated to {new_status}.",
            "success"
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Employee account status update failed.")
        flash("Unable to update employee account status.", "error")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return redirect(url_for("manager_staff"))



@app.route("/manager/staff/<int:employee_id>/edit", methods=["GET", "POST"])
def edit_staff(employee_id):

    # Only authenticated managers can edit employee records.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the employee and associated login account.
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.user_id,
                e.name,
                e.email,
                e.role AS employee_position,
                u.username,
                u.account_status
            FROM employee e
            INNER JOIN users u
                ON e.user_id = u.user_id
            WHERE e.employee_id = %s
              AND u.role = 'EMPLOYEE'
            """,
            (employee_id,)
        )

        employee = cursor.fetchone()

        if not employee:
            flash("Employee record not found.", "error")
            return redirect(url_for("manager_staff"))

        if request.method == "POST":

            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            position = request.form.get("role", "").strip()
            username = request.form.get("username", "").strip()

            # Validate required fields.
            if not all([name, email, position, username]):
                flash("All fields are required.", "error")

            elif (
                len(name) > 100
                or len(email) > 100
                or len(position) > 50
                or len(username) > 50
            ):
                flash("One or more fields exceed the allowed length.", "error")

            elif "@" not in email or "." not in email.split("@")[-1]:
                flash("Please enter a valid email address.", "error")

            else:
                connection.rollback()
                connection.start_transaction()

                # Lock the employee record before updating it.
                cursor.execute(
                    """
                    SELECT
                        e.employee_id,
                        e.user_id
                    FROM employee e
                    INNER JOIN users u
                        ON e.user_id = u.user_id
                    WHERE e.employee_id = %s
                      AND u.role = 'EMPLOYEE'
                    FOR UPDATE
                    """,
                    (employee_id,)
                )

                current_employee = cursor.fetchone()

                if not current_employee:
                    connection.rollback()
                    flash("Employee record no longer exists.", "error")

                else:
                    user_id = current_employee["user_id"]

                    

                    # Check whether another employee uses this email.
                    cursor.execute(
                        """
                        SELECT employee_id
                        FROM employee
                        WHERE email = %s
                          AND employee_id <> %s
                        """,
                        (email, employee_id)
                    )

                    duplicate_employee_email = cursor.fetchone()

                    # Check whether a customer already uses this email.
                    cursor.execute(
                        """
                        SELECT customer_id
                        FROM customer
                        WHERE email = %s
                        """,
                        (email,)
                    )

                    duplicate_customer_email = cursor.fetchone()

                    # Check whether a manager already uses this email.
                    cursor.execute(
                        """
                        SELECT manager_id
                        FROM manager
                        WHERE email = %s
                        """,
                        (email,)
                    )

                    duplicate_manager_email = cursor.fetchone()

                    duplicate_email = (
                        duplicate_employee_email
                        or duplicate_customer_email
                        or duplicate_manager_email
                    )



                    # Check whether another account uses this username.
                    cursor.execute(
                        """
                        SELECT user_id
                        FROM users
                        WHERE username = %s
                          AND user_id <> %s
                        """,
                        (username, user_id)
                    )

                    duplicate_username = cursor.fetchone()

                    if duplicate_email:
                        connection.rollback()
                        flash(
                            "This email address is already in use.",
                            "error"
                        )

                    elif duplicate_username:
                        connection.rollback()
                        flash(
                            "This username is already in use.",
                            "error"
                        )

                    else:
                        cursor.execute(
                            """
                            UPDATE employee
                            SET name = %s,
                                email = %s,
                                role = %s
                            WHERE employee_id = %s
                            """,
                            (name, email, position, employee_id)
                        )

                        cursor.execute(
                            """
                            UPDATE users
                            SET username = %s
                            WHERE user_id = %s
                              AND role = 'EMPLOYEE'
                            """,
                            (username, user_id)
                        )

                        connection.commit()

                        flash(
                            "Employee information updated successfully.",
                            "success"
                        )

                        return redirect(url_for("manager_staff"))

            # Preserve submitted values if validation fails.
            employee["name"] = name
            employee["email"] = email
            employee["employee_position"] = position
            employee["username"] = username

        return render_template(
            "manager_edit_staff.html",
            employee=employee
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Employee editing failed.")
        return "Unable to process employee information. Please try again.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/employee/dashboard")
def employee_dashboard():

    # Only authenticated employees can access this dashboard.
    employee_id = session.get("employee_id")

    if not employee_id:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify that the employee account is still active.
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.name,
                e.email,
                e.role AS employee_position,
                u.account_status
            FROM employee e
            JOIN users u
                ON e.user_id = u.user_id
            WHERE e.employee_id = %s
              AND u.role = 'EMPLOYEE'
            """,
            (employee_id,)
        )

        employee = cursor.fetchone()

        if not employee or employee["account_status"] != "ACTIVE":
            session.clear()
            return redirect(url_for("login"))

        return render_template(
            "employee_dashboard.html",
            employee=employee
        )

    except Error:
        app.logger.exception("Unable to load employee dashboard.")
        return "Unable to load employee dashboard.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


@app.route("/employee/verify-ticket", methods=["POST"])
def verify_ticket():

    # Only authenticated employees can verify tickets.
    employee_id = session.get("employee_id")

    if not employee_id:
        return redirect(url_for("login"))

    ticket_code = request.form.get("ticket_code", "").strip()

    if not ticket_code:
        return "Please enter a ticket code.", 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Confirm that the employee account is still active.
        cursor.execute(
            """
            SELECT employee_id
            FROM employee e
            JOIN users u
                ON e.user_id = u.user_id
            WHERE e.employee_id = %s
              AND u.role = 'EMPLOYEE'
              AND u.account_status = 'ACTIVE'
            """,
            (employee_id,)
        )

        employee = cursor.fetchone()

        if not employee:
            session.clear()
            return redirect(url_for("login"))

        # Retrieve ticket and associated booking information.
        cursor.execute(
            """
            SELECT
                b.booking_id,
                b.total_amount,
                b.booking_status,

                p.payment_method,
                p.payment_status,

                t.ticket_id,
                t.ticket_code,
                t.issue_date,
                t.ticket_status,

                m.title AS movie_title,
                m.genre,

                st.show_date,
                st.start_time,
                st.end_time,

                s.screen_name,

                c.name AS cinema_name,
                c.location AS cinema_location,

                GROUP_CONCAT(
                    CONCAT(seat.seat_number, ' (', seat.seat_type, ')')
                    ORDER BY seat.seat_number
                    SEPARATOR ', '
                ) AS booked_seats

            FROM ticket t

            JOIN booking b
                ON t.booking_id = b.booking_id

            JOIN payment p
                ON b.booking_id = p.booking_id

            JOIN showtime st
                ON b.showtime_id = st.showtime_id

            JOIN movie m
                ON st.movie_id = m.movie_id

            JOIN screen s
                ON st.screen_id = s.screen_id

            JOIN cinema c
                ON s.cinema_id = c.cinema_id

            JOIN booking_seat bs
                ON b.booking_id = bs.booking_id

            JOIN seat
                ON bs.seat_id = seat.seat_id

            WHERE t.ticket_code = %s

            GROUP BY
                b.booking_id,
                b.total_amount,
                b.booking_status,
                p.payment_method,
                p.payment_status,
                t.ticket_id,
                t.ticket_code,
                t.issue_date,
                t.ticket_status,
                m.title,
                m.genre,
                st.show_date,
                st.start_time,
                st.end_time,
                s.screen_name,
                c.name,
                c.location
            """,
            (ticket_code,)
        )

        ticket = cursor.fetchone()

        if not ticket:
            return render_template(
                "employee_ticket_result.html",
                ticket=None,
                searched_code=ticket_code,
                error="No ticket was found with that code."
            )

        # Convert MySQL TIME values into readable strings.
        ticket["start_time_display"] = str(
            ticket["start_time"]
        )[:5]

        ticket["end_time_display"] = str(
            ticket["end_time"]
        )[:5]

        return render_template(
            "employee_ticket_result.html",
            ticket=ticket,
            searched_code=ticket_code,
            error=None
        )

    except Error:
        app.logger.exception("Employee ticket lookup failed.")
        return "Unable to verify ticket right now.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()



@app.route("/employee/admit-ticket", methods=["POST"])
def admit_ticket():

    # Only authenticated employees can admit customers.
    employee_id = session.get("employee_id")

    if not employee_id:
        return redirect(url_for("login"))

    ticket_code = request.form.get("ticket_code", "").strip()

    if not ticket_code:
        return "Ticket code is required.", 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Verify that the employee account is active.
        cursor.execute(
            """
            SELECT e.employee_id
            FROM employee e
            JOIN users u
                ON e.user_id = u.user_id
            WHERE e.employee_id = %s
              AND u.role = 'EMPLOYEE'
              AND u.account_status = 'ACTIVE'
            """,
            (employee_id,)
        )

        employee = cursor.fetchone()

        if not employee:
            connection.rollback()
            session.clear()
            return redirect(url_for("login"))

        # Lock the ticket and its booking/payment records.
        # This prevents two employees from admitting the same ticket
        # at the same time.
        cursor.execute(
            """
            SELECT
                t.ticket_id,
                t.ticket_status,
                b.booking_status,
                p.payment_status,
                (
                    TIMESTAMP(st.show_date, st.start_time) > NOW()
                ) AS showtime_upcoming

            FROM ticket t

            JOIN booking b
                ON t.booking_id = b.booking_id

            JOIN payment p
                ON b.booking_id = p.booking_id

            JOIN showtime st
                ON b.showtime_id = st.showtime_id

            WHERE t.ticket_code = %s

            FOR UPDATE
            """,
            (ticket_code,)
        )

        ticket = cursor.fetchone()

        if not ticket:
            connection.rollback()

            return render_template(
                "admission_result.html",
                success=False,
                message="Ticket not found.",
                ticket_code=ticket_code
            )

        # Check the ticket's current status.
        if ticket["ticket_status"] != "ACTIVE":
            connection.rollback()

            if ticket["ticket_status"] == "USED":
                message = "This ticket has already been used."
            else:
                message = "This ticket is not active and cannot be admitted."

            return render_template(
                "admission_result.html",
                success=False,
                message=message,
                ticket_code=ticket_code
            )

        # Check the booking and payment.
        if (
            ticket["booking_status"] != "CONFIRMED"
            or ticket["payment_status"] != "SUCCESSFUL"
        ):
            connection.rollback()

            return render_template(
                "admission_result.html",
                success=False,
                message="The booking or payment is not valid for admission.",
                ticket_code=ticket_code
            )

        # Prevent admission after the movie's scheduled start time.
        if not ticket["showtime_upcoming"]:
            connection.rollback()

            return render_template(
                "admission_result.html",
                success=False,
                message="This showtime has already started or passed.",
                ticket_code=ticket_code
            )

        # Mark the ticket as USED.
        cursor.execute(
            """
            UPDATE ticket
            SET ticket_status = 'USED'
            WHERE ticket_id = %s
              AND ticket_status = 'ACTIVE'
            """,
            (ticket["ticket_id"],)
        )

        if cursor.rowcount != 1:
            connection.rollback()

            return render_template(
                "admission_result.html",
                success=False,
                message="Ticket admission failed. It may already have been used.",
                ticket_code=ticket_code
            )

        connection.commit()

        return render_template(
            "admission_result.html",
            success=True,
            message="Customer admitted successfully. Ticket marked as USED.",
            ticket_code=ticket_code
        )

    except Error:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Ticket admission failed.")

        return "Unable to process ticket admission right now.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()



@app.route("/employee/search-booking", methods=["GET"])
def search_booking():
    employee_id = session.get("employee_id")

    if not employee_id:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Confirm that the employee account is still active.
        cursor.execute("""
            SELECT e.employee_id, u.account_status
            FROM employee e
            JOIN users u ON e.user_id = u.user_id
            WHERE e.employee_id = %s AND u.role = 'EMPLOYEE'
        """, (employee_id,))

        employee = cursor.fetchone()

        if not employee or employee["account_status"] != "ACTIVE":
            session.clear()
            return redirect(url_for("login"))

        # Read the booking reference entered in the dashboard.
        booking_id = request.args.get("booking_id", "").strip()

        if not booking_id.isdigit() or int(booking_id) < 1:
            return render_template(
                "employee_booking_result.html",
                booking=None,
                error="Please enter a valid booking reference."
            )

        # Retrieve the booking and its related information.
        cursor.execute("""
            SELECT
                b.booking_id,
                b.booking_date,
                b.total_amount,
                b.booking_status,

                c.name AS customer_name,
                c.email AS customer_email,
                c.phone AS customer_phone,

                m.title AS movie_title,
                m.genre AS movie_genre,
                m.duration AS movie_duration,

                st.show_date,
                st.start_time,
                st.end_time,

                sc.screen_name,

                ci.name AS cinema_name,
                ci.location AS cinema_location,

                GROUP_CONCAT(
                    DISTINCT CONCAT(s.seat_number, ' (', s.seat_type, ')')
                    ORDER BY s.seat_number
                    SEPARATOR ', '
                ) AS booked_seats,

                p.amount AS payment_amount,
                p.payment_date,
                p.payment_method,
                p.payment_status,
                p.transaction_reference,

                t.ticket_code,
                t.issue_date,
                t.ticket_status

            FROM booking b

            JOIN customer c
                ON b.customer_id = c.customer_id

            JOIN showtime st
                ON b.showtime_id = st.showtime_id

            JOIN movie m
                ON st.movie_id = m.movie_id

            JOIN screen sc
                ON st.screen_id = sc.screen_id

            JOIN cinema ci
                ON sc.cinema_id = ci.cinema_id

            LEFT JOIN booking_seat bs
                ON b.booking_id = bs.booking_id

            LEFT JOIN seat s
                ON bs.seat_id = s.seat_id

            LEFT JOIN payment p
                ON b.booking_id = p.booking_id

            LEFT JOIN ticket t
                ON b.booking_id = t.booking_id

            WHERE b.booking_id = %s

            GROUP BY
                b.booking_id,
                b.booking_date,
                b.total_amount,
                b.booking_status,
                c.name,
                c.email,
                c.phone,
                m.title,
                m.genre,
                m.duration,
                st.show_date,
                st.start_time,
                st.end_time,
                sc.screen_name,
                ci.name,
                ci.location,
                p.amount,
                p.payment_date,
                p.payment_method,
                p.payment_status,
                p.transaction_reference,
                t.ticket_code,
                t.issue_date,
                t.ticket_status

        """, (int(booking_id),))

        booking = cursor.fetchone()

        if not booking:
            return render_template(
                "employee_booking_result.html",
                booking=None,
                error=f"No booking was found with reference {booking_id}."
            )

        return render_template(
            "employee_booking_result.html",
            booking=booking,
            error=None
        )

    except Error:
        app.logger.exception("Unable to search for booking.")
        return "Unable to search for booking.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


@app.route("/manager/dashboard")
def manager_dashboard():

    # Ensure the user is logged in as a manager
    if "manager_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                m.manager_id,
                m.name,
                m.email,
                u.username,
                u.account_status

            FROM manager AS m

            INNER JOIN users AS u
                ON m.user_id = u.user_id

            WHERE m.manager_id = %s
              AND u.user_id = %s
              AND u.role = 'MANAGER'
              AND u.account_status = 'ACTIVE'

            LIMIT 1
        """, (
            session["manager_id"],
            session["user_id"]
        ))

        manager = cursor.fetchone()

        # Reject missing or inactive manager accounts
        if not manager:
            session.clear()
            return redirect(url_for("login"))

        return render_template(
            "manager_dashboard.html",
            manager=manager
        )

    except Exception:
        app.logger.exception("Manager dashboard failed.")
        return "Unable to load the manager dashboard. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/audit-logs")
def manager_audit_logs():

    # Ensure the user is logged in as an active manager
    if (
        "manager_id" not in session
        or "user_id" not in session
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        # Read search and filter parameters
        search = request.args.get("search", "").strip()
        selected_action = request.args.get("action", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1

        per_page = 20

        # Validate date filters
        if date_from:
            datetime.strptime(date_from, "%Y-%m-%d")

        if date_to:
            datetime.strptime(date_to, "%Y-%m-%d")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify the manager's account
        cursor.execute("""
            SELECT m.manager_id
            FROM manager AS m
            INNER JOIN users AS u
                ON m.user_id = u.user_id
            WHERE m.manager_id = %s
              AND u.user_id = %s
              AND u.role = 'MANAGER'
              AND u.account_status = 'ACTIVE'
            LIMIT 1
        """, (
            session["manager_id"],
            session["user_id"]
        ))

        manager = cursor.fetchone()

        if not manager:
            session.clear()
            return redirect(url_for("login"))

        # Retrieve available audit action types
        cursor.execute("""
            SELECT DISTINCT action
            FROM audit_log
            ORDER BY action ASC
        """)

        actions = cursor.fetchall()

        # Build the search and filter conditions
        conditions = []
        parameters = []

        if search:
            conditions.append("""
                (
                    CAST(a.log_id AS CHAR) LIKE %s
                    OR CAST(a.user_id AS CHAR) LIKE %s
                    OR a.action LIKE %s
                    OR a.description LIKE %s
                    OR u.username LIKE %s
                )
            """)

            search_value = f"%{search}%"
            parameters.extend([search_value] * 5)

        if selected_action:
            conditions.append("a.action = %s")
            parameters.append(selected_action)

        if date_from:
            conditions.append("DATE(a.timestamp) >= %s")
            parameters.append(date_from)

        if date_to:
            conditions.append("DATE(a.timestamp) <= %s")
            parameters.append(date_to)

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Count matching audit records
        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM audit_log AS a
            LEFT JOIN users AS u
                ON a.user_id = u.user_id
            {where_clause}
        """, tuple(parameters))

        total_logs = cursor.fetchone()["total"]

        total_pages = max(
            1,
            (total_logs + per_page - 1) // per_page
        )

        page = min(page, total_pages)
        offset = (page - 1) * per_page

        # Retrieve the current page of audit records
        cursor.execute(f"""
            SELECT
                a.log_id,
                a.user_id,
                u.username,
                a.action,
                a.description,
                a.timestamp
            FROM audit_log AS a
            LEFT JOIN users AS u
                ON a.user_id = u.user_id
            {where_clause}
            ORDER BY a.timestamp DESC, a.log_id DESC
            LIMIT %s OFFSET %s
        """, tuple(parameters + [per_page, offset]))

        logs = cursor.fetchall()

        return render_template(
            "manager_audit_logs.html",
            logs=logs,
            actions=actions,
            search=search,
            selected_action=selected_action,
            date_from=date_from,
            date_to=date_to,
            page=page,
            total_pages=total_pages,
            total_logs=total_logs
        )

    except ValueError:
        flash("Please provide valid date filters.", "error")
        return redirect(url_for("manager_audit_logs"))

    except Exception:
        app.logger.exception("Manager audit logs page failed.")
        return "Unable to load audit logs. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()




@app.route("/manager/support-requests")
def manager_support_requests():

    # Ensure the user is logged in as an active manager
    if (
        "manager_id" not in session
        or "user_id" not in session
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify the manager's account
        cursor.execute("""
            SELECT m.manager_id
            FROM manager AS m
            INNER JOIN users AS u
                ON m.user_id = u.user_id
            WHERE m.manager_id = %s
              AND u.user_id = %s
              AND u.role = 'MANAGER'
              AND u.account_status = 'ACTIVE'
            LIMIT 1
        """, (
            session["manager_id"],
            session["user_id"]
        ))

        manager = cursor.fetchone()

        if not manager:
            session.clear()
            return redirect(url_for("login"))

        # Retrieve all support requests
        cursor.execute("""
            SELECT
                sr.request_id,
                sr.customer_id,

                COALESCE(sr.sender_name, c.name) AS sender_name,
                COALESCE(sr.sender_email, c.email) AS sender_email,

                sr.subject,
                sr.status,
                sr.created_at

            FROM support_request AS sr

            LEFT JOIN customer AS c
                ON sr.customer_id = c.customer_id

            ORDER BY sr.created_at DESC, sr.request_id DESC
        """)

        support_requests = cursor.fetchall()

        return render_template(
            "manager_support_requests.html",
            support_requests=support_requests
        )

    except Exception:
        app.logger.exception("Manager support requests page failed.")
        return "Unable to load support requests. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/support-requests/<int:request_id>", methods=["GET", "POST"])
def manager_support_request_details(request_id):

    # Ensure the user is logged in as an active manager
    if (
        "manager_id" not in session
        or "user_id" not in session
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    valid_statuses = [
        "OPEN",
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED"
    ]

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify the manager's account
        cursor.execute("""
            SELECT m.manager_id
            FROM manager AS m
            INNER JOIN users AS u
                ON m.user_id = u.user_id
            WHERE m.manager_id = %s
              AND u.user_id = %s
              AND u.role = 'MANAGER'
              AND u.account_status = 'ACTIVE'
            LIMIT 1
        """, (
            session["manager_id"],
            session["user_id"]
        ))

        manager = cursor.fetchone()

        if not manager:
            session.clear()
            return redirect(url_for("login"))

        # Retrieve the selected support request
        cursor.execute("""
            SELECT
                sr.request_id,
                sr.customer_id,
                COALESCE(sr.sender_name, c.name) AS sender_name,
                COALESCE(sr.sender_email, c.email) AS sender_email,
                sr.subject,
                sr.description,
                sr.status,
                sr.created_at

            FROM support_request AS sr

            LEFT JOIN customer AS c
                ON sr.customer_id = c.customer_id

            WHERE sr.request_id = %s
            LIMIT 1
        """, (request_id,))

        support_request = cursor.fetchone()

        if not support_request:
            return "Support request not found.", 404

        # Process status updates
        if request.method == "POST":

            new_status = request.form.get("status", "").strip()

            if new_status not in valid_statuses:
                flash("Please select a valid request status.", "error")
                return redirect(url_for(
                    "manager_support_request_details",
                    request_id=request_id
                ))

            cursor.execute("""
                UPDATE support_request
                SET status = %s
                WHERE request_id = %s
            """, (new_status, request_id))

            connection.commit()

            flash("Support request status updated successfully.", "success")

            return redirect(url_for(
                "manager_support_request_details",
                request_id=request_id
            ))

        return render_template(
            "manager_support_request_details.html",
            support_request=support_request,
            valid_statuses=valid_statuses
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Manager support request details failed.")
        return "Unable to load the support request. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/manager/movies")
def manager_movies():

    # Ensure only authenticated managers can access this page
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                movie_id,
                title,
                genre,
                duration,
                release_date,
                rating
            FROM movie
            ORDER BY movie_id DESC
        """)

        movies = cursor.fetchall()

        return render_template(
            "manager_movies.html",
            movies=movies
        )

    except Exception:
        app.logger.exception("Manager movie list failed.")
        return "Unable to load movies. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()




@app.route("/manager/bookings")
def manager_bookings():

    # Ensure only authenticated managers can access this page.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    # Retrieve search and filter values from the URL.
    search = request.args.get("search", "").strip()
    booking_status = request.args.get("booking_status", "").strip()
    payment_status = request.args.get("payment_status", "").strip()

    # Validate filter values against the database ENUM options.
    valid_booking_statuses = [
        "PENDING", "CONFIRMED", "FAILED", "CANCELLED", "EXPIRED"
    ]

    valid_payment_statuses = [
        "PENDING", "SUCCESSFUL", "FAILED", "REFUNDED", "NOT_PAID"
    ]

    if booking_status not in valid_booking_statuses:
        booking_status = ""

    if payment_status not in valid_payment_statuses:
        payment_status = ""

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                b.booking_id,
                b.booking_date,
                b.total_amount,
                b.booking_status,

                c.customer_id,
                c.name AS customer_name,
                c.email AS customer_email,

                m.title AS movie_title,

                s.show_date,
                s.start_time,

                sc.screen_name,

                ci.name AS cinema_name,

                p.payment_status

            FROM booking b

            INNER JOIN customer c
                ON b.customer_id = c.customer_id

            INNER JOIN showtime s
                ON b.showtime_id = s.showtime_id

            INNER JOIN movie m
                ON s.movie_id = m.movie_id

            INNER JOIN screen sc
                ON s.screen_id = sc.screen_id

            INNER JOIN cinema ci
                ON sc.cinema_id = ci.cinema_id

            LEFT JOIN payment p
                ON b.booking_id = p.booking_id

            WHERE 1 = 1
        """

        params = []

        # Search by booking ID, customer name, email or movie title.
        if search:
            search_pattern = f"%{search}%"

            query += """
                AND (
                    CAST(b.booking_id AS CHAR) LIKE %s
                    OR c.name LIKE %s
                    OR c.email LIKE %s
                    OR m.title LIKE %s
                )
            """

            params.extend([
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern
            ])

        # Filter by booking status.
        if booking_status:
            query += " AND b.booking_status = %s"
            params.append(booking_status)

        # Filter by payment status.
        if payment_status == "NOT_PAID":
            query += " AND p.payment_id IS NULL"

        elif payment_status:
            query += " AND p.payment_status = %s"
            params.append(payment_status)

        query += " ORDER BY b.booking_date DESC"

        cursor.execute(query, params)

        bookings = cursor.fetchall()

        return render_template(
            "manager_bookings.html",
            bookings=bookings,
            search=search,
            booking_status=booking_status,
            payment_status=payment_status
        )

    except Exception:
        app.logger.exception("Manager booking list failed.")
        return "Unable to load bookings. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/customers")
def manager_customers():

    # Ensure only authenticated managers can access this page.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    # Retrieve search and account-status filter values.
    search = request.args.get("search", "").strip()
    account_status = request.args.get("account_status", "").strip()

    valid_statuses = ["ACTIVE", "INACTIVE", "SUSPENDED"]

    if account_status not in valid_statuses:
        account_status = ""

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                c.customer_id,
                c.name,
                c.email,
                c.phone,
                u.username,
                u.account_status

            FROM customer c

            INNER JOIN users u
                ON c.user_id = u.user_id

            WHERE 1 = 1
        """

        params = []

        # Search by customer ID, name, email, phone or username.
        if search:
            search_pattern = f"%{search}%"

            query += """
                AND (
                    CAST(c.customer_id AS CHAR) LIKE %s
                    OR c.name LIKE %s
                    OR c.email LIKE %s
                    OR c.phone LIKE %s
                    OR u.username LIKE %s
                )
            """

            params.extend([
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern
            ])

        # Filter by customer account status.
        if account_status:
            query += " AND u.account_status = %s"
            params.append(account_status)

        query += " ORDER BY c.customer_id DESC"

        cursor.execute(query, params)

        customers = cursor.fetchall()

        return render_template(
            "manager_customers.html",
            customers=customers,
            search=search,
            account_status=account_status
        )

    except Exception:
        app.logger.exception("Manager customer list failed.")
        return "Unable to load customers. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def edit_customer(customer_id):

    # Ensure only authenticated managers can access this page.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            connection.start_transaction()

        # Retrieve the customer and associated user account.
        query = """
            SELECT
                c.customer_id,
                c.user_id,
                c.name,
                c.email,
                c.phone,
                u.username,
                u.account_status

            FROM customer c

            INNER JOIN users u
                ON c.user_id = u.user_id

            WHERE c.customer_id = %s
        """

        if request.method == "POST":
            query += " FOR UPDATE"

        cursor.execute(query, (customer_id,))
        customer = cursor.fetchone()

        if customer is None:
            if request.method == "POST":
                connection.rollback()

            flash("Customer not found.", "error")
            return redirect(url_for("manager_customers"))

        if request.method == "POST":

            name = request.form.get("name", "").strip()
            # Preserve the original customer details for audit logging.
            old_name = customer["name"]
            old_email = customer["email"]
            old_phone = customer["phone"]
            old_username = customer["username"]
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            username = request.form.get("username", "").strip()

            # Preserve submitted values when validation fails.
            customer.update({
                "name": name,
                "email": email,
                "phone": phone,
                "username": username
            })

            if not name or not email or not username:
                connection.rollback()

                return render_template(
                    "manager_edit_customer.html",
                    customer=customer,
                    error="Please complete all required fields."
                ), 400

            if "@" not in email or "." not in email.split("@")[-1]:
                connection.rollback()

                return render_template(
                    "manager_edit_customer.html",
                    customer=customer,
                    error="Please enter a valid email address."
                ), 400

            # Check whether another customer already uses this email.
            cursor.execute("""
                SELECT customer_id
                FROM customer
                WHERE email = %s
                  AND customer_id != %s
                LIMIT 1
            """, (email, customer_id))

            duplicate_email = cursor.fetchone()

            if duplicate_email:
                connection.rollback()

                return render_template(
                    "manager_edit_customer.html",
                    customer=customer,
                    error="This email address is already registered."
                ), 400

            # Check whether another account already uses this username.
            cursor.execute("""
                SELECT user_id
                FROM users
                WHERE username = %s
                  AND user_id != %s
                LIMIT 1
            """, (username, customer["user_id"]))

            duplicate_username = cursor.fetchone()

            if duplicate_username:
                connection.rollback()

                return render_template(
                    "manager_edit_customer.html",
                    customer=customer,
                    error="This username is already taken."
                ), 400

            # Update customer details.
            cursor.execute("""
                UPDATE customer
                SET
                    name = %s,
                    email = %s,
                    phone = %s
                WHERE customer_id = %s
            """, (
                name,
                email,
                phone or None,
                customer_id
            ))

            # Update the associated login username.
            cursor.execute("""
                UPDATE users
                SET username = %s
                WHERE user_id = %s
            """, (
                username,
                customer["user_id"]
            ))

                        # Record the customer detail changes.
            changes = []

            if old_name != name:
                changes.append(f"name: {old_name} -> {name}")

            if old_email != email:
                changes.append(f"email: {old_email} -> {email}")

            if old_phone != (phone or None):
                changes.append(
                    f"phone: {old_phone or 'None'} -> {phone or 'None'}"
                )

            if old_username != username:
                changes.append(
                    f"username: {old_username} -> {username}"
                )

            if changes:
                record_audit_log(
                    cursor,
                    session["user_id"],
                    "UPDATE_CUSTOMER",
                    (
                        f"Manager updated customer #{customer_id}: "
                        + "; ".join(changes)
                    )
                )

            connection.commit()

            flash(
                f"Customer record for {name} was successfully updated.",
                "success"
            )

            return redirect(url_for("manager_customers"))

        return render_template(
            "manager_edit_customer.html",
            customer=customer
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Editing customer failed.")
        return "Unable to edit the customer. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route(
    "/manager/customers/<int:customer_id>/status",
    methods=["POST"]
)
def update_customer_status(customer_id):

    # Ensure only authenticated managers can manage customer accounts.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        new_status = request.form.get("account_status", "").strip()

        valid_statuses = ["ACTIVE", "INACTIVE", "SUSPENDED"]

        if new_status not in valid_statuses:
            flash("Invalid customer account status.", "error")
            return redirect(url_for("manager_customers"))

        connection = get_db_connection()
        connection.start_transaction()

        cursor = connection.cursor(dictionary=True)

        # Retrieve and lock the customer's associated account.
        cursor.execute("""
            SELECT
                u.user_id,
                u.account_status

            FROM customer c

            INNER JOIN users u
                ON c.user_id = u.user_id

            WHERE c.customer_id = %s
            FOR UPDATE
        """, (customer_id,))

        customer = cursor.fetchone()

        if customer is None:
            connection.rollback()
            flash("Customer not found.", "error")
            return redirect(url_for("manager_customers"))

        old_status = customer["account_status"]

        if old_status == new_status:
            connection.rollback()

            flash(
                f"Customer account is already {new_status}.",
                "error"
            )

            return redirect(url_for("manager_customers"))

        # Update the customer's account status.
        cursor.execute("""
            UPDATE users
            SET account_status = %s
            WHERE user_id = %s
        """, (
            new_status,
            customer["user_id"]
        ))

        
        # Record the customer account status change.
        record_audit_log(
            cursor,
            session["user_id"],
            "UPDATE_CUSTOMER_STATUS",
            (
                f"Manager changed customer #{customer_id} "
                f"account status from {old_status} to {new_status}."
            )
        )

        connection.commit()

        flash(
            f"Customer account status successfully changed "
            f"from {old_status} to {new_status}.",
            "success"
        )


    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Updating customer account status failed.")

        flash(
            "Unable to update the customer account status. Please try again.",
            "error"
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return redirect(url_for("manager_customers"))


@app.route("/manager/reports")
def manager_reports():

    # Manager authentication
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    # Validate supplied dates.
    try:
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")

        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        if start_date and end_date and start_date > end_date:
            flash("The start date cannot be after the end date.", "error")
            return redirect(url_for("manager_reports"))

    except ValueError:
        flash("Please provide valid dates.", "error")
        return redirect(url_for("manager_reports"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # --------------------------------
        # BOOKING STATISTICS
        # --------------------------------

        

        booking_query = """
            SELECT
                COUNT(*) AS total_bookings,

                SUM(CASE WHEN b.booking_status = 'CONFIRMED'
                    THEN 1 ELSE 0 END) AS confirmed_bookings,

                SUM(CASE WHEN b.booking_status = 'PENDING'
                    THEN 1 ELSE 0 END) AS pending_bookings,

                SUM(CASE WHEN b.booking_status = 'CANCELLED'
                    THEN 1 ELSE 0 END) AS cancelled_bookings,

                SUM(CASE WHEN b.booking_status = 'FAILED'
                    THEN 1 ELSE 0 END) AS failed_bookings,

                SUM(CASE WHEN b.booking_status = 'EXPIRED'
                    THEN 1 ELSE 0 END) AS expired_bookings,

                SUM(CASE WHEN p.payment_id IS NULL
                    THEN 1 ELSE 0 END) AS unpaid_bookings

            FROM booking b

            LEFT JOIN payment p
                ON b.booking_id = p.booking_id

            WHERE 1 = 1
        """

        booking_params = []

        if start_date:
            booking_query += " AND b.booking_date >= %s"
            booking_params.append(start_date)

        if end_date:
            booking_query += """
                AND b.booking_date < DATE_ADD(%s, INTERVAL 1 DAY)
            """
            booking_params.append(end_date)

        cursor.execute(booking_query, booking_params)
        booking_reports = cursor.fetchone()

        # --------------------------------
        # PAYMENT AND REVENUE STATISTICS
        # --------------------------------

        payment_query = """
            SELECT
                SUM(CASE WHEN payment_status = 'SUCCESSFUL'
                    THEN 1 ELSE 0 END) AS successful_payments,

                SUM(CASE WHEN payment_status = 'PENDING'
                    THEN 1 ELSE 0 END) AS pending_payments,

                SUM(CASE WHEN payment_status = 'FAILED'
                    THEN 1 ELSE 0 END) AS failed_payments,

                SUM(CASE WHEN payment_status = 'REFUNDED'
                    THEN 1 ELSE 0 END) AS refunded_payments,

                COALESCE(
                    SUM(CASE WHEN payment_status = 'SUCCESSFUL'
                        THEN amount ELSE 0 END), 0
                ) AS total_revenue,

                COALESCE(
                    SUM(CASE WHEN payment_status = 'REFUNDED'
                        THEN amount ELSE 0 END), 0
                ) AS total_refunded

            FROM payment
            WHERE 1 = 1
        """

        payment_params = []

        if start_date:
            payment_query += " AND payment_date >= %s"
            payment_params.append(start_date)

        if end_date:
            payment_query += """
                AND payment_date < DATE_ADD(%s, INTERVAL 1 DAY)
            """
            payment_params.append(end_date)

        cursor.execute(payment_query, payment_params)
        payment_reports = cursor.fetchone()

        # Combine both result sets.
        reports = {**booking_reports, **payment_reports}

        return render_template(
            "manager_reports.html",
            reports=reports,
            start_date=start_date,
            end_date=end_date
        )

    except Exception:
        app.logger.exception("Manager reports loading failed.")
        return "Unable to load reports. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/manager/bookings/<int:booking_id>")
def manager_booking_details(booking_id):

    # Ensure only authenticated managers can access this page.
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the main booking information.
        cursor.execute("""
            SELECT
                b.booking_id,
                b.booking_date,
                b.total_amount,
                b.booking_status,

                c.customer_id,
                c.name AS customer_name,
                c.email AS customer_email,
                c.phone AS customer_phone,

                m.title AS movie_title,
                m.genre,
                m.duration,

                s.show_date,
                s.start_time,
                s.end_time,

                sc.screen_name,
                sc.capacity,

                ci.name AS cinema_name,
                ci.location AS cinema_location,

                p.payment_id,
                p.amount AS payment_amount,
                p.payment_date,
                p.payment_method,
                p.payment_status,
                p.transaction_reference,

                t.ticket_id,
                t.ticket_code,
                t.issue_date,
                t.ticket_status

            FROM booking b

            INNER JOIN customer c
                ON b.customer_id = c.customer_id

            INNER JOIN showtime s
                ON b.showtime_id = s.showtime_id

            INNER JOIN movie m
                ON s.movie_id = m.movie_id

            INNER JOIN screen sc
                ON s.screen_id = sc.screen_id

            INNER JOIN cinema ci
                ON sc.cinema_id = ci.cinema_id

            LEFT JOIN payment p
                ON b.booking_id = p.booking_id

            LEFT JOIN ticket t
                ON b.booking_id = t.booking_id

            WHERE b.booking_id = %s
        """, (booking_id,))

        booking = cursor.fetchone()

        if booking is None:
            return "Booking not found.", 404

        # Retrieve the seats associated with this booking.
        cursor.execute("""
            SELECT
                se.seat_number,
                se.seat_type

            FROM booking_seat bs

            INNER JOIN seat se
                ON bs.seat_id = se.seat_id

            WHERE bs.booking_id = %s

            ORDER BY se.seat_number
        """, (booking_id,))

        seats = cursor.fetchall()

        # Retrieve reservation records separately because
        # one booking may have multiple reservation records.
        cursor.execute("""
            SELECT
                reservation_id,
                reservation_date,
                reservation_status,
                expiry_time

            FROM reservation

            WHERE booking_id = %s

            ORDER BY reservation_date DESC
        """, (booking_id,))

        reservations = cursor.fetchall()

        return render_template(
            "manager_booking_details.html",
            booking=booking,
            seats=seats,
            reservations=reservations
        )

    except Exception:
        app.logger.exception("Manager booking details failed.")
        return "Unable to load booking details. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/manager/movies/add", methods=["GET", "POST"])
def add_movie():

    # Ensure only authenticated managers can access this page
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        genre = request.form.get("genre", "").strip()
        duration = request.form.get("duration", "").strip()
        release_date = request.form.get("release_date", "").strip()
        description = request.form.get("description", "").strip()
        rating = request.form.get("rating", "").strip()

        # Validate required fields
        if not title or not genre or not duration:
            return render_template(
                "manager_add_movie.html",
                error="Please complete all required fields."
            ), 400

        # Validate movie duration
        try:
            duration = int(duration)

            if duration <= 0:
                raise ValueError

        except ValueError:
            return render_template(
                "manager_add_movie.html",
                error="Duration must be a positive whole number."
            ), 400

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO movie (
                    title,
                    genre,
                    duration,
                    release_date,
                    description,
                    rating
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                title,
                genre,
                duration,
                release_date or None,
                description or None,
                rating or None
            ))

                        # Retrieve the ID of the newly added movie.
            movie_id = cursor.lastrowid

            # Record the movie creation.
            record_audit_log(
                cursor,
                session["user_id"],
                "ADD_MOVIE",
                (
                    f"Manager added movie #{movie_id}: "
                    f"{title} (Genre: {genre}, Duration: {duration} minutes)."
                )
            )

            connection.commit()

            return redirect(url_for("manager_movies"))
        except Exception:
            if connection is not None:
                connection.rollback()

            app.logger.exception("Adding movie failed.")

            return render_template(
                "manager_add_movie.html",
                error="Unable to add the movie. Please try again."
            ), 500

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("manager_add_movie.html")


@app.route("/manager/movies/<int:movie_id>/edit", methods=["GET", "POST"])
def edit_movie(movie_id):

    # Ensure only authenticated managers can access this page
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the existing movie
        cursor.execute("""
            SELECT
                movie_id,
                title,
                genre,
                duration,
                release_date,
                description,
                rating
            FROM movie
            WHERE movie_id = %s
        """, (movie_id,))

        movie = cursor.fetchone()

        if movie is None:
            return "Movie not found.", 404

        if request.method == "POST":

            title = request.form.get("title", "").strip()
             # Preserve original movie details for audit logging.
            old_title = movie["title"]
            old_genre = movie["genre"]
            old_duration = movie["duration"]
            old_release_date = movie["release_date"]
            old_description = movie["description"]
            old_rating = movie["rating"]
            genre = request.form.get("genre", "").strip()
            duration = request.form.get("duration", "").strip()
            release_date = request.form.get("release_date", "").strip()
            description = request.form.get("description", "").strip()
            rating = request.form.get("rating", "").strip()

            if not title or not genre or not duration:
                return render_template(
                    "manager_edit_movie.html",
                    movie=movie,
                    error="Please complete all required fields."
                ), 400

            try:
                duration = int(duration)
                if duration <= 0:
                    raise ValueError
            except ValueError:
                return render_template(
                    "manager_edit_movie.html",
                    movie=movie,
                    error="Duration must be a positive whole number."
                ), 400

            if rating:
                try:
                    rating = float(rating)
                    if not 0 <= rating <= 10:
                        raise ValueError
                except ValueError:
                    return render_template(
                        "manager_edit_movie.html",
                        movie=movie,
                        error="Rating must be a number between 0 and 10."
                    ), 400
            else:
                rating = None

            cursor.execute("""
                UPDATE movie
                SET
                    title = %s,
                    genre = %s,
                    duration = %s,
                    release_date = %s,
                    description = %s,
                    rating = %s
                WHERE movie_id = %s
            """, (
                title,
                genre,
                duration,
                release_date or None,
                description or None,
                rating,
                movie_id
            ))

                        # Record the movie details that were changed.
            changes = []

            if old_title != title:
                changes.append(f"title: {old_title} -> {title}")

            if old_genre != genre:
                changes.append(f"genre: {old_genre} -> {genre}")

            if old_duration != duration:
                changes.append(
                    f"duration: {old_duration} -> {duration} minutes"
                )

            if old_release_date != (release_date or None):
                changes.append(
                    f"release date: {old_release_date} -> "
                    f"{release_date or 'None'}"
                )

            if old_description != (description or None):
                changes.append("description updated")

            if old_rating != rating:
                changes.append(
                    f"rating: {old_rating} -> {rating}"
                )

            if changes:
                record_audit_log(
                    cursor,
                    session["user_id"],
                    "UPDATE_MOVIE",
                    (
                        f"Manager updated movie #{movie_id}: "
                        + "; ".join(changes)
                    )
                )

            connection.commit()

            return redirect(url_for("manager_movies"))
        return render_template(
            "manager_edit_movie.html",
            movie=movie
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Editing movie failed.")
        return "Unable to edit the movie. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()
            

@app.route("/manager/movies/<int:movie_id>/delete", methods=["POST"])
def delete_movie(movie_id):

    # Ensure only authenticated managers can delete movies
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()

        cursor = connection.cursor(dictionary=True)

        # Check whether the movie exists and lock its record
        cursor.execute("""
            SELECT movie_id, title
            FROM movie
            WHERE movie_id = %s
            FOR UPDATE
        """, (movie_id,))

        movie = cursor.fetchone()

        if movie is None:
            connection.rollback()
            flash("Movie not found.", "error")
            return redirect(url_for("manager_movies"))

        # Check whether the movie has associated showtimes
        cursor.execute("""
            SELECT showtime_id
            FROM showtime
            WHERE movie_id = %s
            LIMIT 1
        """, (movie_id,))

        showtime = cursor.fetchone()

        if showtime is not None:
            connection.rollback()
            flash(
                "This movie cannot be deleted because it has "
                "associated showtimes.",
                "error"
            )
            return redirect(url_for("manager_movies"))

        # Delete the movie only if it has no associated showtimes
        cursor.execute("""
            DELETE FROM movie
            WHERE movie_id = %s
        """, (movie_id,))

        connection.commit()

                # Record the movie deletion before committing the transaction.
        record_audit_log(
            cursor,
            session["user_id"],
            "DELETE_MOVIE",
            (
                f"Manager deleted movie #{movie_id}: "
                f"{movie['title']}."
            )
        )

        connection.commit()

        flash(
            f"{movie['title']} was successfully deleted.",
            "success"
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Deleting movie failed.")
        flash("Unable to delete the movie. Please try again.", "error")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return redirect(url_for("manager_movies"))



@app.route("/manager/showtimes")
def manager_showtimes():

    # Ensure only authenticated managers can access this page
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                s.showtime_id,
                m.title AS movie_title,
                c.name AS cinema_name,
                c.location AS cinema_location,
                sc.screen_name,
                s.show_date,
                s.start_time,
                s.end_time
            FROM showtime AS s
            JOIN movie AS m
                ON s.movie_id = m.movie_id
            JOIN screen AS sc
                ON s.screen_id = sc.screen_id
            JOIN cinema AS c
                ON sc.cinema_id = c.cinema_id
            ORDER BY
                s.show_date DESC,
                s.start_time ASC
        """)

        showtimes = cursor.fetchall()

        return render_template(
            "manager_showtimes.html",
            showtimes=showtimes
        )

    except Exception:
        app.logger.exception("Manager showtime list failed.")
        return "Unable to load showtimes. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

@app.route("/manager/showtimes/add")
def add_showtime():

    # Ensure only authenticated managers can access this page
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve available movies
        cursor.execute("""
            SELECT movie_id, title, duration
            FROM movie
            ORDER BY title ASC
        """)
        movies = cursor.fetchall()

        # Retrieve available cinemas
        cursor.execute("""
            SELECT cinema_id, name, location
            FROM cinema
            ORDER BY name ASC
        """)
        cinemas = cursor.fetchall()

        # Retrieve screens together with their cinema details
        cursor.execute("""
            SELECT
                sc.screen_id,
                sc.screen_name,
                sc.capacity,
                c.cinema_id,
                c.name AS cinema_name
            FROM screen AS sc
            JOIN cinema AS c
                ON sc.cinema_id = c.cinema_id
            ORDER BY c.name ASC, sc.screen_name ASC
        """)
        screens = cursor.fetchall()

        return render_template(
            "add_showtime.html",
            movies=movies,
            cinemas=cinemas,
            screens=screens
        )

    except Exception:
        app.logger.exception("Add showtime page failed to load.")
        return "Unable to load the showtime form. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/manager/showtimes/add", methods=["POST"])
def save_showtime():

    # Ensure only authenticated managers can save showtimes
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        # Retrieve submitted form values
        movie_id = int(request.form.get("movie_id", ""))
        cinema_id = int(request.form.get("cinema_id", ""))
        screen_id = int(request.form.get("screen_id", ""))

        show_date = datetime.strptime(
            request.form.get("show_date", ""),
            "%Y-%m-%d"
        ).date()

        start_time = datetime.strptime(
            request.form.get("start_time", ""),
            "%H:%M"
        ).time()

        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Begin transaction
        connection.start_transaction()

        # Retrieve movie duration
        cursor.execute("""
            SELECT duration
            FROM movie
            WHERE movie_id = %s
        """, (movie_id,))

        movie = cursor.fetchone()

        if not movie or movie["duration"] <= 0:
            connection.rollback()
            flash("Please select a valid movie.", "error")
            return redirect(url_for("add_showtime"))

        # Calculate the screening end time on the server
        start_datetime = datetime.combine(show_date, start_time)

        end_datetime = start_datetime + timedelta(
            minutes=movie["duration"]
        )

        # Keep screenings within the same calendar day
        if end_datetime.date() != show_date:
            connection.rollback()
            flash(
                "This screening would end after midnight. "
                "Please select an earlier starting time.",
                "error"
            )
            return redirect(url_for("add_showtime"))

        end_time = end_datetime.time()

        # Lock the selected screen and verify its cinema
        cursor.execute("""
            SELECT screen_id
            FROM screen
            WHERE screen_id = %s
              AND cinema_id = %s
            FOR UPDATE
        """, (screen_id, cinema_id))

        screen = cursor.fetchone()

        if not screen:
            connection.rollback()
            flash(
                "The selected screen does not belong to that cinema.",
                "error"
            )
            return redirect(url_for("add_showtime"))

        # Check whether another screening overlaps on this screen
        

        # Check for overlapping screenings and insufficient turnaround time
        cursor.execute("""
            SELECT showtime_id
            FROM showtime
            WHERE screen_id = %s
              AND show_date = %s
              AND start_time < ADDTIME(%s, '00:30:00')
              AND ADDTIME(end_time, '00:30:00') > %s
            LIMIT 1
        """, (
            screen_id,
            show_date,
            end_time,
            start_time
        ))

        conflict = cursor.fetchone()

        if conflict:
            connection.rollback()
            flash(
                "This screen already has a screening "
                "scheduled during that time.",
                "error"
            )
            return redirect(url_for("add_showtime"))

        # Insert the new screening
        cursor.execute("""
            INSERT INTO showtime (
                movie_id,
                screen_id,
                show_date,
                start_time,
                end_time
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            movie_id,
            screen_id,
            show_date,
            start_time,
            end_time
        ))

        connection.commit()

                # Retrieve the ID of the newly created showtime.
        showtime_id = cursor.lastrowid

        # Record the showtime creation.
        record_audit_log(
            cursor,
            session["user_id"],
            "ADD_SHOWTIME",
            (
                f"Manager scheduled showtime #{showtime_id}: "
                f"Movie #{movie_id}, Screen #{screen_id}, "
                f"Date: {show_date}, "
                f"Time: {start_time} - {end_time}."
            )
        )

        connection.commit()

        flash(
            "Showtime scheduled successfully!",
            "success"
        )

        return redirect(url_for("manager_showtimes"))

    except (ValueError, TypeError):
        if connection is not None:
            connection.rollback()

        flash(
            "Please provide valid movie, cinema, screen, date and time details.",
            "error"
        )

        return redirect(url_for("add_showtime"))

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Saving showtime failed.")

        flash(
            "Unable to save the showtime. Please try again.",
            "error"
        )

        return redirect(url_for("add_showtime"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

@app.route("/manager/showtimes/<int:showtime_id>/edit")
def edit_showtime(showtime_id):

    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the selected showtime
        cursor.execute("""
            SELECT
                s.showtime_id,
                s.movie_id,
                s.screen_id,
                sc.cinema_id,
                s.show_date,
                s.start_time,
                s.end_time
            FROM showtime AS s
            JOIN screen AS sc
                ON s.screen_id = sc.screen_id
            WHERE s.showtime_id = %s
        """, (showtime_id,))

        showtime = cursor.fetchone()

        if not showtime:
            return "Showtime not found.", 404

        # Retrieve movies
        cursor.execute("""
            SELECT movie_id, title, duration
            FROM movie
            ORDER BY title ASC
        """)
        movies = cursor.fetchall()

        # Retrieve cinemas
        cursor.execute("""
            SELECT cinema_id, name, location
            FROM cinema
            ORDER BY name ASC
        """)
        cinemas = cursor.fetchall()

        # Retrieve screens and their cinemas
        cursor.execute("""
            SELECT
                sc.screen_id,
                sc.screen_name,
                sc.capacity,
                sc.cinema_id,
                c.name AS cinema_name
            FROM screen AS sc
            JOIN cinema AS c
                ON sc.cinema_id = c.cinema_id
            ORDER BY c.name, sc.screen_name
        """)
        screens = cursor.fetchall()

        return render_template(
            "edit_showtime.html",
            showtime=showtime,
            movies=movies,
            cinemas=cinemas,
            screens=screens
        )

    except Exception:
        app.logger.exception("Edit showtime page failed.")
        return "Unable to load showtime. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/manager/showtimes/<int:showtime_id>/update", methods=["POST"])
def update_showtime(showtime_id):

    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        movie_id = int(request.form.get("movie_id", ""))
        cinema_id = int(request.form.get("cinema_id", ""))
        screen_id = int(request.form.get("screen_id", ""))

        show_date = datetime.strptime(
            request.form.get("show_date", ""),
            "%Y-%m-%d"
        ).date()

        start_time = datetime.strptime(
            request.form.get("start_time", ""),
            "%H:%M"
        ).time()

        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

                # Lock and retrieve the existing showtime details.
        cursor.execute("""
            SELECT
                showtime_id,
                movie_id,
                screen_id,
                show_date,
                start_time,
                end_time
            FROM showtime
            WHERE showtime_id = %s
            FOR UPDATE
        """, (showtime_id,))

        existing_showtime = cursor.fetchone()

        if not existing_showtime:
            connection.rollback()
            flash("Showtime not found.", "error")
            return redirect(url_for("manager_showtimes"))

        # Retrieve movie duration
        cursor.execute("""
            SELECT duration
            FROM movie
            WHERE movie_id = %s
        """, (movie_id,))

        movie = cursor.fetchone()

        if not movie:
            connection.rollback()
            flash("Please select a valid movie.", "error")
            return redirect(url_for("edit_showtime", showtime_id=showtime_id))

        duration = movie["duration"]

        end_datetime = datetime.combine(
            show_date,
            start_time
        ) + timedelta(minutes=duration)

        # Prevent screenings from crossing midnight
        if end_datetime.date() != show_date:
            connection.rollback()
            flash(
                "Showtime cannot extend past midnight.",
                "error"
            )
            return redirect(url_for("edit_showtime", showtime_id=showtime_id))

        end_time = end_datetime.time()

        # Lock and validate the selected screen
        cursor.execute("""
            SELECT screen_id
            FROM screen
            WHERE screen_id = %s
              AND cinema_id = %s
            FOR UPDATE
        """, (screen_id, cinema_id))

        valid_screen = cursor.fetchone()

        if not valid_screen:
            connection.rollback()
            flash(
                "The selected screen does not belong to this cinema.",
                "error"
            )
            return redirect(url_for("edit_showtime", showtime_id=showtime_id))

        # Check for conflicts, excluding the showtime being edited
        cursor.execute("""
            SELECT showtime_id
            FROM showtime
            WHERE screen_id = %s
              AND show_date = %s
              AND showtime_id != %s
              AND start_time < ADDTIME(%s, '00:30:00')
              AND ADDTIME(end_time, '00:30:00') > %s
            LIMIT 1
        """, (
            screen_id,
            show_date,
            showtime_id,
            end_time,
            start_time
        ))

        conflict = cursor.fetchone()

        if conflict:
            connection.rollback()
            flash(
                "Scheduling conflict. Ensure at least 30 minutes between screenings on the same screen.",
                "error"
            )
            return redirect(url_for("edit_showtime", showtime_id=showtime_id))

        # Update the existing screening
        cursor.execute("""
            UPDATE showtime
            SET movie_id = %s,
                screen_id = %s,
                show_date = %s,
                start_time = %s,
                end_time = %s
            WHERE showtime_id = %s
        """, (
            movie_id,
            screen_id,
            show_date,
            start_time,
            end_time,
            showtime_id
        ))
        # Record the showtime details that were changed.
        changes = []

        if existing_showtime["movie_id"] != movie_id:
            changes.append(
                f"movie: #{existing_showtime['movie_id']} -> #{movie_id}"
            )

        if existing_showtime["screen_id"] != screen_id:
            changes.append(
                f"screen: #{existing_showtime['screen_id']} -> #{screen_id}"
            )

        if str(existing_showtime["show_date"]) != str(show_date):
            changes.append(
                f"date: {existing_showtime['show_date']} -> {show_date}"
            )

        if str(existing_showtime["start_time"]) != str(start_time):
            changes.append(
                f"start time: {existing_showtime['start_time']} -> {start_time}"
            )

        if str(existing_showtime["end_time"]) != str(end_time):
            changes.append(
                f"end time: {existing_showtime['end_time']} -> {end_time}"
            )

        if changes:
            record_audit_log(
                cursor,
                session["user_id"],
                "UPDATE_SHOWTIME",
                (
                    f"Manager updated showtime #{showtime_id}: "
                    + "; ".join(changes)
                )
            )

        connection.commit()

        flash("Showtime updated successfully.", "success")
        return redirect(url_for("manager_showtimes"))

    except (ValueError, TypeError):
        if connection is not None:
            connection.rollback()

        flash("Please provide valid showtime details.", "error")
        return redirect(url_for("edit_showtime", showtime_id=showtime_id))

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Showtime update failed.")
        return "Unable to update showtime. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route(
    "/manager/showtimes/<int:showtime_id>/delete",
    methods=["POST"]
)
def delete_showtime(showtime_id):

    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

                # Lock and retrieve the selected showtime details
        cursor.execute("""
            SELECT
                showtime_id,
                movie_id,
                screen_id,
                show_date,
                start_time,
                end_time
            FROM showtime
            WHERE showtime_id = %s
            FOR UPDATE
        """, (showtime_id,))
        showtime = cursor.fetchone()

        if not showtime:
            connection.rollback()
            flash("Showtime not found.", "error")
            return redirect(url_for("manager_showtimes"))

        # Check for existing bookings
        cursor.execute("""
            SELECT booking_id
            FROM booking
            WHERE showtime_id = %s
            LIMIT 1
        """, (showtime_id,))

        booking = cursor.fetchone()

        # Check for existing reservations
        cursor.execute("""
            SELECT reservation_id
            FROM reservation
            WHERE booking_id IN (
                SELECT booking_id
                FROM booking
                WHERE showtime_id = %s
            )
            LIMIT 1
        """, (showtime_id,))

        reservation = cursor.fetchone()

        if booking or reservation:
            connection.rollback()
            flash(
                "This showtime cannot be deleted because it has associated bookings or reservations.",
                "error"
            )
            return redirect(url_for("manager_showtimes"))

                # Record the showtime deletion
        record_audit_log(
            cursor,
            session["user_id"],
            "DELETE_SHOWTIME",
            (
                f"Manager deleted showtime #{showtime_id}: "
                f"Movie #{showtime['movie_id']}, "
                f"Screen #{showtime['screen_id']}, "
                f"Date: {showtime['show_date']}, "
                f"Time: {showtime['start_time']} - "
                f"{showtime['end_time']}."
            )
        )

        # Delete the showtime
        cursor.execute("""
            DELETE FROM showtime
            WHERE showtime_id = %s
        """, (showtime_id,))

        connection.commit()

        flash("Showtime deleted successfully.", "success")
        return redirect(url_for("manager_showtimes"))

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Showtime deletion failed.")
        return "Unable to delete showtime. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/cinemas")
def manager_cinemas():
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                cinema_id,
                name,
                location
            FROM cinema
            ORDER BY cinema_id ASC
        """)
        cinemas = cursor.fetchall()

        cursor.execute("""
            SELECT
                screen_id,
                cinema_id,
                screen_name,
                capacity
            FROM screen
            ORDER BY cinema_id ASC, screen_id ASC
        """)
        screens = cursor.fetchall()

        return render_template(
            "manager_cinemas.html",
            cinemas=cinemas,
            screens=screens
        )

    except Exception:
        app.logger.exception("Cinema management page failed.")
        return "Unable to load cinema information. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/manager/cinemas/screens/add", methods=["GET", "POST"])
def add_screen():
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            cinema_id = request.form.get("cinema_id", "").strip()
            screen_name = request.form.get("screen_name", "").strip()
            capacity_value = request.form.get("capacity", "").strip()

            try:
                cinema_id = int(cinema_id)
                capacity = int(capacity_value)

                if (
                    cinema_id <= 0
                    or capacity < 5
                    or capacity % 5 != 0
                     or not screen_name
                    ):
                        raise ValueError

            except ValueError:
                flash(
                    "Please provide a valid cinema, screen name and capacity.",
                    "error"
                )
                return redirect(url_for("add_screen"))

            cursor.execute("""
                SELECT cinema_id
                FROM cinema
                WHERE cinema_id = %s
            """, (cinema_id,))

            cinema = cursor.fetchone()

            if not cinema:
                flash("The selected cinema does not exist.", "error")
                return redirect(url_for("add_screen"))

            cursor.execute("""
                SELECT screen_id
                FROM screen
                WHERE cinema_id = %s
                  AND screen_name = %s
                LIMIT 1
            """, (cinema_id, screen_name))

            existing_screen = cursor.fetchone()

            if existing_screen:
                flash(
                    "A screen with that name already exists in this cinema.",
                    "error"
                )
                return redirect(url_for("add_screen"))

            

            # Use the existing active database transaction.
            cursor.execute("""
                INSERT INTO screen (
                    cinema_id,
                    screen_name,
                    capacity
                )
                VALUES (%s, %s, %s)
            """, (cinema_id, screen_name, capacity))

            new_screen_id = cursor.lastrowid

            # Calculate the seating layout.
            row_count = capacity // 5

            # Allocate approximately the central third of rows to VIP.
            vip_row_count = max(1, (row_count + 2) // 3)

            # Calculate the starting and ending VIP rows.
            vip_start_row = (row_count - vip_row_count) // 2
            vip_end_row = vip_start_row + vip_row_count

            seat_records = []

            for seat_index in range(capacity):
                row_index = seat_index // 5

                # Generate alphabetical row labels.
                row_number = row_index
                row_label = ""

                while row_number >= 0:
                    row_label = chr(row_number % 26 + 65) + row_label
                    row_number = row_number // 26 - 1

                seat_position = (seat_index % 5) + 1
                seat_number = f"{row_label}{seat_position}"

                # Assign VIP to central positions in the VIP rows.
                if (
                    vip_start_row <= row_index < vip_end_row
                    and seat_position in (2, 3, 4)
                ):
                    seat_type = "VIP"
                else:
                    seat_type = "STANDARD"

                seat_records.append((
                    new_screen_id,
                    seat_number,
                    seat_type,
                    "AVAILABLE"
                ))

            # Insert all generated seats.
            cursor.executemany("""
                INSERT INTO seat (
                    screen_id,
                    seat_number,
                    seat_type,
                    status
                )
                VALUES (%s, %s, %s, %s)
            """, seat_records)

            connection.commit()

            flash("Screen registered successfully.", "success")
            return redirect(url_for("manager_cinemas"))

        cursor.execute("""
            SELECT cinema_id, name, location
            FROM cinema
            ORDER BY cinema_id ASC
        """)

        cinemas = cursor.fetchall()

        return render_template(
            "add_screen.html",
            cinemas=cinemas
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Adding cinema screen failed.")
        return "Unable to register the screen. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()




@app.route("/manager/cinemas/screens/<int:screen_id>/edit", methods=["GET", "POST"])
def edit_screen(screen_id):
    if (
        "manager_id" not in session
        or session.get("manager_role") != "MANAGER"
    ):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the screen.
        cursor.execute("""
            SELECT screen_id, cinema_id, screen_name, capacity
            FROM screen
            WHERE screen_id = %s
        """, (screen_id,))

        screen = cursor.fetchone()

        if not screen:
            flash("Screen not found.", "error")
            return redirect(url_for("manager_cinemas"))

        if request.method == "POST":
            screen_name = request.form.get("screen_name", "").strip()
            capacity_value = request.form.get("capacity", "").strip()

            # Validate submitted information.
            try:
                capacity = int(capacity_value)

                if (
                    not screen_name
                    or capacity < 5
                    or capacity % 5 != 0
                ):
                    raise ValueError

            except ValueError:
                flash(
                    "Please provide a valid screen name and capacity.",
                    "error"
                )
                return redirect(
                    url_for("edit_screen", screen_id=screen_id)
                )

            # Check for duplicate screen names.
            cursor.execute("""
                SELECT screen_id
                FROM screen
                WHERE cinema_id = %s
                  AND screen_name = %s
                  AND screen_id != %s
                LIMIT 1
            """, (
                screen["cinema_id"],
                screen_name,
                screen_id
            ))

            if cursor.fetchone():
                flash(
                    "Another screen already uses that name in this cinema.",
                    "error"
                )
                return redirect(
                    url_for("edit_screen", screen_id=screen_id)
                )

            old_capacity = screen["capacity"]

            # Check dependencies only when capacity changes.
            if capacity != old_capacity:

                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM showtime
                    WHERE screen_id = %s
                """, (screen_id,))

                showtime_count = cursor.fetchone()["total"]

                if showtime_count > 0:
                    flash(
                        "Capacity cannot be changed because this screen "
                        "has scheduled showtimes.",
                        "error"
                    )
                    return redirect(
                        url_for("edit_screen", screen_id=screen_id)
                    )

                # Check whether any seats have booking records.
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM booking_seat bs
                    INNER JOIN seat s
                        ON bs.seat_id = s.seat_id
                    WHERE s.screen_id = %s
                """, (screen_id,))

                booked_seat_count = cursor.fetchone()["total"]

                if booked_seat_count > 0:
                    flash(
                        "Capacity cannot be changed because this screen "
                        "has seats associated with booking records.",
                        "error"
                    )
                    return redirect(
                        url_for("edit_screen", screen_id=screen_id)
                    )

            # Update screen information.
            cursor.execute("""
                UPDATE screen
                SET screen_name = %s,
                    capacity = %s
                WHERE screen_id = %s
            """, (screen_name, capacity, screen_id))

            # Regenerate the complete seat layout if capacity changes.
            if capacity != old_capacity:

                # Remove existing seats.
                cursor.execute("""
                    DELETE FROM seat
                    WHERE screen_id = %s
                """, (screen_id,))

                row_count = capacity // 5

                # Calculate the central rows for VIP seating.
                vip_row_count = max(1, (row_count + 2) // 3)
                vip_start_row = (row_count - vip_row_count) // 2
                vip_end_row = vip_start_row + vip_row_count

                seat_records = []

                for seat_index in range(capacity):
                    row_index = seat_index // 5

                    # Generate alphabetical row labels: A, B ... Z, AA.
                    row_number = row_index
                    row_label = ""

                    while row_number >= 0:
                        row_label = (
                            chr(row_number % 26 + 65) + row_label
                        )
                        row_number = row_number // 26 - 1

                    seat_position = (seat_index % 5) + 1
                    seat_number = f"{row_label}{seat_position}"

                    # Assign VIP seats to central positions.
                    if (
                        vip_start_row <= row_index < vip_end_row
                        and seat_position in (2, 3, 4)
                    ):
                        seat_type = "VIP"
                    else:
                        seat_type = "STANDARD"

                    seat_records.append((
                        screen_id,
                        seat_number,
                        seat_type,
                        "AVAILABLE"
                    ))

                # Insert the newly generated seats.
                cursor.executemany("""
                    INSERT INTO seat (
                        screen_id,
                        seat_number,
                        seat_type,
                        status
                    )
                    VALUES (%s, %s, %s, %s)
                """, seat_records)

            connection.commit()

            flash("Screen updated successfully.", "success")
            return redirect(url_for("manager_cinemas"))

        # Retrieve the current registered seat count.
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM seat
            WHERE screen_id = %s
        """, (screen_id,))

        seat_count = cursor.fetchone()["total"]

        return render_template(
            "edit_screen.html",
            screen=screen,
            seat_count=seat_count
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Editing cinema screen failed.")
        return "Unable to update the screen. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



if __name__ == "__main__":
    app.run(debug=False)

