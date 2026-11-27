# Contrats de données (web/data)

Les fichiers que le navigateur charge, produits par `pipeline/build/`. Les coordonnées `x`, `y` sont en unités de
carte (origine en haut à gauche, y vers le bas ; 5 unités = 1 km, `world.json` `km_per_unit` = 0,2). `cell` est
l'indice d'un hexagone dans la grille (`col + row × cols`, voir `pipeline/core/hexgrid.py`).

| Fichier | Bâti par | Contenu |
|---|---|---|
| `world.json` | `build/world.py` | Grille (`grid`: radius 25, cols 202, rows 281), `owner` par hexagone (indice de région ≥ 0, −1 eau, −2 voisin ; l'eau comprend le fleuve, les grandes rivières et les lacs de l'Atlas du Canada), `county` (indice de DR), `elev`, `water`, `relief`, `cover` (tout à 0 pour l'instant), tables en français, `states` (17 régions), `counties` (98 DR), `rivers` (tracés `pts` ; les rivières larges, Saint-Laurent et Saguenay, ont aussi `w`, leur largeur réelle en unités de carte à chaque sommet, et vont de l'amont vers l'aval), `features` (noms de mers). |
| `projection.json` | `build/projection.py` | LAEA sphérique, `lon0` −68,5, `lat0` 53,5, `min_x`, `max_y`, `margin`, `scale`, `insets` vide. |
| `states.json` | `build/states.py` | Les 17 régions : population 2021 et 2016, croissance, superficie terrestre, densité, municipalités, SDR sans chiffre publié, rangs. |
| `nation.json` | `build/states.py` | Le Québec : `population` (somme des SDR) et `population_official` (ligne de la province), croissance, superficie, genres de SDR, SDR sans chiffre. `yields` vide. |
| `cities.json` | `build/cities.py` | 48 villes (RMR, AR, municipalités de 10 000 hab. et plus). Rendements, emplois et PIB à `null` (pas encore de données). |
| `communes.json` | `build/communes.py` | `columns` + `rows` : les 1 282 SDR (code, nom, région, population, hexagone, RMR/AR, densité, DR, x, y, genre, croissance). |
| `placenames/top.json` | `build/communes.py` | Noms affichés selon le zoom. |
| `lenses.json`, `lenses/*.json` | `build/lenses.py` | Lentilles `density` et `growth` : une valeur par hexagone (`null` hors Québec). |
| `sources.json` | `build/catalog.py` | Chaque source : éditeur, licence, description, et ses fichiers avec URL, date et sha256. |

Invariants vérifiés par `python -m pipeline check` et `tests/test_quebec.py` :

- somme des SDR = somme des régions = somme des hexagones = total officiel du Québec (8 501 833 en 2021) ;
- chaque source a une licence et un sha256 par fichier ;
- chaque hexagone québécois a une valeur de densité.
