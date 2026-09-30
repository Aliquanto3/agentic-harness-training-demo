# Leitfaden zum Agent-Harness

Demo-Dokument von WaveStack, absichtlich lang: Es dient dazu, die Delegation an einen
Sub-Agenten zu zeigen. Originaltext, nicht vertraulich.

## 1. Das Modell und der Harness

Ein Sprachmodell tut nur eines: Es liest eine Folge von Tokens und sagt die
wahrscheinlichste Fortsetzung voraus. Es hat kein Gedächtnis zwischen zwei Aufrufen, keine
Uhr, keinen Zugriff auf Dateien und kein Mittel, in der Welt zu handeln. Alles, was nach
einem Agenten aussieht, der suchen, lesen, rechnen oder schreiben kann, kommt aus dem Code,
der es umgibt: dem Harness.

Der Harness bereitet vor jedem Aufruf den Kontext vor, liest die Ausgabe des Modells, führt
die angeforderten Aktionen aus und entscheidet, ob das Modell erneut aufgerufen werden muss.
Zwei Agenten, die auf demselben Modell aufbauen, können sich daher sehr unterschiedlich
verhalten: Der Unterschied liegt im Harness, nicht im Modell.

## 2. Der Kontext, eine knappe Ressource

Der Kontext ist der vollständige Text, den das Modell bei jedem Aufruf liest. Seine Größe
ist durch das Kontextfenster des Modells begrenzt, gezählt in Tokens. Ein Teil des Fensters
ist für die Antwort reserviert; der Rest teilt sich auf den System-Prompt, den Verlauf der
Unterhaltung, die Beschreibung der Tools, die gefundenen Dokumente und die Ergebnisse der
Tools auf.

Jedes gelesene Token kostet Rechenzeit, vor allem auf einem Computer ohne Grafikkarte: Ein
doppelt so langer Kontext braucht ungefähr doppelt so lange zum Lesen. Ein guter Harness
spart daher Kontext. Er nimmt nur auf, was der Aufgabe dient, entfernt, was nicht mehr
dient, und fasst zusammen, was zu lang ist.

## 3. Das Gedächtnis

Das Kurzzeitgedächtnis speist die vorigen Wechsel bei jedem Aufruf wieder ein: Ohne es
vergisst das Modell von einer Nachricht zur nächsten alles. Es wächst mit jeder Runde, bis
es das Fenster füllt. Mehrere Strategien halten es in Grenzen: das gleitende Fenster, das
nur die jüngsten Wechsel behält; die Verdichtung, die ältere Wechsel zusammenfasst; das
Entfernen alter Tool-Ergebnisse, die oft am umfangreichsten sind.

Das globale Gedächtnis dagegen überdauert die Unterhaltung: Es ist eine Datei, die der
Harness in jeder Runde neu liest und die das Modell ergänzen kann, wenn es etwas Nützliches
über den Benutzer erfährt.

## 4. Die Tools

Ein Tool ist eine Funktion, die der Harness ausführen kann: die Uhrzeit lesen, rechnen,
eine Datei lesen, einen Dienst abfragen. Der Harness beschreibt dem Modell jedes Tool mit
seinem Namen, seiner Aufgabe und seinen Parametern. Will das Modell eines nutzen, schreibt
es einen Aufruf in einem vereinbarten Format; der Harness erkennt ihn, prüft die Argumente,
führt das Tool aus und speist sein Ergebnis in den Kontext ein. Das Modell selbst führt
nie etwas aus.

Die Tool-Beschreibungen haben ihren Preis: Sie belegen bei jedem Aufruf Kontext, auch wenn
das Tool nicht gebraucht wird. Bei Dutzenden von Tools werden diese Kosten enorm. Das Lazy
Loading senkt sie: Der Harness gibt nur eine Zeile pro Tool an und lädt die vollständige
Dokumentation erst, wenn das Modell sie anfordert.

## 5. Die Agentenschleife und ihre Grenzen

Eine Agentenrunde ist eine Schleife: Aufruf des Modells, Lesen der Ausgabe, Ausführen der
angeforderten Tools, Einspeisen der Ergebnisse, dann ein neuer Aufruf, bis zu einer Antwort
ohne Tool-Aufruf. Eine Schleife ohne Grenze kann endlos laufen, zum Beispiel wenn das
Modell immer wieder dasselbe Tool anfordert oder fehlerhafte Aufrufe schreibt.

Der Harness setzt daher drei Grenzen. Die erste begrenzt die Zahl der Modellaufrufe in
einer Runde. Die zweite begrenzt die neuen Versuche nach einem abgelehnten, fehlerhaften
oder an ein unbekanntes Tool gerichteten Aufruf. Die dritte reserviert der Antwort einen
festen Platz, damit eine zu lange Ausgabe sauber abgeschnitten wird, statt überzulaufen.
Ist eine Grenze erreicht, hält der Harness die Schleife an und erklärt es: Code entscheidet,
nicht das Modell.

## 6. Die Hooks

Ein Hook ist ein Stück Code, das der Harness an einem festen Punkt der Runde aufruft: beim
Eingang der Nachricht, vor jedem Modellaufruf, vor und nach jedem Tool, am Ende der Runde.
Ein Hook kann durchlassen, ändern, blockieren oder die Meinung eines Menschen einholen. Er
dient als Schutzmechanismus (das Lesen eines sensiblen Ordners verbieten), als
Audit-Protokoll, zur Kontextinjektion (das heutige Datum) oder zur menschlichen Freigabe vor
jedem Netzwerkzugriff. Das Modell kann einen Hook nicht umgehen, da es nicht in der
Entscheidungsschleife ist: Der Hook läuft vor oder nach ihm.

## 7. Die Skills und das schrittweise Laden

Ein Skill ist eine Sammlung von Anweisungen für eine Art von Anfrage, zum Beispiel ein
Besprechungsprotokoll verfassen. Solange er nicht gebraucht wird, belegen nur sein Name und
seine Beschreibung Kontext. Passt eine Anfrage dazu, lädt das Modell ihn über ein Meta-Tool,
und seine vollständigen Anweisungen kommen in den Kontext. So bezahlt man die Tokens eines
Skills nur, wenn er gebraucht wird.

## 8. Der Sub-Agent

Manche Teilaufgaben verbrauchen viel Kontext für ein kurzes Ergebnis: ein langes Dokument
lesen, um fünf Ideen daraus zu ziehen, eine Webseite durchsuchen, um eine Zahl zu finden.
Erledigt der Haupt-Agent diese Arbeit selbst, kommt das ganze Dokument in seinen Kontext,
bleibt dort für den Rest der Runde und danach im Verlauf der folgenden Runden.

Der Harness kann die Teilaufgabe stattdessen an einen Sub-Agenten delegieren. Es ist
dasselbe Modell, aber in einem eigenen Kontext aufgerufen: ein kurzer System-Prompt, die
Aufgabe und einige Tools. Der Sub-Agent sieht weder die Unterhaltung noch den Haupt-Prompt.
Er liest das Dokument, zieht das verlangte Ergebnis heraus, und nur dieses Ergebnis kommt in
den Hauptkontext zurück. Die Ersparnis ist direkt: Die Tausende von Tokens des Dokuments
bleiben im Kontext des Sub-Agenten, der nach Abschluss der Aufgabe verschwindet, und der
Haupt-Agent erhält nur einige Hundert Tokens.

Auch die Delegation hat ihre Grenzen. Der Sub-Agent hat eigene Grenzen, enger als die der
Hauptrunde. Läuft sein Kontext über oder kommt er zu keinem Ergebnis, speist der Harness
einen ausdrücklichen Fehler ein, und die Hauptrunde läuft weiter. Und da das Modell dasselbe
ist, macht Delegieren die Arbeit nicht intelligenter: Es macht sie für den Hauptkontext
günstiger. Bei einem kleinen lokalen Modell werden die beiden Kontexte nacheinander von
derselben Instanz gelesen, was man an der Dauer der Runde sieht.

## 9. Wohin die Daten gehen

Solange alles auf dem Arbeitsplatz läuft, verlässt nichts den Rechner: Das Modell, der
Harness, die Dateien und die lokalen Tools bleiben auf der Maschine. Ein Netzwerkzugriff
entsteht, sobald ein Tool einen öffentlichen Dienst abfragt, ein entfernter MCP-Server
verbunden ist oder das Modell selbst in der Cloud gehostet wird. Im letzten Fall sendet
jeder Aufruf den gesamten Kontext an den Anbieter, den Sub-Agenten eingeschlossen. Ein
ehrlicher Harness zeigt diese Datenflüsse, zeigt ihren genauen Inhalt an und lässt sie vor
dem Senden von einem Menschen freigeben.

## 10. Merksätze

- Das Modell sagt Text voraus; der Harness macht daraus einen Agenten.
- Der Kontext ist knapp: Jeder Baustein des Harness fügt Tokens hinzu, mit einem Nutzen und
  einem Preis.
- Tools, Skills und Dokumentation werden bei Bedarf geladen, um Kontext zu sparen.
- Die Grenzen und die Hooks sind Code: Sie entscheiden an Stelle des Modells, wenn es nötig
  ist.
- Der Sub-Agent isoliert eine umfangreiche Teilaufgabe: Nur sein Ergebnis kommt in den
  Hauptkontext zurück.
