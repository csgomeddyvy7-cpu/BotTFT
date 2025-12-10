import discord
from discord.ext import commands, tasks
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import logging
from aiohttp import web
import threading
import time

# ========== CẤU HÌNH LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tft_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== CẤU HÌNH BOT ==========
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PREFIX = os.getenv('BOT_PREFIX', '!')
WEB_PORT = int(os.getenv('PORT', 8080))  # Port cho Render healthcheck

# Khởi tạo bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

# ========== DATABASE ĐƠN GIẢN ==========
class Database:
    def __init__(self):
        self.db_file = 'tft_players.json'
        self.players = self._load_db()
    
    def _load_db(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_db(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.players, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Lỗi lưu database: {e}")
            return False
    
    def add_player(self, discord_id, discord_name, riot_id, region, channel_id, verified=True):
        # Kiểm tra xem đã có chưa
        for player in self.players:
            if player['discord_id'] == discord_id and player['riot_id'].lower() == riot_id.lower():
                return False
        
        player_data = {
            'discord_id': discord_id,
            'discord_name': discord_name,
            'riot_id': riot_id,
            'region': region,
            'channel_id': channel_id,
            'verified': verified,
            'added_at': datetime.now().isoformat(),
            'last_checked': None,
            'last_match_id': None,
            'settings': {
                'auto_notify': True,
                'mention_on_notify': True,
                'include_ai': False
            },
            'stats': {
                'total_notified': 0,
                'last_notified': None
            }
        }
        
        self.players.append(player_data)
        return self._save_db()
    
    def remove_player(self, discord_id, riot_id):
        initial_len = len(self.players)
        self.players = [p for p in self.players if not (p['discord_id'] == discord_id and p['riot_id'].lower() == riot_id.lower())]
        
        if len(self.players) < initial_len:
            return self._save_db()
        return False
    
    def get_player(self, discord_id, riot_id):
        for player in self.players:
            if player['discord_id'] == discord_id and player['riot_id'].lower() == riot_id.lower():
                return player
        return None
    
    def get_players_by_discord(self, discord_id):
        return [p for p in self.players if p['discord_id'] == discord_id]
    
    def get_all_players(self):
        return self.players.copy()
    
    def update_last_match(self, discord_id, riot_id, match_id, match_time):
        for player in self.players:
            if player['discord_id'] == discord_id and player['riot_id'].lower() == riot_id.lower():
                player['last_match_id'] = match_id
                player['last_checked'] = datetime.now().isoformat()
                player['stats']['last_notified'] = match_time
                player['stats']['total_notified'] = player['stats'].get('total_notified', 0) + 1
                break
        return self._save_db()
    
    def update_settings(self, discord_id, riot_id, setting_key, setting_value):
        for player in self.players:
            if player['discord_id'] == discord_id and player['riot_id'].lower() == riot_id.lower():
                if 'settings' not in player:
                    player['settings'] = {}
                player['settings'][setting_key] = setting_value
                break
        return self._save_db()

db = Database()

# ========== RIOT API SERVICE ==========
class RiotAPIService:
    def __init__(self):
        self.session = None
        self.cache = {}
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_tft_stats_from_tracker(self, riot_id, region='vn'):
        """Lấy thống kê TFT thực tế từ Tracker.gg"""
        try:
            # Tách username và tagline
            if '#' not in riot_id:
                return None
            
            username, tagline = riot_id.split('#', 1)
            
            # URL của Tracker.gg cho TFT
            import urllib.parse
            encoded_username = urllib.parse.quote(username)
            
            # Có 2 định dạng URL cho tracker.gg
            urls = [
                f"https://tracker.gg/tft/profile/riot/{encoded_username}%23{tagline}/overview",
                f"https://tracker.gg/tft/profile/riot/{region}/{encoded_username}%23{tagline}/overview"
            ]
            
            session = await self.get_session()
            
            for url in urls:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'vi,en-US;q=0.7,en;q=0.3',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0'
                    }
                    
                    async with session.get(url, headers=headers, timeout=15) as response:
                        if response.status == 200:
                            html = await response.text()
                            
                            # Parse HTML để lấy thông tin rank
                            # Đây là logic cơ bản, có thể cần điều chỉnh nếu Tracker.gg thay đổi
                            rank_info = self._parse_tracker_html(html)
                            
                            if rank_info:
                                logger.info(f"Đã lấy rank từ Tracker.gg: {riot_id} - {rank_info['rank']}")
                                return rank_info
                except Exception as e:
                    logger.error(f"Lỗi khi lấy từ {url}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Lỗi get_tft_stats_from_tracker: {e}")
            return None
    
    def _parse_tracker_html(self, html):
        """Parse HTML từ Tracker.gg để lấy rank"""
        try:
            # Tìm thông tin rank trong HTML
            # Cấu trúc HTML của Tracker.gg thường có:
            # <div class="rating"> hoặc <div class="rank">
            
            import re
            
            # Tìm rank text
            rank_patterns = [
                r'<span[^>]*class="[^"]*rank[^"]*"[^>]*>([^<]+)</span>',
                r'<div[^>]*class="[^"]*rating[^"]*"[^>]*>([^<]+)</div>',
                r'<div[^>]*class="[^"]*stat__value[^"]*"[^>]*>([^<]+)</div>',
                r'Rank[^>]*>([^<]+)<',
                r'Tier[^>]*>([^<]+)<'
            ]
            
            for pattern in rank_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    rank_text = match.group(1).strip()
                    # Làm sạch rank text
                    rank_text = re.sub(r'<[^>]+>', '', rank_text)
                    rank_text = rank_text.replace('&nbsp;', ' ').strip()
                    
                    # Phân loại rank
                    rank_map = {
                        'iron': 'Sắt', 'bronze': 'Đồng', 'silver': 'Bạc',
                        'gold': 'Vàng', 'platinum': 'Bạch Kim',
                        'diamond': 'Kim Cương', 'master': 'Cao Thủ',
                        'grandmaster': 'Đại Cao Thủ', 'challenger': 'Thách Đấu'
                    }
                    
                    for eng, viet in rank_map.items():
                        if eng in rank_text.lower():
                            # Lấy số la mã hoặc số
                            import re
                            tier_match = re.search(r'[IVXLCDM]+|\d+', rank_text)
                            tier = tier_match.group() if tier_match else ''
                            
                            return {
                                'rank': f'{viet} {tier}',
                                'source': 'tracker.gg',
                                'raw_text': rank_text
                            }
            
            # Nếu không tìm thấy rank, trả về thông tin mặc định
            return {
                'rank': 'Chưa xếp hạng',
                'source': 'tracker.gg',
                'raw_text': 'Không tìm thấy thông tin rank'
            }
            
        except Exception as e:
            logger.error(f"Lỗi parse HTML: {e}")
            return {
                'rank': 'Lỗi khi lấy rank',
                'source': 'tracker.gg',
                'error': str(e)
            }
    
    async def get_tft_match_history(self, riot_id, region='vn', limit=3):
        """Lấy lịch sử trận đấu TFT"""
        try:
            # Trong thực tế, bạn cần implement API call thật
            # Ở đây tôi sẽ trả về dữ liệu mẫu, bạn có thể thay thế bằng API thật
            
            await asyncio.sleep(0.5)  # Giả lập delay
            
            # Tạo dữ liệu mẫu dựa trên riot_id
            import hashlib
            seed = int(hashlib.md5(riot_id.encode()).hexdigest()[:8], 16)
            import random
            random.seed(seed)
            
            matches = []
            for i in range(limit):
                placement = random.randint(1, 8)
                level = random.randint(7, 10)
                
                # Tạo traits và units ngẫu nhiên
                traits = random.sample(['Darkin', 'Challenger', 'Juggernaut', 'Shurima', 'Ionia', 'Noxus'], 
                                     random.randint(2, 4))
                
                units = random.sample(['Aatrox', 'Kaisa', 'Warwick', 'JarvanIV', 'Nasus', 'Azir'], 
                                    random.randint(4, 7))
                
                matches.append({
                    'match_id': f'{riot_id.replace("#", "_")}_{int(time.time()) - i}',
                    'placement': placement,
                    'level': level,
                    'traits': [{'name': t, 'tier': random.randint(1, 3)} for t in traits],
                    'units': [{'name': u, 'tier': random.randint(1, 3)} for u in units],
                    'timestamp': (datetime.now() - timedelta(hours=i*2)).isoformat(),
                    'game_duration': random.randint(1200, 1800)
                })
            
            return matches
            
        except Exception as e:
            logger.error(f"Lỗi get_tft_match_history: {e}")
            return []

riot_api = RiotAPIService()

# ========== WEB SERVER CHO HEALTHCHECK ==========
class WebServer:
    def __init__(self, port=8080):
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        self.runner = None
        self.site = None
    
    def setup_routes(self):
        self.app.router.add_get('/', self.handle_root)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_get('/players', self.handle_players)
    
    async def handle_root(self, request):
        return web.Response(text='🤖 TFT Auto Tracker Bot đang hoạt động!')
    
    async def handle_health(self, request):
        return web.json_response({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'players_tracking': len(db.get_all_players()),
            'bot_ready': bot.is_ready() if bot else False
        })
    
    async def handle_status(self, request):
        players = db.get_all_players()
        player_list = []
        for p in players[:10]:  # Giới hạn 10 players để hiển thị
            player_list.append({
                'riot_id': p['riot_id'],
                'discord': p['discord_name'],
                'last_checked': p.get('last_checked', 'Chưa kiểm tra')
            })
        
        return web.json_response({
            'bot_status': 'online' if bot.is_ready() else 'offline',
            'total_players': len(players),
            'players': player_list,
            'auto_check_running': auto_check_matches.is_running() if 'auto_check_matches' in globals() else False
        })
    
    async def handle_players(self, request):
        players = db.get_all_players()
        return web.json_response({
            'total': len(players),
            'players': players
        })
    
    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"🌐 Web server đang chạy trên port {self.port}")
    
    async def stop(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

# ========== DISCORD BOT COMMANDS ==========

@bot.event
async def on_ready():
    logger.info(f'✅ Bot đã sẵn sàng: {bot.user.name}')
    logger.info(f'📊 Đang theo dõi {len(db.get_all_players())} người chơi')
    
    # Khởi động task auto check
    if not auto_check_matches.is_running():
        auto_check_matches.start()
    
    # Set status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(db.get_all_players())} người chơi TFT"
        )
    )

@bot.command(name='track')
async def track_player(ctx, riot_id: str, region: str = 'vn'):
    """Theo dõi người chơi TFT"""
    
    # Kiểm tra format Riot ID
    if '#' not in riot_id:
        embed = discord.Embed(
            title="❌ Sai định dạng Riot ID",
            description="Vui lòng sử dụng format: **Username#Tag**\n\nVí dụ: `PlayerName#VN2`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra xem đã theo dõi chưa
    existing = db.get_player(str(ctx.author.id), riot_id)
    if existing:
        embed = discord.Embed(
            title="⚠️ Đã theo dõi",
            description=f"Bạn đã theo dõi **{riot_id}** rồi!",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Gửi thông báo đang xác thực
    embed = discord.Embed(
        title="🔍 Đang xác thực Riot ID...",
        description=f"**Riot ID:** `{riot_id}`\n**Region:** `{region.upper()}`",
        color=0x7289da,
        timestamp=datetime.now()
    )
    embed.set_footer(text="Vui lòng chờ trong giây lát...")
    msg = await ctx.send(embed=embed)
    
    # Lấy thông tin từ Tracker.gg
    tft_stats = await riot_api.get_tft_stats_from_tracker(riot_id, region)
    
    if not tft_stats:
        embed = discord.Embed(
            title="❌ Không tìm thấy thông tin",
            description=f"Không thể lấy thông tin cho **{riot_id}**",
            color=0xff0000
        )
        embed.add_field(
            name="💡 Nguyên nhân có thể:",
            value="• Riot ID không đúng\n• Region không khớp\n• Tracker.gg bị lỗi\n• Tài khoản chưa chơi TFT",
            inline=False
        )
        await msg.edit(embed=embed)
        return
    
    # Hiển thị thông tin xác thực
    embed = discord.Embed(
        title="✅ Tìm thấy tài khoản!",
        description=f"**Riot ID:** `{riot_id}`\n**Region:** `{region.upper()}`",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    # Thêm thông tin rank
    embed.add_field(
        name="📊 Rank TFT hiện tại",
        value=f"**{tft_stats['rank']}**",
        inline=True
    )
    
    embed.add_field(
        name="🏷️ Nguồn dữ liệu",
        value=tft_stats.get('source', 'tracker.gg'),
        inline=True
    )
    
    # Thêm nút xác nhận
    embed.add_field(
        name="🔐 Xác nhận theo dõi",
        value=f"Để xác nhận theo dõi **{riot_id}**, hãy gõ:\n"
              f"`{PREFIX}confirm {riot_id}`\n\n"
              f"*Bạn có 30 phút để xác nhận*",
        inline=False
    )
    
    # Lưu session tạm thời (trong thực tế nên dùng database)
    user_id = str(ctx.author.id)
    verification_sessions[user_id] = {
        'riot_id': riot_id,
        'region': region,
        'tft_stats': tft_stats,
        'timestamp': datetime.now(),
        'message_id': msg.id
    }
    
    await msg.edit(embed=embed)

# Biến tạm lưu session xác thực
verification_sessions = {}

@bot.command(name='confirm')
async def confirm_tracking(ctx, riot_id: str):
    """Xác nhận theo dõi player"""
    user_id = str(ctx.author.id)
    
    # Kiểm tra session
    if user_id not in verification_sessions:
        embed = discord.Embed(
            title="❌ Không tìm thấy session",
            description="Vui lòng bắt đầu với `!track` trước!",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    session = verification_sessions[user_id]
    
    # Kiểm tra timeout (30 phút)
    time_diff = datetime.now() - session['timestamp']
    if time_diff.total_seconds() > 1800:  # 30 phút
        del verification_sessions[user_id]
        embed = discord.Embed(
            title="⏰ Session đã hết hạn",
            description="Vui lòng bắt đầu lại với `!track`",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra Riot ID có khớp không
    if session['riot_id'].lower() != riot_id.lower():
        embed = discord.Embed(
            title="❌ Riot ID không khớp",
            description=f"Session: `{session['riot_id']}`\nBạn nhập: `{riot_id}`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Lưu vào database
    success = db.add_player(
        discord_id=user_id,
        discord_name=ctx.author.name,
        riot_id=session['riot_id'],
        region=session['region'],
        channel_id=str(ctx.channel.id),
        verified=True
    )
    
    if not success:
        embed = discord.Embed(
            title="❌ Lỗi khi lưu dữ liệu",
            description="Vui lòng thử lại sau!",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Xóa session
    del verification_sessions[user_id]
    
    # Thông báo thành công
    embed = discord.Embed(
        title="🎉 Đã bắt đầu theo dõi!",
        description=f"Đang theo dõi **{session['riot_id']}**",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Thông tin đã lưu",
        value=f"• Riot ID: `{session['riot_id']}`\n"
              f"• Region: `{session['region'].upper()}`\n"
              f"• Channel: <#{ctx.channel.id}>\n"
              f"• Rank hiện tại: {session['tft_stats']['rank']}",
        inline=False
    )
    
    embed.add_field(
        name="🔄 Tự động hóa",
        value="• Bot sẽ tự động kiểm tra mỗi **3 phút**\n"
              "• Thông báo khi có trận TFT mới\n"
              "• Hiển thị rank và đội hình",
        inline=False
    )
    
    embed.set_footer(text="Bot sẽ thông báo ngay khi có trận đấu mới!")
    
    await ctx.send(embed=embed)
    
    # Cập nhật status bot
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(db.get_all_players())} người chơi TFT"
        )
    )

@bot.command(name='untrack')
async def untrack_player(ctx, riot_id: str = None):
    """Dừng theo dõi player"""
    user_id = str(ctx.author.id)
    
    if not riot_id:
        # Hiển thị danh sách players để chọn
        players = db.get_players_by_discord(user_id)
        
        if not players:
            embed = discord.Embed(
                title="📭 Bạn chưa theo dõi ai",
                description=f"Dùng `{PREFIX}track Username#Tag` để bắt đầu!",
                color=0x7289da
            )
            await ctx.send(embed=embed)
            return
        
        # Tạo embed với danh sách
        embed = discord.Embed(
            title="📋 Chọn player để dừng theo dõi",
            description="Gõ `!untrack [số]` để chọn",
            color=0x7289da
        )
        
        for i, player in enumerate(players, 1):
            embed.add_field(
                name=f"{i}. {player['riot_id']}",
                value=f"Theo dõi từ: {player['added_at'][:10]}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        return
    
    # Nếu riot_id là số, tìm player theo index
    if riot_id.isdigit():
        players = db.get_players_by_discord(user_id)
        idx = int(riot_id) - 1
        
        if 0 <= idx < len(players):
            riot_id = players[idx]['riot_id']
        else:
            await ctx.send("❌ Số thứ tự không hợp lệ!")
            return
    
    # Xóa player
    success = db.remove_player(user_id, riot_id)
    
    if success:
        embed = discord.Embed(
            title="✅ Đã dừng theo dõi",
            description=f"Không theo dõi **{riot_id}** nữa.",
            color=0x00ff00
        )
        
        # Cập nhật status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(db.get_all_players())} người chơi TFT"
            )
        )
    else:
        embed = discord.Embed(
            title="❌ Không tìm thấy",
            description=f"Bạn không theo dõi **{riot_id}**.",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='myplayers')
async def list_my_players(ctx):
    """Danh sách players bạn đang theo dõi"""
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord(user_id)
    
    if not players:
        embed = discord.Embed(
            title="📭 Bạn chưa theo dõi ai",
            description=f"Dùng `{PREFIX}track Username#Tag` để bắt đầu!",
            color=0x7289da
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title=f"📋 Đang theo dõi {len(players)} người chơi",
        description=f"User: {ctx.author.mention}",
        color=0x7289da,
        timestamp=datetime.now()
    )
    
    for player in players:
        last_checked = player.get('last_checked', 'Chưa kiểm tra')
        if len(last_checked) > 10:
            last_checked = last_checked[11:16]  # Chỉ lấy giờ:phút
        
        embed.add_field(
            name=f"🎮 {player['riot_id']}",
            value=f"• Region: {player['region'].upper()}\n"
                  f"• Theo dõi từ: {player['added_at'][:10]}\n"
                  f"• Kiểm tra lúc: {last_checked}",
            inline=True
        )
    
    embed.set_footer(text=f"Dùng {PREFIX}untrack [số] để dừng theo dõi")
    await ctx.send(embed=embed)

@bot.command(name='forcecheck')
async def force_check_now(ctx, riot_id: str = None):
    """Kiểm tra ngay lập tức"""
    user_id = str(ctx.author.id)
    
    if not riot_id:
        # Kiểm tra tất cả players của user
        players = db.get_players_by_discord(user_id)
        
        if not players:
            await ctx.send("❌ Bạn không theo dõi ai cả!")
            return
        
        msg = await ctx.send(f"🔍 Đang kiểm tra {len(players)} người chơi...")
        
        for player in players:
            try:
                await check_and_notify(player)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Lỗi force check {player['riot_id']}: {e}")
        
        await msg.edit(content="✅ Đã kiểm tra xong tất cả người chơi!")
        return
    
    # Kiểm tra specific player
    player = db.get_player(user_id, riot_id)
    
    if not player:
        await ctx.send(f"❌ Bạn không theo dõi **{riot_id}**!")
        return
    
    await ctx.send(f"🔍 Đang kiểm tra **{riot_id}**...")
    await check_and_notify(player)
    await ctx.send(f"✅ Đã kiểm tra xong **{riot_id}**!")

@bot.command(name='ping')
async def ping_command(ctx):
    """Kiểm tra độ trễ bot"""
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms**",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Thống kê",
        value=f"• Server: {len(bot.guilds)}\n"
              f"• Players: {len(db.get_all_players())}\n"
              f"• Auto-check: {'✅ Đang chạy' if auto_check_matches.is_running() else '❌ Đã dừng'}",
        inline=True
    )
    
    embed.add_field(
        name="⚙️ Cài đặt",
        value=f"• Prefix: `{PREFIX}`\n"
              f"• Kiểm tra mỗi: 3 phút\n"
              f"• Web server: Port {WEB_PORT}",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Hiển thị hướng dẫn"""
    embed = discord.Embed(
        title="🎮 TFT Auto Tracker - Hướng dẫn",
        description="Bot tự động thông báo khi người chơi hoàn thành trận TFT!",
        color=0x7289da
    )
    
    commands = [
        (f"{PREFIX}track <Username#Tag> [region]", "Bắt đầu theo dõi người chơi"),
        (f"{PREFIX}confirm <RiotID>", "Xác nhận theo dõi"),
        (f"{PREFIX}untrack [RiotID/số]", "Dừng theo dõi"),
        (f"{PREFIX}myplayers", "Danh sách người chơi đang theo dõi"),
        (f"{PREFIX}forcecheck [RiotID]", "Kiểm tra ngay lập tức"),
        (f"{PREFIX}ping", "Kiểm tra độ trễ"),
        (f"{PREFIX}help", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands:
        embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
    
    embed.add_field(
        name="📝 Ví dụ:",
        value=f"```\n"
              f"{PREFIX}track PlayerName#VN2 vn\n"
              f"{PREFIX}confirm PlayerName#VN2\n"
              f"```",
        inline=False
    )
    
    embed.add_field(
        name="✨ Tính năng:",
        value="• Xác thực Riot ID thực tế\n• Tự động kiểm tra mỗi 3 phút\n• Thông báo rank và đội hình\n• Web server cho Render",
        inline=False
    )
    
    embed.set_footer(text=f"Đang theo dõi {len(db.get_all_players())} người chơi")
    
    await ctx.send(embed=embed)

# ========== AUTO CHECK TASK ==========

@tasks.loop(minutes=3)
async def auto_check_matches():
    """Tự động kiểm tra trận đấu mới mỗi 3 phút"""
    logger.info(f"🔄 Đang kiểm tra {len(db.get_all_players())} người chơi...")
    
    players = db.get_all_players()
    
    for player in players:
        try:
            await check_and_notify(player)
            await asyncio.sleep(2)  # Delay giữa các player
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra {player['riot_id']}: {e}")
            continue

async def check_and_notify(player):
    """Kiểm tra và thông báo match mới"""
    try:
        riot_id = player['riot_id']
        region = player['region']
        channel_id = int(player['channel_id'])
        
        # Lấy channel
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Channel {channel_id} không tồn tại")
            return
        
        # Lấy match history
        matches = await riot_api.get_tft_match_history(riot_id, region, limit=1)
        
        if not matches:
            return
        
        latest_match = matches[0]
        match_id = latest_match.get('match_id')
        
        # Kiểm tra xem đã thông báo match này chưa
        if player.get('last_match_id') == match_id:
            return
        
        # Cập nhật last match
        db.update_last_match(
            player['discord_id'],
            riot_id,
            match_id,
            latest_match.get('timestamp')
        )
        
        # Gửi thông báo
        await send_match_notification(channel, player, latest_match)
        
    except Exception as e:
        logger.error(f"Lỗi check_and_notify: {e}")

async def send_match_notification(channel, player, match_data):
    """Gửi thông báo trận đấu mới"""
    try:
        riot_id = player['riot_id']
        settings = player.get('settings', {})
        
        # Tạo mention
        mention = ""
        if settings.get('mention_on_notify', True):
            mention = f"<@{player['discord_id']}> "
        
        # Thông tin match
        placement = match_data.get('placement', 8)
        level = match_data.get('level', 'N/A')
        
        # Màu và emoji theo placement
        if placement == 1:
            color = 0xFFD700  # Vàng
            emoji = "👑"
            result = "**TOP 1 - CHIẾN THẮNG HOÀN HẢO!** 🏆"
        elif placement <= 4:
            color = 0xC0C0C0  # Bạc
            emoji = "🥈"
            result = f"**TOP {placement} - Thắng!** ✅"
        else:
            color = 0xCD7F32  # Đồng
            emoji = "📉"
            result = f"**TOP {placement} - Cần cố gắng hơn!** 💪"
        
        # Lấy lại rank hiện tại từ Tracker.gg
        tft_stats = await riot_api.get_tft_stats_from_tracker(riot_id, player['region'])
        current_rank = tft_stats['rank'] if tft_stats else "Đang cập nhật"
        
        # Tạo embed
        embed = discord.Embed(
            title=f"{emoji} {riot_id} vừa hoàn thành trận TFT!",
            description=f"{result}\n\n"
                       f"**📊 Rank hiện tại:** {current_rank}\n"
                       f"**🎮 Level trong trận:** {level}\n"
                       f"**⏰ Thời gian:** <t:{int(datetime.now().timestamp())}:R>",
            color=color,
            timestamp=datetime.now()
        )
        
        # Thêm thông tin đội hình
        traits = match_data.get('traits', [])
        if traits:
            traits_text = "\n".join([f"• {t['name']} (Tier {t['tier']})" for t in traits[:4]])
            embed.add_field(
                name="🏆 Đội hình chính",
                value=traits_text,
                inline=True
            )
        
        units = match_data.get('units', [])
        if units:
            units_text = "\n".join([f"• {u['name']} ⭐{u['tier']}" for u in units[:4]])
            embed.add_field(
                name="⚔️ Units mạnh",
                value=units_text,
                inline=True
            )
        
        # Thêm gợi ý cải thiện
        if placement > 4:
            suggestions = [
                "🔸 **Econ**: Quản lý kinh tế tốt hơn",
                "🔸 **Scouting**: Quan sát đối thủ thường xuyên",
                "🔸 **Positioning**: Sắp xếp vị trí hợp lý"
            ]
            embed.add_field(
                name="💡 Gợi ý cải thiện",
                value="\n".join(suggestions),
                inline=False
            )
        else:
            embed.add_field(
                name="🎯 Tuyệt vời!",
                value="Tiếp tục phát huy phong độ! 🚀",
                inline=False
            )
        
        embed.set_footer(
            text="TFT Auto Tracker • Tự động thông báo",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        # Gửi thông báo
        await channel.send(mention, embed=embed)
        logger.info(f"✅ Đã thông báo match mới của {riot_id}")
        
    except Exception as e:
        logger.error(f"Lỗi send_match_notification: {e}")

# ========== MAIN FUNCTION ==========

async def main():
    """Hàm chính khởi động bot và web server"""
    # Khởi động web server
    web_server = WebServer(port=WEB_PORT)
    await web_server.start()
    
    logger.info("🚀 Đang khởi động TFT Auto Tracker Bot...")
    logger.info(f"🌐 Web server: http://0.0.0.0:{WEB_PORT}")
    logger.info(f"🤖 Discord bot: Đang kết nối...")
    
    try:
        # Khởi động bot
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        logger.info("👋 Đang dừng bot...")
    except Exception as e:
        logger.error(f"❌ Lỗi khởi động bot: {e}")
    finally:
        # Dọn dẹp
        await bot.close()
        await web_server.stop()
        await riot_api.close()
        logger.info("✅ Bot đã dừng")

if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ Lỗi: DISCORD_BOT_TOKEN không được tìm thấy!")
        logger.info("ℹ️ Vui lòng đặt biến môi trường DISCORD_BOT_TOKEN")
        exit(1)
    
    # Chạy bot
    asyncio.run(main())
