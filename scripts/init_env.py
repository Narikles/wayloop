"""Crée .env à partir de .env.example avec des clés aléatoires (bibliothèque standard seulement)."""
import base64
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env existe déjà : supprimez-le d'abord si vous voulez le régénérer.")
text = (root / ".env.example").read_text(encoding="utf-8")
text = text.replace("SECRET_KEY=a-remplacer", "SECRET_KEY=" + secrets.token_urlsafe(48), 1)
text = text.replace("STORAGE_ENCRYPTION_KEY=a-remplacer",
                    "STORAGE_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(os.urandom(32)).decode(), 1)
text = text.replace("POSTGRES_PASSWORD=a-remplacer", "POSTGRES_PASSWORD=" + secrets.token_urlsafe(18), 1)
target.write_text(text, encoding="utf-8")
print("Fichier .env créé. Sauvegardez STORAGE_ENCRYPTION_KEY en lieu sûr : sans elle, les CV sont illisibles.")
