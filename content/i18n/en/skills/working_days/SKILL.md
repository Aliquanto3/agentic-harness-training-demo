---
name: working_days
label_text: Working days
description: Count the working days of a period with the get_datetime, public_holidays (network) and calculator tools. Load it when the user asks how many working or business days a period has.
---
Count the working days (Monday to Friday, public holidays excluded) of a period, in three steps, in this order.

Tools to enable ("Tools" brick): "Time and date" (get_datetime), "Public holidays" (public_holidays) and "Calculator" (calculator). public_holidays is a network tool, disabled by default: if it is missing, tell the user to enable it.

1. Call get_datetime to know today's date, and so the year, if the period does not state it ("this month", "next month").
2. Call public_holidays with the period's year, to get the list of public holidays. If the period spans two years, call it for each of them.
3. Count the days from Monday to Friday in the period, then subtract with calculator the public holidays that fall on a weekday within the period (for example 23-2).

Answer with the number of working days, then the list of the public holidays subtracted. If a tool fails, say which one and why, without inventing any date.
