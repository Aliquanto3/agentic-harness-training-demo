---
name: meeting_minutes
label_fr: Besprechungsprotokoll
description: Das Protokoll einer Besprechung (Entscheidungen, Aufgaben, Verantwortliche) aus den Angaben der Nachricht verfassen. Laden, wenn der Benutzer ein Protokoll oder eine Zusammenfassung einer Besprechung verlangt.
---
Verfasse ein strukturiertes Besprechungsprotokoll.

Schritte:
1. Enthält die Nachricht des Benutzers Angaben zur Besprechung (Teilnehmende, Themen, Entscheidungen, Termine), schreibe nur auf Grundlage dieser Angaben, ohne eine Datei zu lesen. Nur wenn die Nachricht keine Notizen enthält, lies sie mit dem Tool read_file, Pfad „notes_reunion.txt“ (Baustein „Tools“, Tool „Datei lesen“).
2. Verfasse das Protokoll in dieser Reihenfolge:
   - Anwesende: die Teilnehmenden, sofern bekannt.
   - Entscheidungen: was beschlossen wurde, eine Zeile pro Entscheidung.
   - Aufgaben: was zu tun ist, mit der verantwortlichen Person und der Frist, sofern bekannt.
   - Nächste Besprechung: Datum und Uhrzeit, sofern angegeben.

Erfinde weder Entscheidungen noch Verantwortliche noch Termine: Fehlt eine Information, schreibe „nicht angegeben“. Fasse dich kurz, eine Zeile pro Punkt.
