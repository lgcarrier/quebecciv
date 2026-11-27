# quebecciv

Le Québec dessiné comme une carte de jeu de stratégie façon *Civilization* : un territoire en hexagones de 5 km,
des villes, des régions et des « lentilles » de données, uniquement à partir de données publiques.

> **Statut : deuxième étape (PR 2).** La base de la carte, la population du Recensement de 2021 et la couverture du
> sol (RNCan 2020) sont en place. Les rendements, l'économie et les ressources ne sont pas encore portés : ils sont
> masqués plutôt qu'inventés.

## Crédits

quebecciv est un port de [Europe-Civilization](https://github.com/lmveprog/Europe-Civilization) (europeciv,
par lmveprog et ses contributeurs), lui-même un port de [usaciv](https://karpathy.ai/usaciv/) d'Andrej Karpathy.
Le moteur (grille hexagonale, rendu, interface) vient de ces projets, sous licence MIT ; voir [LICENSE](LICENSE),
qui garde les droits d'auteur d'Andrej Karpathy et des contributeurs d'europeciv à côté de ceux de l'adaptation
québécoise.

## Ce que montre la carte

- **Territoire** : 22 619 hexagones de 5 km de rayon (environ 65 km² chacun) sur une grille de 202 × 281
  (56 762 hexagones en tout, avec les voisins et la mer). Projection azimutale équivalente de Lambert (sphérique),
  centrée à 68,5° O, 53,5° N : les aires sont conservées.
- **Régions** : les 17 régions administratives (régions économiques de Statistique Canada, 2410 à 2490).
- **Divisions** : les 98 divisions de recensement (MRC et équivalents).
- **Municipalités** : les 1 282 subdivisions de recensement (SDR), nommées selon Statistique Canada, y compris les
  réserves et terres réservées sous leur nom officiel.
- **Villes** : les RMR et AR (partie québécoise d'au moins 10 000 habitants) et les municipalités de 10 000 habitants
  ou plus hors RMR et AR : 48 villes, Québec comme capitale.
- **Lentilles** : densité de population et croissance 2016-2021 ; Forêt, Terres agricoles, Milieux humides et Bâti
  (part de chaque hexagone, couverture du sol du Canada 2020).
- **Terrain** : relief (ETOPO1), mer (contour des terres de Statistique Canada), eaux intérieures (étendues d'eau de
  l'Atlas du Canada au 1:1 000 000 : fleuve, grandes rivières, lacs), tracé des rivières (Natural Earth), couverture
  du sol (classe dominante de chaque hexagone : conifères, taïga, feuillus, forêt mixte, arbustaie, toundra, prairie,
  terres cultivées, milieux humides, bâti, roc, neige et glace).

Population du Québec au Recensement de 2021 : **8 501 833** habitants. La somme des SDR, la somme des 17 régions et la
somme des hexagones sont vérifiées égales à ce total officiel (`python -m pipeline check` et les tests).

## Sources et licences

| Source | Utilisée pour | Licence |
|---|---|---|
| Statistique Canada, fichiers des limites cartographiques 2021 (service ArcGIS REST) | SDR, DR, régions économiques, provinces voisines | Licence du gouvernement ouvert – Canada |
| Statistique Canada, tableaux 98-10-0002-01 et 98-10-0003-01 (Recensement de 2021) | Population 2021 et 2016, superficie, RMR et AR | Licence du gouvernement ouvert – Canada |
| Natural Earth 1:10m v5.1.2 | Lacs, rivières, contour des États-Unis | Domaine public |
| NOAA ETOPO1 (par ERDDAP) | Relief, profondeur de la mer | Domaine public (gouvernement des États-Unis) |
| Ressources naturelles Canada, Atlas du Canada 1:1 000 000 : étendues d'eau et îles | Fleuve, rivières larges, lacs (eau à l'intérieur des municipalités) | Licence du gouvernement ouvert – Canada |
| Ressources naturelles Canada, couverture du sol du Canada 2020 (30 m, GeoTIFF de 2,1 Go) | Couverture du sol des hexagones, lentilles du territoire | Licence du gouvernement ouvert – Canada |

Chaque source a son module dans `pipeline/sources/` et sa provenance (URL, date, sha256) dans
`web/data/sources.json`, que l'Almanach affiche avec sa licence.

## Approximations (affichées dans l'Almanach)

- La population de chaque SDR est répartie **uniformément** sur sa superficie, au prorata de la part de la SDR dans
  chaque hexagone. Une grande municipalité rurale ou un territoire non organisé paraît donc uniformément peuplé.
- Huit SDR n'ont pas de chiffre publié (« .. » chez Statistique Canada, dénombrement partiel) : Lac-Rapide,
  Pakuashipi, Romaine 2, Listuguj, Doncaster, Kanesatake, Akwesasne, Kahnawake. Elles restent sans population ; le
  total officiel les exclut aussi.
- Une RMR ou AR qui déborde du Québec (Ottawa – Gatineau) ne compte que sa partie québécoise.
- **Terre ou eau** : un hexagone est de la terre quand au moins la moitié de ses points d'échantillonnage (67, maille
  de 1 km) tombent sur la terre, les étendues d'eau de l'Atlas du Canada retirées des limites de Statistique Canada.
  Chaque municipalité garde au moins un hexagone de terre (celui où elle a le plus de points, même s'il est surtout
  dans l'eau, comme pour une petite île) : toutes les municipalités habitées gardent leur population sur leurs propres
  hexagones (Montréal et l'ouest de l'île, Kirkland, Beaconsfield, L'Île-Perrot, Laval, l'île d'Orléans…).
- **Saint-Laurent et Saguenay** : plus étroits qu'un hexagone (1 à 3 km contre 8,7 km), leurs rives restent de la
  terre à la règle de la majorité. Ils sont **dessinés à leur largeur réelle** par-dessus les hexagones, du lac
  Saint-Louis à l'estuaire et de Chicoutimi à Tadoussac : le tracé suit le milieu de l'eau du raster de 500 m et la
  largeur y est mesurée en travers (`pipeline/core/rivers.py`). À l'île d'Orléans, les deux chenaux sont tracés et
  l'île apparaît entre eux. Les lacs fluviaux (Saint-Louis, Saint-Pierre), assez larges, restent des hexagones d'eau
  que le fleuve relie. Les autres rivières (Outaouais, des Prairies, Mille Îles…) ne sont en eau que là où elles
  occupent la moitié d'un hexagone ; ailleurs, leur tracé de Natural Earth est dessiné quand il existe.
- L'eau de l'estuaire et du golfe est classée « côte » ou « mer » (reliée au bord de la carte) ; les eaux intérieures,
  « lac ».
- La frontière Québec – Labrador est celle des fichiers de Statistique Canada.
- Couverture du sol : un point tous les 480 m (un pixel sur huit de l'aperçu à 60 m inclus dans le GeoTIFF de 30 m),
  environ 280 points par hexagone. La couleur est la classe de terre dominante ; les lentilles donnent la part des
  points dans un groupe de classes, eau comprise dans le total. Exactitude globale annoncée par RNCan : 86,9 %.
- Ordre de grandeur vérifié : la forêt (classes NALCMS 1, 2, 5, 6) couvre 50 % des points des hexagones du Québec,
  environ 730 000 km², contre « plus de 901 503 km² » (59,6 % du milieu terrestre) dans les *Chiffres-clés du Québec
  forestier – Édition 2026* du MRNF. L'écart vient des définitions (le MRNF compte les coupes et brûlis en
  régénération, classés ici en arbustaie) et des hexagones d'eau, exclus.
- Pas de rendements (nourriture, production) : aucune formule tirée de la couverture du sol ne serait assez
  transparente ni vérifiable ; ils restent masqués.

## Lancer le projet

Python 3.11 ou plus, bibliothèque standard seulement ; [uv](https://docs.astral.sh/uv/) recommandé.

```sh
uv run python -m pipeline all      # télécharge (data/raw), traite (data/interim) et bâtit web/data
uv run python -m pipeline all --light  # sans le GeoTIFF de 2,1 Go : carte sans couverture du sol (à ne pas publier)
uv run python -m pipeline check    # vérifie web/data
uv run python -m unittest discover tests
uv run python -m pipeline serve    # http://127.0.0.1:8765
```

`data/raw/` et `data/interim/` ne sont pas versionnés ; `web/data/` l'est (environ 3,4 Mo, dont 1,6 Mo de lentilles
chargées à la demande). Le premier `pipeline fetch` télécharge le GeoTIFF de la couverture du sol (2,1 Go) ; son
traitement (lecteur GeoTIFF en bibliothèque standard, `pipeline/core/geotiff.py`) prend environ 40 s. Aucune clé, aucun
compte, aucun service payant.

## Pas encore porté

Rendements et économie, emploi et revenus, ressources,
routes et chemins de fer, conseillers, classements, vue de ville, défi quotidien. Voir
[docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) pour le format des fichiers.
