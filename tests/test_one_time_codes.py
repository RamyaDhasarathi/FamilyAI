"""A one-time code is discarded at the door: not stored, not read, not shown."""
from email.message import EmailMessage

import pytest

from familyos.intake import codes, gateway

TOMTOM = ("Subject: Please activate your TomTom account to get started\n\nYour one-time verification code:\n\n19496094\n\n"
          "Enter the verification code in the browser to continue setting up your account.\nThe code will be valid for 30 minutes.\n--\nPrivacy policy: https://x.example")


@pytest.mark.parametrize("subject,body", [
    ("Please activate your TomTom account", "Your one-time verification code:\n\n19496094\n\nvalid for 30 minutes"),
    ("123456 is your OTP", "123456 is your OTP for a transaction of INR 500 at Amazon. Do not share it."),
    ("Your Google verification code", "G-482913 is your Google verification code."),
    ("Security code", "Your security code is 7781 and expires in 10 minutes."),
])
def test_codes_are_recognised(subject, body):
    assert codes.is_one_time_code(subject, body)


@pytest.mark.parametrize("subject,body", [
    ("Term 2 fee due", "Dear parents, please pay the term fee of Rs 48000 by 25 September. For queries call 04412345678."),
    ("Your bank statement", "Never share your OTP with anyone, including the bank. " + "Statement line. " * 400),
    ("PTM on Friday", "The PTM is at 9 am in room 12. Verification of the diary is required."),
    ("Booking confirmed", "Your booking reference is 2203. Thank you."),
])
def test_ordinary_mail_is_not(subject, body):
    assert not codes.is_one_time_code(subject, body)


async def test_a_code_mail_through_the_forwarding_door_is_refused_and_nothing_is_stored(family, database):
    msg = EmailMessage()
    msg["From"] = "dashboard@messages.tomtom.com"
    msg["To"] = family.household["inbound_address"]
    msg["Subject"] = "Please activate your TomTom account to get started"
    msg.set_content("Your one-time verification code:\n\n19496094\n\nThe code will be valid for 30 minutes.")
    before = await database.fetchval("SELECT count(*) FROM input_artifacts")
    with pytest.raises(gateway.Rejected) as exc:
        await gateway.receive_email(msg.as_bytes())
    assert exc.value.reason == "one_time_code"
    assert await database.fetchval("SELECT count(*) FROM input_artifacts") == before
