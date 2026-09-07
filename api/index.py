import os
import json
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

# In-memory storage for demonstration (Note: Vercel serverless instances reset state on cold starts)
RECENT_SIGNALS = []
ACTIVE_POSITIONS = []

# System Configuration from Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL_THRESHOLD = float(os.environ.get("MODEL_THRESHOLD", "0.60"))


def send_telegram_alert(mint: str, prob: float, price: float) -> bool:
    """Sends an instant alert to your Telegram chat via Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Bot token or Chat ID missing.")
        return False

    message = (
        f"🚨 <b>PUMPFUN HIGH CONVICTION SIGNAL</b> 🚨\n\n"
        f"• <b>Mint:</b> <code>{mint}</code>\n"
        f"• <b>Model Probability:</b> <code>{prob * 100:.1f}%</code>\n"
        f"• <b>Entry Price:</b> <code>{price:.8f} SOL</code>\n"
        f"• <b>Target (+200%):</b> <code>{price * 3.0:.8f} SOL</code>\n\n"
        f"🔗 <a href='https://pump.fun/{mint}'>View on Pump.fun</a>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"[Telegram Alert Failed]: {e}")
        return False


def calculate_model_score(token_data: dict) -> float:
    """
    Lightweight feature scorer mapping token metadata & early stats to probability score.
    """
    score = 0.50  # Base prior probability

    # Feature 1: Check creator volume history / bonding curve velocity
    v_sol = float(token_data.get("vTokensInBondingCurve", 0))
    if v_sol > 10:
        score += 0.15

    # Feature 2: Early buy ratio & volume
    buy_volume = float(token_data.get("initialBuy", 0))
    if buy_volume >= 1.0:
        score += 0.15

    # Feature 3: Dev holding check
    dev_percent = float(token_data.get("devHoldingPct", 0))
    if dev_percent < 5.0:
        score += 0.10
    elif dev_percent > 20.0:
        score -= 0.25

    return round(min(max(score, 0.01), 0.99), 3)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Serves live signals and open positions data to index.html dashboard."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        response_payload = {
            "status": "online",
            "signals": RECENT_SIGNALS[:15],
            "positions": ACTIVE_POSITIONS[:10]
        }
        self.wfile.write(json.dumps(response_payload).encode("utf-8"))

    def do_POST(self):
        """Processes incoming Webhook events from PumpPortal."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode("utf-8"))
        except Exception:
            payload = {}

        mint = payload.get("mint", "unknown")
        entry_price = float(payload.get("priceSol", 0.00000003))

        # Compute model prediction
        prob = calculate_model_score(payload)
        telegram_sent = False

        # Execute alert if probability satisfies the model threshold
        if prob >= MODEL_THRESHOLD:
            telegram_sent = send_telegram_alert(mint, prob, entry_price)

            # Record simulated paper position
            ACTIVE_POSITIONS.insert(0, {
                "mint": mint,
                "entry": entry_price,
                "current": entry_price * 1.05,  # Initial tick preview
                "prob": prob,
                "status": "OPEN"
            })

        # Log signal to memory
        RECENT_SIGNALS.insert(0, {
            "mint": mint,
            "prob": prob,
            "telegram_sent": telegram_sent,
            "price": entry_price
        })

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": True, "score": prob}).encode("utf-8"))
