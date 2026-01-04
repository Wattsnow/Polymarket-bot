import requests
import time
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import json

class PolymarketTelegramBot:
    def __init__(self, telegram_token, chat_id, api_key=None, secret=None, passphrase=None):
        self.telegram_token = telegram_token
        self.chat_id = chat_id
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        
        self.base_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.telegram_url = f"https://api.telegram.org/bot{telegram_token}"
        
        # Track historical data
        self.wallet_history = defaultdict(list)
        self.market_volumes = defaultdict(list)
        self.market_prices = defaultdict(list)
        self.wallet_outcomes = defaultdict(list)
        self.sent_alerts = set()
        
        # Bot state
        self.is_paused = False
        self.scan_interval = 60
        self.last_update_id = 0
        
        # Configurable thresholds
        self.thresholds = {
            'fresh_wallet_days': 7,
            'fresh_wallet_min_value': 1000,
            'unusual_size_multiplier': 2.5,
            'niche_volume_max': 10000,
            'niche_trades_min': 3,
            'win_rate_conviction_min': 7,
            'win_rate_min_value': 300,
            'pre_move_min_value': 500,
            'pre_move_change_pct': 0.15,
            'coordinated_min_value': 200,
            'coordinated_min_wallets': 3
        }
    
    def send_telegram(self, message, reply_markup=None):
        """Send message to Telegram"""
        url = f"{self.telegram_url}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data)
            return response.json()
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return None
    
    def get_updates(self):
        """Get new messages from Telegram"""
        url = f"{self.telegram_url}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 30}
        try:
            response = requests.get(url, params=params, timeout=35)
            return response.json().get('result', [])
        except Exception as e:
            print(f"Error getting updates: {e}")
            return []
    
    def process_command(self, message):
        """Process commands from Telegram"""
        text = message.get('text', '').strip()
        
        if text == '/start' or text == '/help':
            help_text = """🤖 <b>Polymarket Edge Bot Commands</b>

<b>Control:</b>
/pause - Pause monitoring
/resume - Resume monitoring
/status - Show bot status

<b>Settings:</b>
/interval [seconds] - Set scan interval
/thresholds - View current thresholds
/set [param] [value] - Update threshold

<b>Info:</b>
/stats - Show detection statistics
/help - Show this message

<b>Available threshold parameters:</b>
• fresh_wallet_days
• fresh_wallet_min_value
• unusual_size_multiplier
• niche_volume_max
• pre_move_min_value
• win_rate_min_value"""
            self.send_telegram(help_text)
        
        elif text == '/pause':
            self.is_paused = True
            self.send_telegram("⏸️ Monitoring paused. Use /resume to continue.")
        
        elif text == '/resume':
            self.is_paused = False
            self.send_telegram("▶️ Monitoring resumed.")
        
        elif text == '/status':
            status = "▶️ Active" if not self.is_paused else "⏸️ Paused"
            stats_text = f"""📊 <b>Bot Status</b>

Status: {status}
Scan interval: {self.scan_interval}s
Wallets tracked: {len(self.wallet_history)}
Markets tracked: {len(self.market_volumes)}
Alerts sent: {len(self.sent_alerts)}"""
            self.send_telegram(stats_text)
        
        elif text.startswith('/interval'):
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                new_interval = int(parts[1])
                if 10 <= new_interval <= 600:
                    self.scan_interval = new_interval
                    self.send_telegram(f"✅ Scan interval set to {new_interval} seconds")
                else:
                    self.send_telegram("❌ Interval must be between 10 and 600 seconds")
            else:
                self.send_telegram(f"Current interval: {self.scan_interval}s\nUsage: /interval [seconds]")
        
        elif text == '/thresholds':
            thresh_text = "<b>Current Thresholds:</b>\n\n"
            for key, value in self.thresholds.items():
                thresh_text += f"• {key}: {value}\n"
            thresh_text += "\nUse /set [param] [value] to change"
            self.send_telegram(thresh_text)
        
        elif text.startswith('/set'):
            parts = text.split()
            if len(parts) == 3:
                param = parts[1]
                try:
                    value = float(parts[2])
                    if param in self.thresholds:
                        self.thresholds[param] = value
                        self.send_telegram(f"✅ Set {param} = {value}")
                    else:
                        self.send_telegram(f"❌ Unknown parameter: {param}")
                except ValueError:
                    self.send_telegram("❌ Invalid value. Must be a number.")
            else:
                self.send_telegram("Usage: /set [parameter] [value]")
        
        elif text == '/stats':
            total_trades = sum(len(trades) for trades in self.wallet_history.values())
            
            stats_text = f"""📈 <b>Detection Statistics</b>

Total wallets: {len(self.wallet_history)}
Total trades tracked: {total_trades}
Markets monitored: {len(self.market_volumes)}
Alerts sent: {len(self.sent_alerts)}

Bot running for this session."""
            self.send_telegram(stats_text)
    
    def listen_for_commands(self):
        """Background thread to listen for Telegram commands"""
        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.last_update_id = update['update_id']
                    if 'message' in update:
                        message = update['message']
                        if message.get('chat', {}).get('id') == int(self.chat_id):
                            self.process_command(message)
                time.sleep(1)
            except Exception as e:
                print(f"Error in command listener: {e}")
                time.sleep(5)
    
    def get_markets(self, limit=100):
        """Fetch active markets"""
        url = f"{self.gamma_url}/markets"
        params = {"limit": limit, "active": True}
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []
    
    def get_market_trades(self, condition_id, limit=100):
        """Fetch recent trades for a market"""
        url = f"{self.base_url}/trades"
        params = {"condition_id": condition_id, "limit": limit}
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"Error fetching trades: {e}")
            return []
    
    def get_wallet_age(self, address):
        """Estimate wallet age from first trade"""
        if address in self.wallet_history:
            first_seen = self.wallet_history[address][0]['timestamp']
            age_days = (datetime.now() - datetime.fromisoformat(first_seen)).days
            return age_days
        return None
    
    def analyze_trade(self, trade, market_data):
        """Analyze a single trade for suspicious patterns"""
        alerts = []
        
        wallet = trade.get('maker_address', 'unknown')
        size = float(trade.get('size', 0))
        price = float(trade.get('price', 0))
        value = size * price
        timestamp = trade.get('timestamp', datetime.now().isoformat())
        outcome = trade.get('outcome', 'unknown')
        
        alert_key = f"{wallet}_{market_data.get('condition_id')}_{timestamp}"
        if alert_key in self.sent_alerts:
            return []
        
        self.wallet_history[wallet].append({
            'timestamp': timestamp,
            'market': market_data.get('question', 'unknown'),
            'market_id': market_data.get('condition_id'),
            'size': size,
            'value': value,
            'price': price,
            'outcome': outcome
        })
        
        market_id = market_data.get('condition_id')
        if market_id:
            self.market_prices[market_id].append({
                'timestamp': timestamp,
                'price': price
            })
            if len(self.market_prices[market_id]) > 200:
                self.market_prices[market_id].pop(0)
        
        wallet_age = self.get_wallet_age(wallet)
        if (wallet_age is not None and 
            wallet_age < self.thresholds['fresh_wallet_days'] and 
            value > self.thresholds['fresh_wallet_min_value']):
            alerts.append({
                'type': 'FRESH_WALLET_LARGE_BET',
                'wallet': wallet,
                'age_days': wallet_age,
                'value': value,
                'market': market_data.get('question', 'unknown'),
                'key': alert_key
            })
        
        if market_id:
            recent_trades = self.market_volumes.get(market_id, [])
            if len(recent_trades) > 10:
                avg_size = sum(recent_trades) / len(recent_trades)
                if size > avg_size * self.thresholds['unusual_size_multiplier']:
                    alerts.append({
                        'type': 'UNUSUAL_SIZE',
                        'wallet': wallet,
                        'size': size,
                        'avg_size': avg_size,
                        'market': market_data.get('question', 'unknown'),
                        'key': alert_key
                    })
            
            self.market_volumes[market_id].append(size)
            if len(self.market_volumes[market_id]) > 100:
                self.market_volumes[market_id].pop(0)
        
        wallet_trades = self.wallet_history[wallet]
        same_market_trades = [t for t in wallet_trades if t['market'] == market_data.get('question')]
        
        volume = float(market_data.get('volume', 0))
        if (len(same_market_trades) > self.thresholds['niche_trades_min'] and 
            volume < self.thresholds['niche_volume_max']):
            alerts.append({
                'type': 'REPEAT_NICHE_PLAYER',
                'wallet': wallet,
                'trades_count': len(same_market_trades),
                'market_volume': volume,
                'market': market_data.get('question', 'unknown'),
                'key': alert_key
            })
        
        self.wallet_outcomes[wallet].append({
            'market_id': market_id,
            'outcome': outcome,
            'price': price
        })
        
        if len(self.wallet_outcomes[wallet]) >= 10:
            high_conviction_trades = [
                t for t in self.wallet_outcomes[wallet][-20:]
                if t['price'] > 0.8 or t['price'] < 0.2
            ]
            
            if (len(high_conviction_trades) >= self.thresholds['win_rate_conviction_min'] and 
                value > self.thresholds['win_rate_min_value']):
                alerts.append({
                    'type': 'HIGH_WIN_RATE_TRADER',
                    'wallet': wallet,
                    'conviction_trades': len(high_conviction_trades),
                    'total_trades': len(self.wallet_outcomes[wallet]),
                    'current_market': market_data.get('question', 'unknown'),
                    'current_price': price,
                    'value': value,
                    'key': alert_key
                })
        
        if market_id and value > self.thresholds['pre_move_min_value']:
            recent_prices = self.market_prices.get(market_id, [])
            if len(recent_prices) > 10:
                now = datetime.fromisoformat(timestamp)
                last_30_min = [
                    p for p in recent_prices
                    if (now - datetime.fromisoformat(p['timestamp'])).total_seconds() < 1800
                ]
                
                if len(last_30_min) >= 5:
                    old_price = last_30_min[0]['price']
                    price_change = abs(price - old_price)
                    
                    if price_change > self.thresholds['pre_move_change_pct']:
                        alerts.append({
                            'type': 'PRE_MOVE_POSITIONING',
                            'wallet': wallet,
                            'value': value,
                            'old_price': old_price,
                            'new_price': price,
                            'price_change': price_change * 100,
                            'market': market_data.get('question', 'unknown'),
                            'key': alert_key
                        })
        
        if market_id and value > self.thresholds['coordinated_min_value']:
            now = datetime.fromisoformat(timestamp)
            
            similar_recent = []
            for w, trades in self.wallet_history.items():
                if w == wallet:
                    continue
                for t in trades[-5:]:
                    if t['market_id'] == market_id and t['outcome'] == outcome:
                        trade_time = datetime.fromisoformat(t['timestamp'])
                        if abs((now - trade_time).total_seconds()) < 300:
                            similar_recent.append(w)
            
            unique_wallets = set(similar_recent)
            if len(unique_wallets) + 1 >= self.thresholds['coordinated_min_wallets']:
                alerts.append({
                    'type': 'COORDINATED_ENTRY',
                    'wallet': wallet,
                    'coordinated_wallets': len(unique_wallets) + 1,
                    'outcome': outcome,
                    'market': market_data.get('question', 'unknown'),
                    'value': value,
                    'key': alert_key
                })
        
        for alert in alerts:
            self.sent_alerts.add(alert['key'])
        
        return alerts
    
    def format_alert(self, alert):
        """Format alert for Telegram"""
        alert_type = alert['type']
        wallet_short = alert['wallet'][:8] + '...' + alert['wallet'][-6:]
        market = alert['market'][:100]
        
        if alert_type == 'FRESH_WALLET_LARGE_BET':
            return f"""🚨 <b>FRESH WALLET LARGE BET</b>

Wallet: <code>{wallet_short}</code>
Age: {alert['age_days']} days
Value: ${alert['value']:.2f}

Market: {market}"""
            
        elif alert_type == 'UNUSUAL_SIZE':
            return f"""📊 <b>UNUSUAL POSITION SIZE</b>

Wallet: <code>{wallet_short}</code>
Size: {alert['size']:.2f} (avg: {alert['avg_size']:.2f})
Multiplier: {alert['size']/alert['avg_size']:.1f}x

Market: {market}"""
            
        elif alert_type == 'REPEAT_NICHE_PLAYER':
            return f"""🎯 <b>REPEAT NICHE PLAYER</b>

Wallet: <code>{wallet_short}</code>
Trades: {alert['trades_count']} in this market
Volume: ${alert['market_volume']:.2f}

Market: {market}"""
        
        elif alert_type == 'HIGH_WIN_RATE_TRADER':
            return f"""🏆 <b>HIGH WIN RATE TRADER</b>

Wallet: <code>{wallet_short}</code>
Track record: {alert['conviction_trades']}/{alert['total_trades']} conviction trades
Entry: {alert['current_price']:.3f}
Value: ${alert['value']:.2f}

Market: {market}"""
        
        elif alert_type == 'PRE_MOVE_POSITIONING':
            return f"""⚡ <b>PRE-MOVE POSITIONING</b>

Wallet: <code>{wallet_short}</code>
Value: ${alert['value']:.2f}
Price move: {alert['old_price']:.3f} → {alert['new_price']:.3f}
Change: {alert['price_change']:.1f}%

Market: {market}"""
        
        elif alert_type == 'COORDINATED_ENTRY':
            return f"""🤝 <b>COORDINATED ENTRY</b>

Wallets: {alert['coordinated_wallets']} trading together
Lead: <code>{wallet_short}</code>
Value: ${alert['value']:.2f}
Outcome: {alert['outcome']}

Market: {market}"""
        
        return ""
    
    def scan_markets(self):
        """Main scanning loop"""
        if self.is_paused:
            return []
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning markets...")
        
        markets = self.get_markets(limit=50)
        new_alerts = []
        
        for market in markets:
            condition_id = market.get('condition_id')
            if not condition_id:
                continue
            
            trades = self.get_market_trades(condition_id, limit=20)
            
            for trade in trades:
                alerts = self.analyze_trade(trade, market)
                new_alerts.extend(alerts)
        
        if new_alerts:
            print(f"Found {len(new_alerts)} new alerts, sending to Telegram...")
            for alert in new_alerts:
                message = self.format_alert(alert)
                self.send_telegram(message)
                time.sleep(0.5)
        
        return new_alerts
    
    def run(self):
        """Run continuous monitoring with command listening"""
        startup_msg = """🤖 <b>Polymarket Edge Bot Started</b>

Monitoring for:
• Fresh wallets with large bets
• Unusual position sizing
• Repeat niche market players
• High win rate traders
• Pre-move positioning
• Coordinated entries

Use /help to see available commands"""
        
        self.send_telegram(startup_msg)
        print("Bot started. Alerts will be sent to Telegram.")
        print("Listening for commands...")
        
        command_thread = threading.Thread(target=self.listen_for_commands, daemon=True)
        command_thread.start()
        
        while True:
            try:
                self.scan_markets()
                time.sleep(self.scan_interval)
            except KeyboardInterrupt:
                self.send_telegram("🛑 Bot stopped by user")
                print("\nBot stopped")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(self.scan_interval)


# ============================================
# PUT YOUR TELEGRAM BOT TOKEN HERE
# ============================================
TELEGRAM_TOKEN = "8362537374:AAHMrYIPWjuEMHRGuuA6zZty18fnWbYA8Y8"

# ============================================
# PUT YOUR CHAT ID HERE
# ============================================
CHAT_ID = "2102682028"

# You don't need these for monitoring
API_KEY = None
SECRET = None
PASSPHRASE = None

# Start the bot
bot = PolymarketTelegramBot(
    telegram_token=TELEGRAM_TOKEN,
    chat_id=CHAT_ID,
    api_key=API_KEY,
    secret=SECRET,
    passphrase=PASSPHRASE
)

bot.run()
