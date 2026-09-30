# Recette réelle de l'intégration (nuit du 2026-09-30)

## Conditions

- **Code testé :** commit `7e3cb12` de `feat/i18n-1`, qui réunit Gemini, FinOps, GreenOps et Langues (1/5).
- **Poste :** le PC cible (Windows 11, sans droits administrateur).
- **Environnement :** le `.venv` de la démo (extra `compression`, sans `greenops`).
- **Modèle :** Gemini réel, clé lue hors du dépôt.
- **Lancement :** WaveStack réel sur un dossier de données jetable, piloté par Playwright et par l'API.

## Résultat : 14 vérifications sur 14

- **Tour Gemini** (« Outils natifs », calculatrice) : terminé (`completed`), 2 appels.
- **FinOps :**
  - Le coût d'entrée vaut `prompt_tokens × 0,30 / 10⁶` : 473 tokens donnent 0,0001419 $.
  - La sortie compte 23 tokens pour 0,0000575 $, et la source est `api`.
  - Tour : entrée 0,0002961 $, sortie 0,0001175 $.
  - La barre haute affiche « Dépense estimée | 0,0003 $ + 0,0001 $ ».
  - L'infobulle donne le détail et la conversion : 0,0003557 € au taux de 0,86 €.
- **GreenOps (EcoLogits) :**
  - Fourchette par appel : 0,0020–0,012 Wh et 0,00089–0,0052 g CO₂e.
  - Tour : 0,0041–0,025 Wh et 0,0018–0,011 g CO₂e.
  - La note, en français, donne la méthode, le cycle de vie et les avertissements (architecture non publiée, modèle multimodal).
- **Langues :**
  - Vider la conversation, puis passer à l'anglais : 200.
  - Le tour « What time is it? » envoie le prompt système anglais, et la réponse est « It is 2:41 AM on Wednesday, September 30, 2026. ».
  - Retour au français ensuite.
- **Clé :** absente du journal complet et de `wavestack.log`.

Coût de cette recette : environ 0,0005 $. L'ensemble des appels réels de la nuit reste sous 0,05 $.
