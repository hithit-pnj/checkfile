# Contrôle d'un fichier salariés

Le fichier contient une ligne par salarié. Il va servir à des statistiques ou à un sondage. Ce programme le lit d'abord et écrit un rapport texte : ce qui est rempli, ce qui se répète, et les lignes à ne pas utiliser telles quelles.

## Lancer sans ouvrir le code

1. Ouvrir le dossier `data_quality_simple`.
2. Glisser le fichier `.xlsx` ou `.csv` sur `verifier.bat`.
3. Une fenêtre noire s'affiche, puis attend une touche.
4. Le rapport est créé **à côté du fichier**, avec le même nom et le suffixe `_quality_report.txt`.

Exemple : glisser `employeefile_test.xlsx` produit `employeefile_test_quality_report.txt`.

Python doit être installé sur la machine. Pour un Excel, c'est la première feuille qui est lue.

## Lancer depuis une invite de commandes

Ouvrir l'invite dans le dossier `CheckFile` (celui qui contient `data_quality_simple`), puis :

```bat
python -m data_quality_simple.main employeefile_test.xlsx
```

Le chemin du fichier peut être complet. Le rapport est écrit à côté de lui.

## Ce que contient le rapport

| Section | Contenu |
|---|---|
| 1. Column metrics | Pour chaque colonne : type, cellules vides, nombre de valeurs distinctes |
| 2. Modalities | Chaque valeur et sa part des lignes. L'identifiant, le nom, le prénom et l'e-mail sont omis |
| 3. E-mail domains | Suffixe de l'adresse (la partie après `@`) et combien de salariés l'utilisent |
| 4. Constant columns | Colonnes qui ont partout la même valeur |
| 5. Duplicates | Même `respid`, même e-mail, ou même nom + prénom |
| 6. Missing values | Lignes avec des cellules vides, en dehors de l'identité et de l'e-mail |
| 7. Business rule violations | Lignes qui cassent une règle, aujourd'hui le format d'e-mail |
| 8. Issues by line | Les doublons et les règles, regroupés par ligne |

Une cellule vide n'est pas une erreur. Elle est listée en section 6 pour que les répartitions restent lisibles. Un doublon, lui, compte deux fois la même personne.

## Ajouter une règle métier

Les règles sont en bas de `checks.py`, dans la liste `RULES`.

Une règle est une fonction. Elle reçoit le tableau et retourne une liste de problèmes (`Issue`). Une adresse ou une valeur vide ne doit pas être signalée ici : le vide est déjà décrit dans le rapport. On ne signale que ce qui est rempli et faux.

1. Écrire la fonction au-dessus de `run_rules`.
2. Ajouter son nom dans `RULES`.

Les sections 7 et 8 du rapport la prennent toutes seules. Rien à modifier dans `report.py`.

Exemple : le genre, quand il est rempli, doit être `Female` ou `Male`.

```python
def check_gender(frame):
    allowed = {"Female", "Male"}
    respids = frame[RESPID].astype(str)
    issues = []
    for line, value in frame["Gender"].items():
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text not in allowed:
            issues.append(
                Issue(
                    line=int(line),
                    respid=respids[line],
                    category="gender",
                    column="Gender",
                    message=f"Value '{text}' is not Female or Male",
                )
            )
    return issues
```

Puis :

```python
RULES = [
    check_email_format,
    check_gender,
]
```

`category` est le nom court affiché dans le rapport. `column` est la colonne à regarder. `message` est la phrase lue par l'opérateur. Le numéro de ligne est celui du fichier (l'en-tête est la ligne 1).

Pour signaler un autre doublon (deux salariés avec le même service, par exemple), ne pas écrire une règle : ajouter un groupe dans `DUPLICATE_GROUPS`, en haut de `checks.py`.

```python
DUPLICATE_GROUPS = (
    (RESPID,),
    (EMAIL,),
    (LAST_NAME, FIRST_NAME),
    ("Department",),
)
```

Le nom doit être exactement celui de l'en-tête.

## Les fichiers

| Fichier | Rôle |
|---|---|
| `verifier.bat` | Lancement par glisser-déposer |
| `main.py` | Lit le fichier et lance le contrôle |
| `checks.py` | Calculs, doublons, règles |
| `report.py` | Texte du rapport |
| `__init__.py` | Fichier vide. Il dit à Python que ce dossier est un paquet, ce qui permet la commande `python -m`. On ne le modifie pas : il n'y a aucune règle dedans |

## Ce que l'outil attend

Les colonnes `respid`, `Last name`, `First name` et `E-mail address` doivent être présentes, avec cette orthographe. Les autres colonnes sont décrites telles quelles. Si un en-tête manque, la fenêtre l'affiche au lieu de produire un rapport.

## Étape suivante, à part

Ce contrôle ne code rien. Le classeur de modalités est un autre outil, dans le dossier `coding`. On le lance après avoir lu le rapport. Il fonctionne sans ce dossier.

Mode d'emploi : [coding/README.md](../coding/README.md).
