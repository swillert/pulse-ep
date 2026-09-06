# Synthetische Exporte (CARTO 3 / EnSiteX)

Zwei vollständige Beispiel-Exporte, je einer pro Hersteller, mit denen sich
pulse-ep ohne Patientendaten prüfen lässt.

```
carto/synthetic_study/    <Karte>.mesh, Study.xml, <Karte>_Points_Export.xml
                          + 64 Punkt-Exporte + je eine Elektroden-Positionsdatei
ensite/synthetic_study/   Contact_Mapping_Model.xml (SJM_DIF_5.0)
                          + Contact_Mapping/Map_PP_bi.csv
```

## Was sie belegen — und was nicht

**Sie belegen:** dass pulse-ep beide Dateilayouts vollständig liest — Mesh,
Skalarfelder, Messpunkte, Elektrodengeometrie — und dass das Ergebnis bis in
die Auswertung trägt. Beide Exporte enthalten **dieselbe** synthetische
Oberfläche; dass beide Leser dieselbe Fläche herausbekommen, vergleicht die
zwei Dekodierpfade gegeneinander.

**Sie belegen nicht**, dass die Feldbedeutungen klinisch korrekt sind. Ob die
Spalte, die wir `voltage_bipolar` nennen, im Gerät wirklich die bipolare
Spannung ist, kann kein selbst erzeugter Datensatz zeigen — dafür braucht es
echte Exporte. Diese Zuordnung wurde an echten Studien beider Hersteller
geprüft; das ist hier nicht reproduzierbar.

Kurz: **Format ja, Semantik nein.**

## Warum sie aus echten Exporten abgeleitet sind

Die Dateien sind nicht frei erfunden. `tools/make_synthetic_fixtures.py` liest
einen echten Export, übernimmt dessen *Struktur* — Abschnittsköpfe, Kommentar-
zeilen, Spaltensätze, Zahlenformate — und füllt sie mit erzeugtem Inhalt. Der
Unterschied ist nicht kosmetisch: ein von Hand nachgebauter
`[VerticesColorsSection]`-Kopf hatte eine Kommentarzeile zu wenig und drei
statt dreizehn Spalten. Der Leser verlor dadurch genau eine Zeile — ein Fehler,
der gegen ein frei erfundenes Fixture unsichtbar geblieben wäre.

Die übernommenen Kopfzeilen sind Formatdokumentation, keine Studiendaten.
Kommentare, die auf die Quellstudie verweisen, entfernt der Generator; die
gespeicherte Kameramatrix wird auf die Identität zurückgesetzt.

### Dateinamen

Die Namen sind Teil des Formats, deshalb stimmen sie mit den echten überein:
`Contact_Mapping_Model.xml`, `Contact_Mapping/Map_PP_bi.csv`, `<Karte>.mesh`,
`<Karte>_Points_Export.xml`, `<Karte>_P<id>_Point_Export.xml`,
`<Karte>_<Konnektor>_Eleclectrode_Positions_OnAnnotation_<t>.txt`. Der
Kartenname trägt Leerzeichen und Bindestriche wie im Original
(`1-1-1-Synthetic Left Atrium`) — ein Name ohne Leerzeichen würde einen Pfad
prüfen, den es in echten Exporten nicht gibt.

**Eine Abweichung, bewusst:** der CARTO-Studienkatalog heißt im Original nach
Patient und Untersuchungszeitpunkt. Dieser Name kann nicht mitgeliefert
werden, das Fixture nennt ihn `Study.xml`. Die Erkennung liest den Inhalt
(`<Study`), nicht den Namen, deshalb ist die Abweichung folgenlos — aber das
Fixture prüft die Katalogbenennung damit nicht.

## Dabei gefunden

Beim Erzeugen und Prüfen dieser Fixtures kamen echte Fehler heraus:

- Der `core`-Importpfad lieferte für CARTO **gar keine** Messpunkte. Die
  Koordinaten stehen im Studienkatalog, nicht im Punkt-Export, und nur die CLI
  trug sie nach (`fill_positions`).
- Die CARTO-Erkennung reichte jedes Punkt-XML als Studienkatalog weiter.

## Benutzung

```bash
examples/verify.sh                      # gegen eine Installation prüfen
pytest tests/test_synthetic_fixtures.py # dasselbe als Test, läuft in der CI
```

Neu erzeugen (braucht echte Exporte, die nicht Teil des Repositoriums sind):

```bash
python tools/make_synthetic_fixtures.py --ensite <export.zip> --carto <verzeichnis>
```

Der Generator räumt nur die Herstellerunterverzeichnisse auf — diese Datei
bleibt liegen. Sie war schon einmal einem `rm -rf` auf das Elternverzeichnis
zum Opfer gefallen, bevor sie überhaupt eingecheckt war.
