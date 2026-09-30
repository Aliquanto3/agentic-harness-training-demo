---
name: working_days
label_text: Arbeitstage
description: Die Arbeitstage eines Zeitraums mit den Tools get_datetime, public_holidays (Netzwerk) und calculator zählen. Laden, wenn der Benutzer fragt, wie viele Arbeits- oder Werktage ein Zeitraum hat.
---
Zähle die Arbeitstage (Montag bis Freitag, ohne Feiertage) eines Zeitraums, in drei Schritten, in dieser Reihenfolge.

Zu aktivierende Tools (Baustein „Tools“): „Uhrzeit und Datum“ (get_datetime), „Feiertage“ (public_holidays) und „Taschenrechner“ (calculator). public_holidays ist ein Netzwerk-Tool und standardmäßig deaktiviert: Fehlt es, sag dem Benutzer, dass er es aktivieren soll.

1. Rufe get_datetime auf, um das heutige Datum und damit das Jahr zu kennen, wenn der Zeitraum es nicht angibt („diesen Monat“, „nächsten Monat“).
2. Rufe public_holidays mit dem Jahr des Zeitraums auf, um die Liste der Feiertage zu erhalten. Erstreckt sich der Zeitraum über zwei Jahre, rufe es für jedes der beiden auf.
3. Zähle die Tage von Montag bis Freitag im Zeitraum und ziehe dann mit calculator die Feiertage ab, die im Zeitraum auf einen Wochentag fallen (zum Beispiel 23-2).

Antworte mit der Anzahl der Arbeitstage und dann mit der Liste der abgezogenen Feiertage. Schlägt ein Tool fehl, sag welches und warum, ohne ein Datum zu erfinden.
