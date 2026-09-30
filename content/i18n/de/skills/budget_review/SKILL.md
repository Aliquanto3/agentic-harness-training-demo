---
name: budget_review
label_text: Budgetübersicht
description: Das Budget des Projekts mit den Tools read_file (Datei confidentiel/budget_projet.txt) und calculator prüfen, als Tabelle dargestellt. Laden, wenn der Benutzer nach dem Budget des Projekts, seiner Summe oder der Aufteilung seiner Posten fragt.
---
Prüfe das Budget des Projekts in drei Schritten, in dieser Reihenfolge.

Zu aktivierende Tools (Baustein „Tools“): „Datei lesen“ (read_file) und „Taschenrechner“ (calculator). Ist eines davon deaktiviert, sag es dem Benutzer und bitte ihn, es zu aktivieren.

1. Lies das Budget mit read_file, Pfad „confidentiel/budget_projet.txt“.
2. Berechne die Summe mit calculator, indem du alle Posten addierst (zum Beispiel 12000+48000+5000).
3. Berechne den Anteil jedes Postens an der Summe in Prozent (zum Beispiel 12000*100/65000): Sende alle diese Aufrufe an calculator zusammen, in einer einzigen Antwort, einen Aufruf pro Posten.

Antworte zum Schluss mit einer Markdown-Tabelle mit drei Spalten: Posten, Betrag (€), Anteil an der Summe (%), mit einer letzten Zeile „Summe“.

Rechne nie im Kopf: Jede Zahl der Tabelle stammt aus der Datei oder von calculator. Runde die Prozentsätze auf eine Nachkommastelle.
