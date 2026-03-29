# Calculateur de Zakat al-Maal Manquee

Application web permettant d'estimer la Zakat al-Maal manquee pour une personne souhaitant regulariser sa situation.

## Utilisation

Telechargez `index.html` et ouvrez-le dans votre navigateur -- aucune installation necessaire.

## Fonctionnalites

- Calcul de la Zakat manquee annee par annee (calendrier lunaire Hijri)
- Saisie de l'historique patrimonial avec gestion des fourchettes (min/max)
- Conversion automatique de l'or via les cours historiques (LBMA)
- Estimation majorante (en cas de doute, l'estimation penche vers le haut)
- Sauvegarde et reprise des saisies (export/import JSON)
- Graphiques interactifs (patrimoine vs Nisab, Zakat cumulee)
- Mode clair / Mode sombre
- 100% cote utilisateur : aucune donnee ne quitte votre navigateur

## Base juridique

- **Calendrier** : lunaire (Hijri), base sur un calendrier tabulaire islamique
- **Hawl** : position hanafite (pas de reinitialisation si la richesse tombe sous le Nisab en cours d'annee)
- **Taux** : 2.5% de la totalite de la richesse nette zakatable
- **Nisab** : base sur l'or (87,48 g)

## Avertissement

Ce calculateur fournit une **estimation majorante** de la zakat à verser.

## Sources des donnees

- Cours de l'or : [LBMA](https://www.lbma.org.uk/) via datahub.io
- Taux de change USD-EUR : [Banque Centrale Europeenne](https://www.ecb.europa.eu/)
- Calendrier Hijri : algorithme tabulaire islamique

## Licence

MIT -- voir [LICENSE](LICENSE)
