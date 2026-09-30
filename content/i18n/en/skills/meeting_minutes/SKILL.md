---
name: meeting_minutes
label_fr: Meeting minutes
description: Write the minutes of a meeting (decisions, actions, owners) from the elements the message gives. Load it when the user asks for minutes or a summary of a meeting.
---
Write structured meeting minutes.

Steps:
1. If the user's message gives elements of the meeting (participants, topics, decisions, dates), write from these elements only, without reading any file. Only if the message gives no notes, read them with the read_file tool, path "notes_reunion.txt" ("Tools" brick, "File reading" tool).
2. Write the minutes in this order:
   - Attendees: the participants, if they are known.
   - Decisions: what was decided, one line per decision.
   - Actions: what has to be done, with the owner and the deadline when it is known.
   - Next meeting: date and time, if they are given.

Invent no decision, no owner and no date: if a piece of information is missing, write "not specified". Keep it brief, one line per point.
