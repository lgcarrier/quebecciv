"""Ce que couvre la carte du Québec : sa projection, la taille des hexagones et ses 17 régions administratives.

Les régions administratives du Québec correspondent une à une aux 17 régions économiques (RÉ) du Recensement de
2021 de Statistique Canada (codes 2410 à 2490) ; leur numéro officiel (01 à 17) sert d'abréviation."""

from __future__ import annotations

PRUID = "24"  # code de province du Québec dans la Classification géographique type de Statistique Canada

# Projection azimutale équivalente de Lambert (forme sphérique) centrée sur le Québec. Le méridien central est celui
# de la projection conique conforme de Lambert du Québec (EPSG:32198, -68,5°) ; la latitude d'origine (53,5° N) est
# à peu près au milieu de la province (45,0° N à 62,6° N). Une projection équivalente garde les surfaces : chaque
# hexagone couvre la même superficie réelle partout sur la carte, ce qu'exige une carte de densité.
LON0 = -68.5
LAT0 = 53.5

# Échelle : 5 unités de carte par km réel. Le moteur (hérité d'usaciv) dessine des hexagones de 25 unités de rayon ;
# à cette échelle, un hexagone a 5 km de rayon (environ 8,7 km d'un côté plat à l'autre, 65 km²).
SCALE = 5.0
HEX_RADIUS_UNITS = 25.0
HEX_RADIUS_KM = HEX_RADIUS_UNITS / SCALE

# Fenêtre lon/lat de la carte (le Québec et un peu de ses voisins).
BBOX = (-80.6, 44.3, -56.0, 63.2)

# Marge de mer et de voisins autour de la province, en unités de carte (60 km).
MARGIN_UNITS = 300.0

# Région économique (RÉ 2021) → (numéro de région administrative, nom officiel avec le tiret demi-cadratin).
REGIONS = {
    "2415": ("01", "Bas-Saint-Laurent"),
    "2475": ("02", "Saguenay–Lac-Saint-Jean"),
    "2420": ("03", "Capitale-Nationale"),
    "2470": ("04", "Mauricie"),
    "2430": ("05", "Estrie"),
    "2440": ("06", "Montréal"),
    "2460": ("07", "Outaouais"),
    "2465": ("08", "Abitibi-Témiscamingue"),
    "2480": ("09", "Côte-Nord"),
    "2490": ("10", "Nord-du-Québec"),
    "2410": ("11", "Gaspésie–Îles-de-la-Madeleine"),
    "2425": ("12", "Chaudière-Appalaches"),
    "2445": ("13", "Laval"),
    "2450": ("14", "Lanaudière"),
    "2455": ("15", "Laurentides"),
    "2435": ("16", "Montérégie"),
    "2433": ("17", "Centre-du-Québec"),
}

# Provinces et territoires voisins dessinés autour du Québec (couche PR des fichiers des limites cartographiques).
NEIGHBOUR_PROVINCES = ("10", "11", "12", "13", "35", "62")  # T.-N.-L., Î.-P.-É., N.-É., N.-B., Ontario, Nunavut

# Types de subdivisions de recensement (SDR) au Québec, codes de Statistique Canada → libellé français.
CSD_TYPES = {  # genres de subdivisions de recensement de 2021 présents au Québec (libellés de Statistique Canada)
    "MÉ": "Municipalité", "V": "Ville", "PE": "Paroisse (municipalité de)", "VL": "Village", "CT": "Canton",
    "CU": "Cantons unis", "NO": "Territoire non organisé", "IRI": "Réserve indienne", "S-É": "Établissement indien",
    "VN": "Village nordique", "TI": "Terres réservées aux Inuits", "VC": "Village cri", "TC": "Terres réservées aux Cris",
    "VK": "Village naskapi", "TK": "Terre réservée aux Naskapis", "GR": "Gouvernement régional",
}

# Seuils des villes : toutes les RMR et AR (régions métropolitaines et agglomérations de recensement) dont la partie
# québécoise compte au moins CITY_PART_MIN habitants, plus les municipalités hors RMR/AR d'au moins TOWN_MIN.
CITY_PART_MIN = 10_000
TOWN_MIN = 10_000
METRO_MIN = 250_000
CAPITAL_CSD = "2423027"  # Québec (ville), capitale nationale
