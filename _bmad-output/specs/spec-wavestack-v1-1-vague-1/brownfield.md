# Existant touché par la vague 1 (relevé du 15/10/2026)

| Zone | Où | État |
|---|---|---|
| Installation | `README.md:30-60`, `docs/installation.md` (proxy :40, Windows :75, macOS/Linux :122, modèle local :146, premier lancement long :252) | Commandes PowerShell manuelles : uv via `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`, Qwen via `Invoke-WebRequest` (`unsloth/Qwen3.5-2B-GGUF`, `Qwen3.5-2B-Q4_K_M.gguf`). Aucun script d'installation. |
| Garde du README | `tests/test_docs_links.py:67-73` | 100 lignes au plus, ancres existantes, sans « -- ». |
| Dossier des modèles | `config.py:44-50` `data_dir()`, `config.py:1317` `models_dir()` | `%LOCALAPPDATA%\WaveStack\models`. |
| Découverte | `models/discovery.py:69-72` `_glob_gguf` (rglob), `:244-251` `discover()` | Parcourt models_dir, cache HF, LM Studio, Ollama et chemins explicites. Appelée par `session/diagnostic.py:439`. Cache d'en-têtes : `catalog.py:350-386`. Tests : `tests/test_discovery.py`. |
| Menu des modèles | `web/static/app.js:2564` `pickerOption`, `:2788` `rebuildModelPicker`, `:2828` `rebuildModelPickerByKind` | `<select id="model-picker">` natif, optgroups locaux/cloud (préfixe `cloud:`). Hébergement lisible via `hosting === "network"` et `kind`. |
| Séquence | `web/static/mcp.html:99`, `mcp.js:445`, `mcp.css:86-92` et `:534+` ; `rag.html:89` | Hauteur fixée par variables CSS ; pas de bouton agrandir (le « Mode projection » agrandit seulement les textes). |
| E2E | `tools/e2e/run_e2e.py` | `s_mcp_lab_page` (Séquence), `s_mcp_lab`, `s_model_switch`, `s_model_catalog` (sélecteur). |
