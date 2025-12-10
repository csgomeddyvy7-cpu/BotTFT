import discord
from discord.ext import commands, tasks
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import pytz
from bs4 import BeautifulSoup

# Token bot Discord
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Cấu hình bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database đơn giản (có thể nâng cấp lên SQLite sau)
class TFTDatabase:
    def __init__(self):
        self.tracking_list = {}  # {user_id: {summoner_name, region, channel_id}}
        self.last_matches = {}   # {summoner_name: last_match_id}
        self.user_settings = {}  # {user_id: {notifications: True/False}}
    
    def add_tracking(self, user_id, summoner_name, region, channel_id):
        """Thêm người chơi vào danh sách theo dõi"""
        self.tracking_list[user_id] = {
            'summoner_name': summoner_name,
            'region': region,
            'channel_id': channel_id,
            'added_at': datetime.now()
        }
        return True
    
    def remove_tracking(self, user_id):
        """Xóa khỏi danh sách theo dõi"""
        if user_id in self.tracking_list:
            del self.tracking_list[user_id]
            return True
        return False
    
    def get_all_tracking(self):
        """Lấy tất cả người đang được theo dõi"""
        return self.tracking_list
    
    def update_last_match(self, summoner_name, match_id):
        """Cập nhật match cuối cùng"""
        self.last_matches[summoner_name] = match_id
    
    def get_last_match(self, summoner_name):
        """Lấy match cuối cùng đã thông báo"""
        return self.last_matches.get(summoner_name)

db = TFTDatabase()

# ========== TFT API SERVICES ==========

class TFTAPIService:
    """Dịch vụ lấy dữ liệu TFT từ các nguồn khác nhau"""
    
    def __init__(self):
        self.session = None
        self.riot_api_key = os.getenv('RIOT_API_KEY', '')
    
    async def get_session(self):
        """Lấy aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Đóng session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_tft_match_history(self, summoner_name, region='vn'):
        """
        Lấy lịch sử trận đấu TFT
        Phương án 1: Tracker Network (công khai, không cần key)
        """
        try:
            # Mã hóa summoner name cho URL
            import urllib.parse
            encoded_name = urllib.parse.quote(summoner_name)
            
            # Tracker.gg TFT API
            url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{encoded_name}%23{region.upper()}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://tracker.gg",
                "Referer": "https://tracker.gg/"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Xử lý dữ liệu từ Tracker.gg
                    matches = []
                    if 'data' in data and 'segments' in data['data']:
                        for segment in data['data']['segments']:
                            if segment['type'] == 'overview':
                                stats = segment['stats']
                                match_info = {
                                    'rank': stats.get('rank', {}).get('displayValue', 'N/A'),
                                    'placement': stats.get('placement', {}).get('value', 0),
                                    'date': datetime.now().isoformat(),
                                    'match_id': f"tracker_{datetime.now().timestamp()}",
                                    'traits': [],
                                    'units': []
                                }
                                matches.append(match_info)
                    
                    return matches[:5]  # Trả về 5 match gần nhất
                    
        except Exception as e:
            print(f"Lỗi Tracker.gg API: {e}")
        
        # Phương án 2: Lolchess.gg scraping
        try:
            return await self.get_lolchess_stats(summoner_name, region)
        except:
            return []
    
    async def get_lolchess_stats(self, summoner_name, region='vn'):
        """Lấy thống kê từ Lolchess.gg (web scraping)"""
        try:
            # Chuyển đổi region code
            region_map = {
                'vn': 'vn',
                'na': 'na',
                'euw': 'euw',
                'eune': 'eune',
                'kr': 'kr'
            }
            region_code = region_map.get(region.lower(), 'vn')
            
            url = f"https://lolchess.gg/profile/{region_code}/{summoner_name}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Tìm match history
                    matches = []
                    match_elements = soup.find_all('div', class_='profile__match-history__item')
                    
                    for element in match_elements[:5]:  # Lấy 5 match gần nhất
                        try:
                            # Lấy thông tin placement
                            placement_elem = element.find('div', class_='placement')
                            placement = int(placement_elem.text.strip().replace('#', '')) if placement_elem else 8
                            
                            # Lấy traits
                            traits = []
                            trait_elems = element.find_all('div', class_='trait')
                            for trait in trait_elems:
                                trait_name = trait.get('title', '').split('(')[0].strip()
                                if trait_name:
                                    traits.append(trait_name)
                            
                            # Lấy units
                            units = []
                            unit_elems = element.find_all('div', class_='champion')
                            for unit in unit_elems:
                                unit_name = unit.get('title', '').strip()
                                if unit_name:
                                    units.append(unit_name)
                            
                            matches.append({
                                'placement': placement,
                                'traits': traits[:8],  # Giới hạn 8 traits
                                'units': units[:10],   # Giới hạn 10 units
                                'match_id': f"lolchess_{datetime.now().timestamp()}_{placement}",
                                'date': datetime.now().isoformat()
                            })
                        except:
                            continue
                    
                    return matches
        except Exception as e:
            print(f"Lỗi Lolchess.gg: {e}")
        
        return []
    
    async def get_match_details(self, match_id, summoner_name):
        """
        Lấy chi tiết trận đấu TFT
        Nếu có Riot API key, sẽ lấy chi tiết hơn
        """
        if self.riot_api_key and match_id.startswith('RIOT_'):
            try:
                # Dùng Riot API nếu có key
                url = f"https://sea.api.riotgames.com/tft/match/v1/matches/{match_id}"
                headers = {"X-Riot-Token": self.riot_api_key}
                
                session = await self.get_session()
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
            except:
                pass
        
        # Trả về dữ liệu mẫu nếu không có API
        return {
            'info': {
                'game_datetime': datetime.now().timestamp() * 1000,
                'game_length': 1800,
                'participants': []
            }
        }
    
    def analyze_tft_match(self, match_data, summoner_name):
        """Phân tích trận đấu TFT và đưa ra nhận xét"""
        try:
            # Nếu là dữ liệu từ Riot API
            if 'info' in match_data and 'participants' in match_data['info']:
                for participant in match_data['info']['participants']:
                    if participant['puuid'] == summoner_name or participant.get('summoner_name', '').lower() == summoner_name.lower():
                        placement = participant['placement']
                        level = participant['level']
                        traits = participant['traits']
                        units = participant['units']
                        
                        # Tìm traits đã kích hoạt
                        active_traits = []
                        for trait in traits:
                            if trait['tier_current'] > 0:
                                active_traits.append({
                                    'name': trait['name'],
                                    'tier': trait['tier_current'],
                                    'num_units': trait['num_units']
                                })
                        
                        # Sắp xếp traits theo tier
                        active_traits.sort(key=lambda x: x['tier'], reverse=True)
                        
                        return {
                            'placement': placement,
                            'level': level,
                            'traits': active_traits,
                            'units': units,
                            'source': 'riot_api'
                        }
            
            # Dữ liệu từ web scraping
            if isinstance(match_data, dict):
                return {
                    'placement': match_data.get('placement', 8),
                    'level': 0,
                    'traits': [{'name': t, 'tier': 1} for t in match_data.get('traits', [])],
                    'units': [{'character_id': u, 'tier': 1} for u in match_data.get('units', [])],
                    'source': 'web_scraping'
                }
        
        except Exception as e:
            print(f"Lỗi phân tích match: {e}")
        
        return None

tft_service = TFTAPIService()

# ========== DISCORD EMBED HELPERS ==========

def create_tft_match_embed(analysis, summoner_name, match_id=None):
    """Tạo embed Discord cho kết quả TFT"""
    
    placement = analysis['placement']
    level = analysis.get('level', 'N/A')
    
    # Màu sắc theo placement
    if placement == 1:
        color = 0xFFD700  # Vàng - Top 1
        title_icon = "👑"
    elif placement <= 4:
        color = 0xC0C0C0  # Bạc - Top 4
        title_icon = "🥈"
    else:
        color = 0xCD7F32  # Đồng - Top 5-8
        title_icon = "📉"
    
    embed = discord.Embed(
        title=f"{title_icon} TFT Match Result - {summoner_name}",
        description=f"**🏆 Placement:** `#{placement}` | **📊 Level:** `{level}`",
        color=color,
        timestamp=datetime.now()
    )
    
    # Hiển thị traits
    traits = analysis.get('traits', [])
    if traits:
        # Nhóm traits theo tier
        tier_groups = {}
        for trait in traits:
            tier = trait.get('tier', 1)
            if tier not in tier_groups:
                tier_groups[tier] = []
            tier_groups[tier].append(trait.get('name', 'Unknown'))
        
        # Hiển thị traits theo tier
        for tier in sorted(tier_groups.keys(), reverse=True):
            stars = "⭐" * min(tier, 3)
            traits_text = ", ".join(tier_groups[tier][:5])  # Giới hạn 5 traits mỗi tier
            if len(tier_groups[tier]) > 5:
                traits_text += f" (+{len(tier_groups[tier]) - 5} more)"
            
            embed.add_field(
                name=f"{stars} Tier {tier} Traits",
                value=traits_text,
                inline=False
            )
    
    # Hiển thị units
    units = analysis.get('units', [])
    if units:
        units_text = []
        for unit in units[:8]:  # Giới hạn 8 units
            if isinstance(unit, dict):
                unit_name = unit.get('character_id', '').replace('TFT7_', '').replace('_', ' ').title()
                tier = unit.get('tier', 1)
                stars = "★" * tier
                units_text.append(f"{stars} {unit_name}")
            else:
                units_text.append(str(unit))
        
        if units_text:
            embed.add_field(
                name="⚔️ Main Units",
                value="\n".join(units_text[:8]),
                inline=True
            )
    
    # Phân tích và gợi ý
    suggestions = get_tft_suggestions(analysis)
    if suggestions:
        embed.add_field(
            name="💡 Analysis & Suggestions",
            value="\n".join(suggestions),
            inline=False
        )
    
    # Footer
    embed.set_footer(
        text=f"TFT Auto Tracker • {analysis.get('source', 'Unknown source')}",
        icon_url="https://cdn.discordapp.com/emojis/1065110917776146483.webp?size=96&quality=lossless"
    )
    
    return embed

def get_tft_suggestions(analysis):
    """Đưa ra gợi ý dựa trên kết quả trận đấu"""
    placement = analysis['placement']
    level = analysis.get('level', 0)
    traits = analysis.get('traits', [])
    
    suggestions = []
    
    # Gợi ý theo placement
    if placement == 1:
        suggestions.append("🎯 **Perfect game!** Great decision making!")
    elif placement <= 4:
        suggestions.append("✅ **Good result!** You secured a Top 4 finish.")
    else:
        suggestions.append("📉 **Need improvement:** Try to scout opponents more.")
    
    # Gợi ý theo level
    if level < 7 and placement > 4:
        suggestions.append("🔸 **Consider leveling:** Don't stay at low level too long.")
    
    # Gợi ý theo traits
    trait_count = len(traits)
    if trait_count < 3:
        suggestions.append("🔸 **Focus traits:** Try to activate more synergies.")
    elif trait_count > 5:
        suggestions.append("🔸 **Too scattered:** Focus on 3-4 core traits.")
    
    # Gợi ý chung
    suggestions.append("🔸 **Economy:** Maintain 50 gold when possible.")
    suggestions.append("🔸 **Scouting:** Check opponents every round.")
    
    return suggestions

# ========== DISCORD COMMANDS ==========

@bot.event
async def on_ready():
    print(f'✅ TFT Bot đã sẵn sàng: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'📊 Đang theo dõi: {len(db.get_all_tracking())} người chơi')
    
    # Bắt đầu task theo dõi tự động
    if not auto_check_tft_matches.is_running():
        auto_check_tft_matches.start()

@bot.command(name='track', help='Theo dõi tự động TFT match của summoner')
async def track_tft(ctx, summoner_name, region='vn'):
    """Thêm summoner vào danh sách theo dõi tự động"""
    user_id = str(ctx.author.id)
    
    # Kiểm tra xem đã theo dõi chưa
    if user_id in db.tracking_list:
        await ctx.send(f"❌ Bạn đang theo dõi **{db.tracking_list[user_id]['summoner_name']}** rồi!")
        return
    
    # Thêm vào danh sách theo dõi
    db.add_tracking(user_id, summoner_name.lower(), region.lower(), ctx.channel.id)
    
    embed = discord.Embed(
        title="✅ Đã bật theo dõi TFT Auto Tracker",
        description=f"Tôi sẽ thông báo khi **{summoner_name}** hoàn thành trận đấu TFT mới!",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="🎮 Summoner", value=summoner_name, inline=True)
    embed.add_field(name="🌍 Region", value=region.upper(), inline=True)
    embed.add_field(name="📢 Channel", value=f"<#{ctx.channel.id}>", inline=True)
    embed.add_field(
        name="🔄 Kiểm tra",
        value="Bot sẽ tự động kiểm tra mỗi 3 phút",
        inline=False
    )
    
    embed.set_footer(text="Dùng !untrack để dừng theo dõi")
    
    await ctx.send(embed=embed)
    
    # Kiểm tra ngay lập tức một lần
    await check_and_notify_single(summoner_name, region, ctx.channel)

@bot.command(name='untrack', help='Dừng theo dõi TFT match')
async def untrack_tft(ctx):
    """Xóa khỏi danh sách theo dõi"""
    user_id = str(ctx.author.id)
    
    if user_id not in db.tracking_list:
        await ctx.send("❌ Bạn chưa theo dõi ai cả!")
        return
    
    summoner_name = db.tracking_list[user_id]['summoner_name']
    db.remove_tracking(user_id)
    
    embed = discord.Embed(
        title="⏹️ Đã dừng theo dõi",
        description=f"Không theo dõi **{summoner_name}** nữa.",
        color=0xff9900,
        timestamp=datetime.now()
    )
    
    await ctx.send(embed=embed)

@bot.command(name='mystats', help='Xem TFT stats của summoner')
async def tft_stats(ctx, summoner_name=None, region='vn'):
    """Xem thống kê TFT của summoner"""
    if not summoner_name:
        # Nếu không có tên, kiểm tra xem user có đang theo dõi ai không
        user_id = str(ctx.author.id)
        if user_id in db.tracking_list:
            summoner_name = db.tracking_list[user_id]['summoner_name']
            region = db.tracking_list[user_id]['region']
        else:
            await ctx.send("❌ Vui lòng cung cấp summoner name hoặc dùng `!track <tên>` trước!")
            return
    
    await ctx.send(f"📊 Đang lấy thống kê TFT của **{summoner_name}**...")
    
    # Lấy lịch sử trận đấu
    matches = await tft_service.get_tft_match_history(summoner_name, region)
    
    if not matches:
        await ctx.send(f"❌ Không tìm thấy dữ liệu TFT cho **{summoner_name}**")
        return
    
    # Phân tích tổng quan
    placements = [match.get('placement', 8) for match in matches]
    avg_placement = sum(placements) / len(placements)
    top4_count = sum(1 for p in placements if p <= 4)
    top1_count = sum(1 for p in placements if p == 1)
    
    # Tạo embed tổng quan
    embed = discord.Embed(
        title=f"📊 TFT Stats - {summoner_name}",
        description=f"**{len(matches)}** matches gần nhất",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📈 Thống kê",
        value=f"• Avg Placement: `{avg_placement:.2f}`\n"
              f"• Top 4 Rate: `{top4_count}/{len(matches)}` ({top4_count/len(matches)*100:.1f}%)\n"
              f"• Top 1: `{top1_count}` lần",
        inline=True
    )
    
    # Hiển thị 3 match gần nhất
    recent_matches = matches[:3]
    match_texts = []
    for i, match in enumerate(recent_matches, 1):
        placement = match.get('placement', 8)
        emoji = "👑" if placement == 1 else "🥈" if placement <= 4 else "📉"
        match_texts.append(f"{emoji} **Match {i}:** Top #{placement}")
    
    embed.add_field(
        name="🎮 Recent Matches",
        value="\n".join(match_texts),
        inline=True
    )
    
    # Phân tích playstyle dựa trên traits
    all_traits = []
    for match in matches[:5]:
        all_traits.extend(match.get('traits', []))
    
    from collections import Counter
    if all_traits:
        common_traits = Counter(all_traits).most_common(3)
        trait_text = "\n".join([f"• {trait[0]}" for trait in common_traits])
        embed.add_field(
            name="🏆 Frequent Traits",
            value=trait_text,
            inline=False
        )
    
    embed.set_footer(text=f"Region: {region.upper()} • Dùng !track để tự động thông báo")
    
    await ctx.send(embed=embed)
    
    # Hiển thị chi tiết match gần nhất
    if matches:
        latest_match = matches[0]
        analysis = tft_service.analyze_tft_match(latest_match, summoner_name)
        if analysis:
            match_embed = create_tft_match_embed(analysis, summoner_name)
            await ctx.send(embed=match_embed)

@bot.command(name='listtracking', help='Xem danh sách đang theo dõi')
async def list_tracking(ctx):
    """Hiển thị tất cả summoner đang được theo dõi"""
    tracking_list = db.get_all_tracking()
    
    if not tracking_list:
        embed = discord.Embed(
            title="📋 Danh sách theo dõi",
            description="Chưa có ai được theo dõi.",
            color=0x7289DA
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="📋 Danh sách theo dõi TFT",
        description=f"Đang theo dõi **{len(tracking_list)}** người chơi",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    
    for user_id, data in tracking_list.items():
        try:
            user = await bot.fetch_user(int(user_id))
            user_name = user.name
        except:
            user_name = f"User {user_id}"
        
        added_time = data.get('added_at', datetime.now())
        time_ago = datetime.now() - added_time
        hours_ago = time_ago.total_seconds() / 3600
        
        embed.add_field(
            name=f"🎮 {data['summoner_name']}",
            value=f"👤 {user_name}\n"
                  f"🌍 {data['region'].upper()}\n"
                  f"⏰ {hours_ago:.1f} giờ trước",
            inline=True
        )
    
    embed.set_footer(text="Bot kiểm tra mỗi 3 phút")
    await ctx.send(embed=embed)

@bot.command(name='forcecheck', help='Kiểm tra ngay lập tức')
async def force_check(ctx, summoner_name=None):
    """Kiểm tra ngay mà không cần chờ schedule"""
    if not summoner_name:
        user_id = str(ctx.author.id)
        if user_id in db.tracking_list:
            data = db.tracking_list[user_id]
            summoner_name = data['summoner_name']
            region = data['region']
            channel_id = data['channel_id']
            
            await ctx.send(f"🔍 Đang kiểm tra ngay **{summoner_name}**...")
            await check_and_notify_single(summoner_name, region, ctx.channel)
        else:
            await ctx.send("❌ Bạn chưa theo dõi ai. Dùng `!track <tên>` trước.")
    else:
        await ctx.send(f"🔍 Đang kiểm tra ngay **{summoner_name}**...")
        await check_and_notify_single(summoner_name, 'vn', ctx.channel)

# ========== AUTO CHECK TASK ==========

@tasks.loop(minutes=3)
async def auto_check_tft_matches():
    """Tự động kiểm tra trận đấu mới mỗi 3 phút"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Đang kiểm tra TFT matches...")
    
    tracking_list = db.get_all_tracking()
    
    if not tracking_list:
        return
    
    for user_id, data in tracking_list.items():
        try:
            summoner_name = data['summoner_name']
            region = data['region']
            channel_id = data['channel_id']
            
            # Lấy channel
            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"Channel {channel_id} không tồn tại")
                continue
            
            await check_and_notify_single(summoner_name, region, channel)
            
            # Chờ 2 giây giữa mỗi người chơi để tránh rate limit
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Lỗi khi kiểm tra {summoner_name}: {e}")
            continue

async def check_and_notify_single(summoner_name, region, channel):
    """Kiểm tra và thông báo cho một summoner"""
    try:
        # Lấy match history
        matches = await tft_service.get_tft_match_history(summoner_name, region)
        
        if not matches:
            return
        
        # Lấy match gần nhất
        latest_match = matches[0]
        latest_match_id = latest_match.get('match_id', 'unknown')
        
        # Kiểm tra xem đã thông báo match này chưa
        last_notified_match = db.get_last_match(summoner_name)
        
        if last_notified_match != latest_match_id:
            # Đây là match mới, thông báo!
            db.update_last_match(summoner_name, latest_match_id)
            
            # Phân tích match
            analysis = tft_service.analyze_tft_match(latest_match, summoner_name)
            
            if analysis:
                # Tạo và gửi embed thông báo
                embed = create_tft_match_embed(analysis, summoner_name, latest_match_id)
                
                # Thêm mention nếu là channel công khai
                mention = ""
                if isinstance(channel, discord.TextChannel):
                    mention = f"🎮 **{summoner_name}** vừa hoàn thành trận TFT!\n"
                
                await channel.send(mention, embed=embed)
                print(f"✅ Đã thông báo match mới của {summoner_name}")
            
            # Chờ 1 giây trước khi tiếp tục
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Lỗi khi xử lý {summoner_name}: {e}")

@auto_check_tft_matches.before_loop
async def before_auto_check():
    """Đợi bot sẵn sàng trước khi chạy task"""
    await bot.wait_until_ready()

# ========== BASIC COMMANDS ==========

@bot.command(name='ping', help='Kiểm tra độ trễ')
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! Độ trễ: {latency}ms')

@bot.command(name='help', help='Hiển thị hướng dẫn')
async def help_command(ctx):
    embed = discord.Embed(
        title="🎮 TFT Auto Tracker - Hướng dẫn",
        description="Bot tự động thông báo khi bạn hoàn thành trận TFT!",
        color=0x7289DA
    )
    
    commands_list = [
        ("!track <tên> [region]", "Theo dõi tự động TFT match (mặc định region: vn)"),
        ("!untrack", "Dừng theo dõi"),
        ("!mystats [tên]", "Xem thống kê TFT của bạn/bạn bè"),
        ("!listtracking", "Xem danh sách đang theo dõi"),
        ("!forcecheck", "Kiểm tra ngay lập tức"),
        ("!ping", "Kiểm tra độ trễ"),
        ("!help", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
    
    embed.add_field(
        name="📊 Tự động hóa",
        value="Bot sẽ tự động kiểm tra mỗi **3 phút** và thông báo khi có trận mới!",
        inline=False
    )
    
    embed.add_field(
        name="🌍 Regions hỗ trợ",
        value="VN, NA, EUW, EUNE, KR\nMặc định: VN (Vietnam)",
        inline=False
    )
    
    embed.set_footer(text="Made with ❤️ for TFT players")
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Xử lý lỗi command"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Thiếu tham số! Dùng `!help` để xem hướng dẫn.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Bỏ qua lỗi command không tồn tại
    else:
        print(f"Lỗi command: {error}")

# ========== RUN BOT ==========

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Lỗi: DISCORD_BOT_TOKEN không được tìm thấy!")
        print("ℹ️ Vui lòng đặt biến môi trường trên Render.com")
