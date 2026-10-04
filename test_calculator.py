from datetime import date, time

from astrology.calculator import calculate_chart


# 출생시간 있음
chart = calculate_chart(
    date(2022, 5, 17),
    time(14, 20),
    "Austin, TX, USA",
)

# 출생시간 없음
chart = calculate_chart(
    date(2022, 5, 17),
    None,
    "Austin, TX, USA",
)
print(chart)
                                                                                                                                                                                              