from database.db import get_db_connection
from mysql.connector import Error

connection = None

try:
    connection = get_db_connection()

    if connection.is_connected():
        print("SUCCESS: Connected to the icctms database.")

        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")

        print("\nTables found:")
        for table in cursor.fetchall():
            print("-", table[0])

        cursor.close()

except Error as error:
    print("Database connection failed.")
    print("Error:", error)

finally:
    if connection is not None and connection.is_connected():
        connection.close()
