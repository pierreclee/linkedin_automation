# LinkedIn Bot Automation

Bot Playwright qui automatise les interactions LinkedIn : acceptation de connexions et envoi de messages ciblés aux personnes ayant à la fois liké ET commenté un post.

Tourne sur Raspberry Pi 4 (Linux headless). Contrôlé via Telegram (OpenClaw).

---

## Prérequis

- Python 3.11+
- pip
- Raspberry Pi 4 avec accès internet
- OpenClaw installé et configuré avec Telegram

---

## Installation sur le Raspberry Pi

```bash
# Cloner le repo
git clone <repo-url>
cd bot-linkedin-automation

# Créer et activer l'environnement virtuel (obligatoire sur Raspberry Pi OS)
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Installer Chromium pour Playwright (ARM64)
playwright install chromium

# Copier et remplir le fichier d'environnement
cp .env.example .env
nano .env   # Ajouter TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID

# Initialiser la DB
python linkedin_bot.py --status
```

---

## 🔑 Procédure de login LinkedIn (à faire sur Windows, pas sur le Pi)

Le Raspberry Pi est headless (pas d'écran). Le login doit se faire sur ton PC Windows.

### Étape 1 — Sur ton PC Windows

Dans ce dossier :
```bash
pip install -r requirements.txt
playwright install chromium
python linkedin_bot.py --login
```

Un navigateur Chromium s'ouvre. Connecte-toi manuellement à LinkedIn (email, mot de passe, 2FA si nécessaire). Quand tu es sur le fil d'actualité, reviens dans le terminal et appuie sur **Entrée**. Le fichier `session/state.json` est créé automatiquement.

### Étape 2 — Transférer la session sur le Pi

```bash
scp session/state.json pi@<ip-du-raspberry>:~/bot-linkedin-automation/session/state.json
```

### Quand la session expire

La session dure en général 30 à 90 jours. Quand tu reçois l'alerte Telegram "Session expirée" :
1. Relancer `python linkedin_bot.py --login` sur Windows
2. Retransférer `session/state.json` sur le Pi via SCP
3. Le bot reprend automatiquement au prochain run cron

---

## Configuration du cron (Raspberry Pi)

```bash
crontab -e
```

Créer le dossier de logs d'abord :
```bash
mkdir -p /home/pi/linkedin_automation/logs
```

Ajouter (exemple : toutes les 4 heures) — utilise le Python du venv, pas `python3` système :
```
0 */4 * * * cd /home/pi/linkedin_automation && /home/pi/linkedin_automation/venv/bin/python linkedin_bot.py --run >> logs/cron.log 2>&1
```

---

## Utilisation via Telegram

Une fois le listener démarré (voir section Déploiement du listener), contrôle le bot directement depuis Telegram :

| Commande | Action |
|----------|--------|
| `/linkedin help` | Afficher toutes les commandes |
| `/linkedin add <url>` | Ajouter un post (flow interactif : le bot te demande les templates) |
| `/linkedin list` | Lister les posts trackés |
| `/linkedin remove <url>` | Supprimer un post et ses données |
| `/linkedin setmsg <url>` | Modifier les templates d'un post existant |
| `/linkedin on` / `/linkedin off` | Activer / désactiver le bot |
| `/linkedin status` | État et stats du dernier run |
| `/linkedin run` | Forcer un run immédiat (asynchrone — rapport envoyé à la fin) |

---

## Utilisation via SSH (alternative)

Si le listener n'est pas actif, contrôle via SSH :

```bash
ssh pi@<ip-du-pi>
cd ~/linkedin_automation
source venv/bin/activate
python linkedin_bot.py --status
python linkedin_bot.py --add-post <url>
```

---

## Déploiement du listener (service systemd)

Sur le Pi, après avoir cloné le repo et installé les dépendances :

```bash
sudo cp linkedin-listener.service /etc/systemd/system/
sudo systemctl enable linkedin-listener
sudo systemctl start linkedin-listener
sudo systemctl status linkedin-listener   # vérifier que ça tourne
```

Le service redémarre automatiquement en cas de crash et au reboot du Pi. Pour voir les logs :

```bash
journalctl -u linkedin-listener -f
```

---

## Templates de messages

Chaque post a 2 templates configurables via Telegram :

- **msg_mp** — Message privé envoyé aux personnes qui ont **liké ET commenté** et sont connectées
- **msg_comment_reply** — Réponse en commentaire pour ceux qui ont **liké ET commenté** mais ne sont pas connectés

Variables disponibles : `{first_name}`, `{post_url}`, `{reposted}` (dans msg_mp uniquement)

Exemples :
- msg_mp : `Salut {first_name}, j'ai vu que tu avais interagi avec mon post — tu aurais 2 min pour me donner ton feedback ?`
- msg_comment_reply : `Salut {first_name} ! Je voulais t'écrire en MP mais on n'est pas encore connectés — envoie-moi une demande et je t'écris dès que c'est bon 👋`

---

## Règles d'engagement

| Condition | Action |
|-----------|--------|
| Liké + Commenté + Reposté + Connecté | MP (priorité 1) |
| Liké + Commenté + Connecté | MP (priorité 2, après les reposters) |
| Liké + Commenté + Non connecté | Réponse en commentaire |
| Seulement liké | Rien |
| Seulement commenté | Rien |
| Seulement reposté | Rien |

Les commentaires postés il y a moins de 5 minutes sont ignorés.

---

## Structure des fichiers

```
bot-linkedin-automation/
├── linkedin_bot.py   # CLI entry point
├── db.py             # SQLite (état, engagements, config)
├── scraper.py        # Playwright lecture (réactions, commentaires, reposts)
├── messenger.py      # Playwright écriture (MP, réponses, connexions)
├── telegram.py       # Notifications Telegram HTTP
├── linkedin.db       # Base de données (créée au premier lancement)
├── session/
│   └── state.json    # Session LinkedIn (créée par --login sur Windows)
└── logs/
    └── cron.log      # Logs des runs cron
```
