# Veröffentlichungsmaterial

Alles, was für die Publikation gezeigt wird, entsteht hier — aus den
synthetischen Exporten, nicht aus Patientendaten.

```
make_figures.py     erzeugt jede Abbildung aus tests/fixtures/synthetic/
test_figures.py     prüft, dass sie sich reproduzieren lassen
figures/            die erzeugten Abbildungen
```

Die Eingangsdaten liegen bewusst nicht hier, sondern unter
`tests/fixtures/synthetic/` — dieselben Dateien, die die Testsuite und
`examples/verify.sh` benutzen. Eine zweite Kopie würde nur auseinanderlaufen.

## Erzeugen

```bash
python publication/make_figures.py
pytest publication/test_figures.py
```

Kein Server, keine Datenbank, keine Patientendaten. Ein frischer Checkout
genügt.

## Die Abbildungen

| Datei | Was sie zeigt |
| --- | --- |
| `map_ensite.png` | EnSiteX-Export: bipolare Spannung mit Niedervoltage-Areal und Randzone, dazu die 64 Messpunkte |
| `map_carto.png` | CARTO-Export derselben Oberfläche: Aktivierungszeit, spät im selben Areal |
| `area_per_interval.png` | Fläche je Spannungsintervall — die Auswertung, die alle Klienten in `examples/` reproduzieren |
| `scalar_histograms.png` | Werteverteilung beider Hersteller |
| `cross_vendor_delta.png` | CARTO minus EnSiteX auf derselben Oberfläche |

## Zur letzten Abbildung

Sie ist **kein** klinischer Unterschied. Beide Exporte tragen dasselbe Feld;
gezeigt wird, worin die zwei Dekodierpfade voneinander abweichen — berechnet
mit derselben `compare_maps()`-Operation, die ein echter Karte-gegen-Karte-
Vergleich benutzt. Das Residuum beträgt **5·10⁻⁵ mV** und ist die
Rechengenauigkeit der Formate selbst (CARTO speichert drei Nachkommastellen),
keine Interpretationsdifferenz. `test_figures.py` hält diesen Wert fest: eine
Regression in einem der beiden Leser würde ihn um Größenordnungen verschieben
und die Bildunterschrift falsch machen.

## Was das Material belegt

Dass die Verarbeitungskette von der Herstellerdatei bis zur Auswertung
vollständig und reproduzierbar durchläuft, für beide Formate.

Es belegt **nicht**, dass die Feldbedeutungen klinisch korrekt sind — dafür
braucht es echte Exporte, die nicht Teil dieses Repositoriums sind. Siehe
`tests/fixtures/synthetic/README.md`.
