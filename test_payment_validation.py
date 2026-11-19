def payment_allows_admission(booking_status, payment_status):

    return (
        booking_status == "CONFIRMED"
        and payment_status == "SUCCESSFUL"
    )


# Test different payment scenarios
test_cases = [
    ("CONFIRMED", "SUCCESSFUL"),
    ("CONFIRMED", "PENDING"),
    ("CONFIRMED", "FAILED"),
    ("CONFIRMED", "REFUNDED"),
    ("PENDING", "SUCCESSFUL"),
]

for booking_status, payment_status in test_cases:

    result = payment_allows_admission(
        booking_status,
        payment_status
    )

    print(
        f"Booking: {booking_status}, "
        f"Payment: {payment_status} "
        f"=> Admission allowed: {result}"
    )