# Parcours utilisateurs — WaveStack

Déroulé par défaut d'une session : le formateur est seul aux commandes, WaveStack est projeté. Une session dure de 30 min à 1 h ; le programme complet se découpe en modules, répartis sur plusieurs sessions. Quelques profils techniques installeront WaveStack sur leur poste, en amont ou après, en suivant le README.

Ces parcours ancrent les scénarios (CAP-40, CAP-42) et servent de guide pour la découpe en stories : chaque UJ pointe les capacités qu'il traverse.

- **UJ-1. Anaël anime une session et fait émerger le « déclic MCP ».** (palier 1 — CAP-1, CAP-2, CAP-3, CAP-9, CAP-11, CAP-12, CAP-14, CAP-15, CAP-16, CAP-21, CAP-40, CAP-41)
  - Anaël forme douze consultants en salle. Il lance WaveStack d'une commande et part du LLM nu : le modèle invente l'heure, la vue harnais montre que seul le message a été envoyé.
  - Il active la mémoire courte, puis le prompt système ; il rejoue le même prompt, le contexte grossit sous les yeux de la salle.
  - Il active les outils : le schéma s'anime, le modèle demande l'outil « heure », le harnais l'exécute et réinjecte le résultat.
  - Il active un serveur MCP public : le schéma montre qu'un composant sort du poste. Un participant demande « donc mes données partent où ? ». La salle a compris la question de l'hébergement.
  - Il réinitialise pour la session suivante.
  - Cas limite : le modèle produit un appel d'outil mal formé — la vue harnais montre l'échec du parsing, servant d'illustration plutôt que de blocage.
- **UJ-2. Karim, consultant SOC, reprend WaveStack seul après la session.** (palier 1 — CAP-27, CAP-28, CAP-29, CAP-37)
  - Karim installe WaveStack sur son poste professionnel sans droits admin, en suivant la procédure française. Il lance le scénario « Hooks ».
  - Il modifie le prompt pour que le modèle tente de lire un fichier sensible ; si le modèle ne s'y risque pas, Karim force l'appel (CAP-8). Le hook H1 bloque l'appel, la vue harnais indique que c'est le harnais qui a décidé, pas le modèle.
- **UJ-3. Léa, consultante cloud, installe WaveStack sur un poste verrouillé avant la session.** (palier 1 — CAP-36, CAP-37, CAP-39)
  - Le proxy bloque le téléchargement du modèle depuis Hugging Face. Le diagnostic de démarrage le signale en français et propose la voie hors ligne (copie du fichier depuis un partage fourni par le formateur).
  - Léa relance, WaveStack démarre, le diagnostic est vert.
- **UJ-4 (usage client en V2, scénario livré en V1). Anaël montre WaveStack à un client RSSI.** (palier 1 — CAP-3, CAP-14, CAP-20, CAP-21, CAP-40)
  - Anaël ouvre le scénario « Où vont mes données ? » et active successivement un outil local, un MCP local, un MCP public. Le schéma distingue ce qui reste sur le poste de ce qui en sort.
- **UJ-5. Sophie, consultante conformité, voit d'où vient la réponse.** (palier 2 — CAP-17, CAP-18, CAP-19)
  - Module RAG, corpus déjà indexé. Anaël pose une question dont la réponse se trouve dans un seul document ; le volet contexte LLM montre trois extraits, score et position.
  - Anaël active le reranking : l'ordre des extraits change, visible avant/après.
  - Sophie remarque que l'index est un fichier local : « le RAG, ce n'est pas le modèle qui sait, c'est le harnais qui cherche ».
- **UJ-6. Anaël délègue une lecture à un sous-agent et montre l'économie de contexte.** (palier 2 — CAP-14, CAP-30)
  - Anaël demande au modèle de lire une page courte de documentation publique puis d'en tirer trois questions de quiz. Le modèle délègue, ou Anaël force la délégation (CAP-8).
  - Le volet contexte LLM permet de basculer entre contexte principal et contexte du sous-agent : seul le résumé (quelques centaines de tokens) entre dans le contexte principal, la page complète (~2 000 tokens) reste dans le sous-agent.
- **UJ-7. Anaël compresse ce qui entre, puis ce qui sort.** (palier 2 — CAP-26, CAP-32)
  - Anaël rejoue une question dont le résultat d'outil est volumineux, cette fois avec la compression du contexte (CAP-32). Le contexte avant/après s'affiche, avec la latence de chaque tour.
  - Il déclenche Caveman (CAP-26) et rejoue la même question : les tokens de sortie chutent, l'information reste.
  - La salle voit la symétrie : la compression réduit ce qui entre, Caveman ce qui sort.
