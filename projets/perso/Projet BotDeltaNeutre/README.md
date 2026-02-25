# 🤖 Bot Delta-Neutre de Funding

Ce dépôt est **un projet** de bot d’arbitrage delta-neutre sur les taux de funding pour **Hyperliquid DEX**.

Il surveille les taux de funding des contrats perpétuels (90+ paires) et ouvre automatiquement des positions delta-neutres quand les taux deviennent anormalement élevés, afin de collecter les paiements de funding tout en couvrant le risque de prix avec une position spot.

> Quiconque veut s’amuser à le tester, l’améliorer ou l’adapter peut le faire librement.

## ✨ Fonctionnalités

- **Surveillance automatique du funding** — scan de 20+ paires actives toutes les ~20 secondes
- **Stratégie delta-neutre** — couverture perp + spot pour neutraliser le risque directionnel
- **Détection intelligente des signaux** — détection d’anomalies avec Z-score et seuils configurables
- **Gestion du risque** — drawdown max, circuit breaker, limites de concentration
- **Dashboard Telegram** — alertes en temps réel + commandes `/status`, `/start`, `/stop`
- **Suivi interne du wallet** — suivi du PnL et historique des financements
- **Localisation française** — support complet du français

## 🏗️ Architecture

```
├── main.py                    # Point d’entrée
├── config.example.json        # Modèle de configuration
├── modules/
│   ├── hyperliquid_api.py     # Wrapper SDK Hyperliquid (perps + spot)
│   ├── execution_engine.py    # Exécution des ordres (perp + hedge spot)
│   ├── funding_analyzer.py    # Analyse des taux de funding + signaux
│   ├── position_manager.py    # Gestion de l’état des positions
│   ├── risk_manager.py        # Contrôles de risque + circuit breaker
│   └── telegram_bot.py        # Interface bot Telegram
├── strategies/
│   └── delta_neutral.py       # Logique principale de stratégie
├── wallet/
│   └── wallet_manager.py      # Suivi du capital et du PnL
├── core/
│   ├── config.py              # Chargement de la config
│   └── logger.py              # Logs CSV des trades/funding
└── localization/
    └── translator.py          # Support i18n
```

## 🚀 Démarrage rapide

### 1. Cloner et installer

```bash
git clone https://github.com/YOUR_USERNAME/delta-neutral-bot.git
cd delta-neutral-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurer

```bash
cp config.example.json config.json
```

Éditez `config.json` avec vos identifiants :

| Champ | Description |
|---|---|
| `hyperliquid.private_key` | Votre clé privée EVM (`0x...`) |
| `hyperliquid.account` | Votre adresse EVM (`0x...`) |
| `telegram.token` | Token de bot Telegram obtenu via @BotFather |
| `telegram.admin_chat_ids` | Votre identifiant utilisateur Telegram |

### 3. Alimenter le compte

1. Déposez des USDC sur [app.hyperliquid.xyz](https://app.hyperliquid.xyz)
2. Vérifiez que les fonds sont dans le compte de trading **Perps** (et non Spot ou HyperEVM)

### 4. Lancer le bot

```bash
python main.py
```

## 📊 Fonctionnement

### Stratégie delta-neutre

1. **Surveiller** les taux de funding sur toutes les paires activées
2. **Détecter** les anomalies quand `|funding_rate| > threshold` (par défaut : `0.003%/h`)
3. **Ouvrir** une position delta-neutre :
   - **Funding positif** → SHORT perp + BUY spot (les shorts reçoivent le funding)
   - **Funding négatif** → LONG perp + SELL spot (les longs reçoivent le funding)
4. **Collecter** les paiements de funding chaque heure
5. **Fermer** la position quand le funding repasse sous le seuil de rentabilité

### Répartition du capital

Le capital est réparti à 50/50 entre marge perp et couverture spot afin de conserver la neutralité delta.

### Exemple

```
Signal : funding HYPE = -0.0048%/h (42% annualisé)
→ LONG 0.51 HYPE perp @ $26.95
→ BUY 0.51 HYPE spot @ $26.95 (couverture)
→ Collecte d’environ $0.006/h de funding
→ Position neutre au prix : gains/pertes se compensent entre perp et spot
```

## ⚙️ Configuration

### Paramètres de stratégie

| Paramètre | Valeur par défaut | Description |
|---|---|---|
| `funding_threshold` | `3e-05` | Taux de funding minimal pour déclencher (0.003%/h) |
| `funding_ma_period` | `3` | Période de moyenne mobile pour le signal |
| `funding_zscore_k` | `1.0` | Multiplicateur de Z-score pour la détection d’anomalie |
| `capital_per_pair_pct` | `1.0` | % du capital alloué par trade |
| `min_trade_size_usdt` | `5.0` | Taille minimale d’ordre |
| `slippage_pct` | `0.001` | Tolérance maximale de slippage |

### Paramètres de risque

| Paramètre | Valeur par défaut | Description |
|---|---|---|
| `max_drawdown_pct` | `0.10` | Drawdown maximal du portefeuille (10%) |
| `max_daily_loss_pct` | `0.03` | Perte quotidienne maximale (3%) |
| `circuit_breaker_enabled` | `true` | Arrêt automatique en cas de pertes importantes |

## 📱 Commandes Telegram

| Commande | Description |
|---|---|
| `/start` | Démarrer la stratégie |
| `/stop` | Arrêter la stratégie |
| `/status` | Afficher les positions en cours et le PnL |
| `/dashboard` | Ouvrir le dashboard interactif avec boutons |

## ⚠️ Avertissement

Ce bot est fourni à des fins éducatives. Le trading de contrats perpétuels comporte des risques importants. Utilisez-le à vos propres risques. N’investissez jamais des fonds que vous ne pouvez pas vous permettre de perdre.

## 📄 Licence

MIT
