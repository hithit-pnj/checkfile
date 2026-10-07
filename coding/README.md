# Classeur de codage

Outil à part du contrôle. On le lance en général après avoir lu le rapport de `data_quality_simple`, mais il ne lit pas ce rapport et n'a pas besoin de ce dossier pour fonctionner.

Il lit le fichier salariés et écrit un classeur Excel. Chaque colonne, sauf l'identité et l'e-mail, a son onglet. L'onglet porte le nom de la colonne. Dedans : la liste des modalités, et un code qui commence à 1.

## Lancer sans ouvrir le code

1. Ouvrir le dossier `coding`.
2. Glisser le fichier `.xlsx` ou `.csv` sur `generer.bat`.
3. Une fenêtre noire s'affiche, puis attend une touche.
4. Le classeur est créé **à côté du fichier**, avec le même nom et le suffixe `_coding.xlsx`.

Exemple : glisser `employeefile_test.xlsx` produit `employeefile_test_coding.xlsx`.

Relancer le script **écrase** ce classeur. À faire avant les modifications manuelles, pas après.

Python doit être installé sur la machine. Pour un Excel, c'est la première feuille qui est lue.

## Lancer depuis une invite de commandes

Ouvrir l'invite dans le dossier `CheckFile` (celui qui contient `coding`), puis :

```bat
python -m coding.generate_coding employeefile_test.xlsx
```

Le chemin du fichier peut être complet. Le classeur est écrit à côté de lui.

## Ce que contient le classeur

| Onglet | Contenu |
|---|---|
| Un onglet par colonne | Toutes les colonnes du fichier, dans le même ordre, sauf `respid`, `Last name`, `First name` et `E-mail address` |
| Colonne A | Chaque valeur non vide, une fois, dans l'ordre alphabétique (sans tenir compte des majuscules). L'en-tête de cette colonne reste vide |
| Colonne `VALUE` | 1, 2, 3… Le compte repart à 1 dans chaque onglet |

Une cellule vide n'a pas de ligne, et donc pas de code. Elle reste vide dans le fichier codé.

`France`, `france` et ` France ` sont trois modalités. Le script ne rapproche rien.

Les nombres sont classés comme du texte : `10` vient avant `2`. L'ordre sert de point de départ. Il est prévu pour être revu à la main.

Le nom d'un onglet Excel est limité à 31 caractères et ne peut pas contenir `\ / * ? : [ ]`. Si un en-tête pose ce problème, le script s'arrête et le nomme, sans écrire de classeur.

## Modifications manuelles

Le classeur est une template. On peut changer les codes, y compris mettre le même code sur deux modalités pour les regrouper ensuite.

Si une modalité est renommée dans ce classeur, il faut la renommer **de la même façon dans le fichier source**. Le remplacement compare le texte exact. Rien n'est réconcilié automatiquement.

## Remplacer les modalités par les codes

Les deux fichiers sont côte à côte : le fichier original, et le classeur dont le nom se termine par `_coding.xlsx`.

1. Glisser le fichier original sur `remplacer.bat`.
2. Le script lit le classeur à côté de lui.
3. Il écrit une copie, suffixe `_coded.xlsx`. Le fichier original n'est pas modifié.

Depuis le dossier `CheckFile` :

```bat
python -m coding.generate_coded_file employeefile_test.xlsx
```

Si le classeur porte un autre nom, le passer en second :

```bat
python -m coding.generate_coded_file employeefile_test.xlsx mon_codage.xlsx
```

Pour chaque colonne du fichier original :

- pas d'onglet à son nom dans le classeur : la colonne est recopiée telle quelle, sans erreur ;
- un onglet existe : chaque modalité de la colonne A est remplacée par le code de la colonne `VALUE`.

Une cellule vide le reste. Une modalité absente de l'onglet reste en clair, et la fenêtre la liste. `France` ne remplace pas `france`.

Les colonnes exclues dans `generate_coding.py` n'ont pas d'onglet, donc elles restent en clair ici aussi. Inutile de les répéter dans ce script.

## Les fichiers

| Fichier | Rôle |
|---|---|
| `generer.bat` | Glisser-déposer pour créer le classeur de codage |
| `generate_coding.py` | Lit le fichier et écrit le classeur |
| `remplacer.bat` | Glisser-déposer du fichier original pour appliquer les codes |
| `generate_coded_file.py` | Écrit la copie `_coded.xlsx` |
| `__init__.py` | Fichier vide. Il dit à Python que ce dossier est un paquet, ce qui permet la commande `python -m` |
