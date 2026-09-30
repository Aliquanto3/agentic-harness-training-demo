# Datensicherungsrichtlinie von Exemplia

<!-- Fiktiver Text, geschrieben für WaveStack. Exemplia ist eine erfundene Organisation: Diese Richtlinie beschreibt kein reales Unternehmen. -->

Die Daten von Exemplia folgen der 3-2-1-Regel: mindestens 3 Kopien aller Daten, auf 2 verschiedenen Datenträgern, davon 1 Kopie außerhalb des Hauptstandorts. Diese Regel gilt für die Dateiserver, die Datenbanken der Anwendungen und die E-Mail.

Die Vollsicherung der Server läuft jeden Sonntag um 2 Uhr morgens. In jeder Nacht unter der Woche kopiert um 22 Uhr eine inkrementelle Sicherung nur, was sich seit dem Vortag geändert hat. Kritische Datenbanken, etwa Buchhaltung und Kundenverwaltung, werden tagsüber zusätzlich alle 4 Stunden gesichert.

Tägliche Sicherungen werden 35 Tage aufbewahrt, wöchentliche Sicherungen 12 Wochen, und eine monatliche Sicherung wird wegen der Buchhaltungspflichten 7 Jahre lang behalten. Eine wöchentliche Kopie wird auf Band geschrieben, dann vom Netz getrennt und in einem Tresor in einem zweiten Gebäude aufbewahrt, 30 Kilometer vom Hauptsitz entfernt: Dort bleibt sie außer Reichweite von Ransomware.

Die Wiederherstellungsziele werden pro Anwendung festgelegt. Für kritische Anwendungen beträgt der maximal zulässige Datenverlust 4 Stunden, und der Dienst muss in weniger als 8 Stunden wieder laufen. Für die übrigen Anwendungen beträgt der zulässige Verlust 24 Stunden und die Wiederherstellungszeit 2 Arbeitstage.

Ein Wiederherstellungstest findet jeden Monat an einer Stichprobe von 10 zufällig gewählten Dateien statt und jedes Halbjahr an einer vollständigen Anwendung, in einer isolierten Umgebung. Das Ergebnis jedes Tests wird im Register des Betriebsteams festgehalten; ein Fehlschlag wird als Vorfall der Stufe 2 behandelt.

Arbeitsplatzrechner werden nicht gesichert: Alle Mitarbeitenden speichern ihre Dokumente in ihrem Netzlaufwerk oder im Bereich ihres Teams, die gesichert werden. Eine versehentlich gelöschte Datei kann der Support während der 35 Tage Aufbewahrung auf einfache Anfrage wiederherstellen.
