

def test_a_two_digit_year_of_99_is_1999_not_2099():
    import datetime as dt

    from familyos.extraction import dates
    assert dates._full_year(26) == 2026 and dates._full_year(69) == 2069 and dates._full_year(70) == 1970 and dates._full_year(99) == 1999
    assert [f.date for f in dates.find_dates("Fee due 05/11/26", dt.date(2026, 10, 21))] == [dt.date(2026, 11, 5)]
    assert [f.date for f in dates.find_dates("Born 05/11/99", dt.date(2026, 10, 21))] == [dt.date(1999, 11, 5)]
