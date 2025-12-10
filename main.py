import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timedelta
import json

# Import các module riêng
from config import Config
from database import Database
from riot_verifier import RiotVerifier
from tft_service import TFTService
from gemini_analyzer import GeminiAnalyzer

# Load config
config = Config()

# Khởi tạo bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(
    command_prefix=config.PREFIX,
    intents=intents,
    help_command=None
)

# Khởi tạo các service
db = Database()
riot_verifier = RiotVerifier(config.RIOT_API_KEY)
tft_service = TFTService()
gemini_analyzer = GeminiAnalyzer(config.GEMINI_API_KEY)

# Biến tạm lưu trạng thái xác thực
verification_sessions = {}

# ========== EVENTS ==========

@bot.event
async def on_ready():
    """Sự kiện khi bot sẵn sàng"""
    print(f'✅ TFT Tracker Bot đã sẵn sàng!')
    print(f'🤖 Bot: {bot.user.name}')
    print(f'🎮 Prefix: {config.PREFIX}')
    print(f'📊 Database: {len(db.get_all_players())} players')
    print(f'🔧 Gemini AI: {gemini_analyzer.status}')
    
    # Khởi động task tự động
    if not auto_check_matches.is_running():
        auto_check_matches.start()
    
    # Set status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(db.get_all_players())} TFT players"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    """Xử lý lỗi command"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Thiếu tham số",
            description=f"Vui lòng kiểm tra lại cú pháp lệnh!",
            color=0xff0000
        )
        embed.add_field(
            name="ℹ️ Hướng dẫn",
            value=f"Dùng `{config.PREFIX}help` để xem hướng dẫn đầy đủ",
            inline=False
        )
        await ctx.send(embed=embed)
    
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Tham số không hợp lệ: {str(error)}")
    
    else:
        print(f"Lỗi không xác định: {error}")
        await ctx.send(f"❌ Đã xảy ra lỗi: {str(error)[:100]}...")

# ========== VERIFICATION FLOW ==========

@bot.command(name='track')
async def track_player(ctx, riot_id: str, region: str = 'vn'):
    """
    Bắt đầu theo dõi player - Bước 1: Xác thực Riot ID
    Format: !track Username#Tagline [region]
    Example: !track DarkViPer#VN2 vn
    """
    
    # Kiểm tra format Riot ID
    if '#' not in riot_id:
        embed = discord.Embed(
            title="❌ Sai định dạng Riot ID",
            description="Vui lòng sử dụng đúng format: **Username#Tagline**",
            color=0xff0000
        )
        embed.add_field(
            name="📝 Ví dụ đúng:",
            value=f"`{config.PREFIX}track DarkViPer#VN2 vn`\n`{config.PREFIX}track TFTGod#KR1 kr`",
            inline=False
        )
        embed.add_field(
            name="ℹ️ Lưu ý:",
            value="Tagline thường là mã vùng (VN2, KR1, EUW, NA1...)",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Tách username và tagline
    try:
        username, tagline = riot_id.split('#', 1)
    except ValueError:
        await ctx.send("❌ Sai format! Dùng: Username#Tagline")
        return
    
    # Kiểm tra xem đã theo dõi chưa
    existing = db.get_player_by_riot_id(riot_id)
    if existing:
        embed = discord.Embed(
            title="⚠️ Đã theo dõi",
            description=f"Riot ID `{riot_id}` đã được theo dõi!",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Gửi thông báo đang xác thực
    embed = discord.Embed(
        title="🔍 Đang xác thực Riot ID...",
        description=f"**Riot ID:** `{riot_id}`\n**Region:** `{region.upper()}`",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    embed.set_footer(text="Vui lòng chờ trong giây lát...")
    msg = await ctx.send(embed=embed)
    
    # Xác thực Riot ID
    verification_result = await riot_verifier.verify_riot_id(riot_id, region)
    
    if not verification_result['success']:
        # Xác thực thất bại
        embed = discord.Embed(
            title="❌ Xác thực thất bại",
            description=f"Không thể xác thực Riot ID: `{riot_id}`",
            color=0xff0000
        )
        embed.add_field(
            name="📝 Lý do:",
            value=verification_result.get('error', 'Không rõ lý do'),
            inline=False
        )
        embed.add_field(
            name="💡 Gợi ý:",
            value="1. Kiểm tra lại chính tả\n2. Kiểm tra Region\n3. Đảm bảo tài khoản tồn tại",
            inline=False
        )
        await msg.edit(embed=embed)
        return
    
    # Xác thực thành công - hiển thị thông tin
    account_data = verification_result['data']
    
    embed = discord.Embed(
        title="✅ Đã tìm thấy tài khoản!",
        description=f"**Riot ID:** `{riot_id}`",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    # Thêm thông tin cơ bản
    if account_data.get('game_name'):
        embed.add_field(
            name="👤 Game Name",
            value=account_data['game_name'],
            inline=True
        )
    
    if account_data.get('tagline'):
        embed.add_field(
            name="🏷️ Tagline",
            value=account_data['tagline'],
            inline=True
        )
    
    # Lấy thông tin TFT
    tft_info = await tft_service.get_player_overview(riot_id, region)
    
    if tft_info and tft_info.get('rank'):
        embed.add_field(
            name="📊 Rank TFT",
            value=f"**{tft_info['rank']}**\n{tft_info.get('lp', '')} LP",
            inline=True
        )
    
    if tft_info and tft_info.get('level'):
        embed.add_field(
            name="🎮 Level",
            value=tft_info['level'],
            inline=True
        )
    
    if tft_info and tft_info.get('wins'):
        win_rate = (tft_info['wins'] / max(tft_info['total_games'], 1)) * 100
        embed.add_field(
            name="📈 Thống kê",
            value=f"Tổng: {tft_info['total_games']} trận\nThắng: {tft_info['wins']} ({win_rate:.1f}%)",
            inline=True
        )
    
    # Thêm hướng dẫn xác nhận
    embed.add_field(
        name="🔐 Bước 2: Xác nhận sở hữu",
        value=f"Để xác nhận đây là tài khoản của bạn, hãy gõ:\n"
              f"`{config.PREFIX}confirm {riot_id}`\n\n"
              f"Hoặc hủy với: `{config.PREFIX}cancel`",
        inline=False
    )
    
    # Lưu session xác thực tạm thời
    verification_sessions[ctx.author.id] = {
        'riot_id': riot_id,
        'region': region,
        'data': account_data,
        'tft_info': tft_info,
        'timestamp': datetime.now(),
        'message_id': msg.id
    }
    
    await msg.edit(embed=embed)

@bot.command(name='confirm')
async def confirm_ownership(ctx, riot_id: str):
    """
    Bước 2: Xác nhận sở hữu tài khoản
    """
    user_id = ctx.author.id
    
    # Kiểm tra session
    if user_id not in verification_sessions:
        embed = discord.Embed(
            title="❌ Không tìm thấy session",
            description="Vui lòng bắt đầu với lệnh `!track` trước.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    session = verification_sessions[user_id]
    
    # Kiểm tra Riot ID khớp
    if session['riot_id'].lower() != riot_id.lower():
        embed = discord.Embed(
            title="❌ Riot ID không khớp",
            description=f"Session: `{session['riot_id']}`\nBạn nhập: `{riot_id}`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra thời gian session (30 phút)
    time_diff = datetime.now() - session['timestamp']
    if time_diff.total_seconds() > 1800:  # 30 phút
        del verification_sessions[user_id]
        embed = discord.Embed(
            title="⏰ Session hết hạn",
            description="Vui lòng bắt đầu lại với `!track`.",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Lưu player vào database
    player_data = {
        'discord_id': str(user_id),
        'discord_name': ctx.author.name,
        'riot_id': session['riot_id'],
        'region': session['region'],
        'game_name': session['data'].get('game_name', ''),
        'tagline': session['data'].get('tagline', ''),
        'puuid': session['data'].get('puuid', ''),
        'verified': True,
        'verification_date': datetime.now().isoformat(),
        'tracking_started': datetime.now().isoformat(),
        'channel_id': str(ctx.channel.id),
        'tft_info': session['tft_info'],
        'settings': {
            'auto_notify': True,
            'include_ai_analysis': True,
            'mention_on_notify': True
        }
    }
    
    success = db.add_player(player_data)
    
    if not success:
        embed = discord.Embed(
            title="❌ Lỗi khi lưu dữ liệu",
            description="Vui lòng thử lại sau.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Xóa session
    del verification_sessions[user_id]
    
    # Thông báo thành công
    embed = discord.Embed(
        title="🎉 Đã xác thực thành công!",
        description=f"Bắt đầu theo dõi **{session['riot_id']}**",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Thông tin đã lưu",
        value=f"• Riot ID: `{session['riot_id']}`\n"
              f"• Region: `{session['region'].upper()}`\n"
              f"• Channel: <#{ctx.channel.id}>\n"
              f"• Verified: ✅",
        inline=False
    )
    
    embed.add_field(
        name="🔄 Tự động hóa",
        value="• Bot sẽ tự động kiểm tra mỗi **5 phút**\n"
              "• Thông báo khi có trận TFT mới\n"
              "• Phân tích AI tự động (nếu bật)",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Cài đặt",
        value=f"Dùng `{config.PREFIX}settings` để thay đổi cài đặt",
        inline=False
    )
    
    embed.set_footer(text="Bot sẽ thông báo khi có trận đấu mới!")
    
    await ctx.send(embed=embed)
    
    # Cập nhật bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(db.get_all_players())} TFT players"
        )
    )

@bot.command(name='cancel')
async def cancel_verification(ctx):
    """Hủy quá trình xác thực"""
    user_id = ctx.author.id
    
    if user_id not in verification_sessions:
        await ctx.send("❌ Không có session nào để hủy.")
        return
    
    riot_id = verification_sessions[user_id]['riot_id']
    del verification_sessions[user_id]
    
    embed = discord.Embed(
        title="🗑️ Đã hủy xác thực",
        description=f"Đã hủy session cho `{riot_id}`",
        color=0xff9900
    )
    await ctx.send(embed=embed)

# ========== PLAYER MANAGEMENT ==========

@bot.command(name='untrack')
async def untrack_player(ctx, riot_id: str = None):
    """
    Dừng theo dõi player
    Usage: !untrack [RiotID] (nếu không có ID sẽ hỏi)
    """
    user_id = str(ctx.author.id)
    
    # Nếu không có riot_id, hiển thị danh sách để chọn
    if not riot_id:
        players = db.get_players_by_discord_id(user_id)
        
        if not players:
            await ctx.send("❌ Bạn không theo dõi ai cả!")
            return
        
        # Tạo embed với danh sách
        embed = discord.Embed(
            title="📋 Chọn player để dừng theo dõi",
            description="Gõ `!untrack [số_thứ_tự]`",
            color=0x7289DA
        )
        
        for i, player in enumerate(players, 1):
            embed.add_field(
                name=f"{i}. {player['riot_id']}",
                value=f"Theo dõi từ: {player['tracking_started'][:10]}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        return
    
    # Nếu riot_id là số, tìm player theo index
    if riot_id.isdigit():
        players = db.get_players_by_discord_id(user_id)
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
            description=f"Không theo dõi `{riot_id}` nữa.",
            color=0x00ff00
        )
        
        # Cập nhật status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(db.get_all_players())} TFT players"
            )
        )
    else:
        embed = discord.Embed(
            title="❌ Không tìm thấy player",
            description=f"Bạn không theo dõi `{riot_id}`.",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='myplayers')
async def list_my_players(ctx):
    """Danh sách players bạn đang theo dõi"""
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord_id(user_id)
    
    if not players:
        embed = discord.Embed(
            title="📋 Danh sách theo dõi",
            description="Bạn chưa theo dõi player nào.",
            color=0x7289DA
        )
        embed.add_field(
            name="🎮 Bắt đầu theo dõi",
            value=f"Dùng `{config.PREFIX}track Username#Tagline`",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title=f"📋 Đang theo dõi {len(players)} player(s)",
        description=f"User: {ctx.author.name}",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    
    for player in players:
        status = "✅" if player.get('verified') else "⚠️"
        last_match = player.get('last_match_time', 'Chưa có')
        
        if isinstance(last_match, str) and len(last_match) > 10:
            last_match = last_match[:10]
        
        embed.add_field(
            name=f"{status} {player['riot_id']}",
            value=f"• Region: {player.get('region', 'N/A').upper()}\n"
                  f"• Theo dõi từ: {player.get('tracking_started', 'N/A')[:10]}\n"
                  f"• Match cuối: {last_match}",
            inline=True
        )
    
    embed.set_footer(text=f"Dùng !untrack [số] để dừng theo dõi")
    await ctx.send(embed=embed)

@bot.command(name='allplayers')
@commands.has_permissions(administrator=True)
async def list_all_players(ctx):
    """Danh sách tất cả players (admin only)"""
    players = db.get_all_players()
    
    if not players:
        await ctx.send("📭 Chưa có player nào được theo dõi.")
        return
    
    # Phân trang
    items_per_page = 6
    pages = [players[i:i + items_per_page] for i in range(0, len(players), items_per_page)]
    
    current_page = 0
    
    def create_embed(page):
        embed = discord.Embed(
            title=f"👥 Tất cả players ({len(players)})",
            description=f"Trang {page + 1}/{len(pages)}",
            color=0x7289DA,
            timestamp=datetime.now()
        )
        
        for player in pages[page]:
            discord_user = f"<@{player['discord_id']}>"
            verified = "✅" if player.get('verified') else "❌"
            
            embed.add_field(
                name=f"{verified} {player['riot_id']}",
                value=f"• Discord: {discord_user}\n"
                      f"• Region: {player.get('region', 'N/A').upper()}\n"
                      f"• Channel: <#{player.get('channel_id', '')}>",
                inline=True
            )
        
        return embed
    
    # Gửi embed đầu tiên
    message = await ctx.send(embed=create_embed(current_page))
    
    # Thêm reactions cho pagination
    if len(pages) > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id
        
        while True:
            try:
                reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
                
                if str(reaction.emoji) == "▶️" and current_page < len(pages) - 1:
                    current_page += 1
                    await message.edit(embed=create_embed(current_page))
                elif str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=create_embed(current_page))
                
                await message.remove_reaction(reaction, user)
                
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

# ========== MATCH CHECKING & NOTIFICATION ==========

@tasks.loop(minutes=5)
async def auto_check_matches():
    """Tự động kiểm tra trận đấu mới mỗi 5 phút"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Đang kiểm tra TFT matches...")
    
    players = db.get_all_players()
    
    if not players:
        return
    
    for player in players:
        try:
            await check_player_matches(player)
            await asyncio.sleep(1)  # Delay để tránh rate limit
        except Exception as e:
            print(f"Lỗi khi kiểm tra {player['riot_id']}: {e}")

async def check_player_matches(player):
    """Kiểm tra và thông báo match mới cho một player"""
    try:
        riot_id = player['riot_id']
        region = player.get('region', 'vn')
        channel_id = int(player['channel_id'])
        
        # Lấy channel
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} không tồn tại")
            return
        
        # Lấy match history
        matches = await tft_service.get_match_history(riot_id, region, limit=1)
        
        if not matches or len(matches) == 0:
            return
        
        latest_match = matches[0]
        match_id = latest_match.get('match_id')
        
        # Kiểm tra xem đã thông báo match này chưa
        last_notified_match = player.get('last_match_id')
        
        if last_notified_match != match_id:
            # Match mới! Cập nhật database
            db.update_last_match(
                player['discord_id'],
                riot_id,
                match_id,
                latest_match.get('timestamp')
            )
            
            # Tạo và gửi thông báo
            await send_match_notification(channel, player, latest_match)
            
    except Exception as e:
        print(f"Lỗi check_player_matches: {e}")

async def send_match_notification(channel, player, match_data):
    """Gửi thông báo trận đấu mới"""
    try:
        riot_id = player['riot_id']
        settings = player.get('settings', {})
        
        # Tạo mention
        mention = ""
        if settings.get('mention_on_notify', True):
            discord_user = await bot.fetch_user(int(player['discord_id']))
            mention = f"{discord_user.mention} "
        
        # Tạo embed cơ bản
        placement = match_data.get('placement', 8)
        level = match_data.get('level', 'N/A')
        
        # Màu theo placement
        if placement == 1:
            color = 0xFFD700  # Vàng
            emoji = "👑"
        elif placement <= 4:
            color = 0xC0C0C0  # Bạc
            emoji = "🥈"
        else:
            color = 0xCD7F32  # Đồng
            emoji = "📉"
        
        embed = discord.Embed(
            title=f"{emoji} {riot_id} vừa hoàn thành trận TFT!",
            description=f"**🏆 Placement:** #{placement} | **📊 Level:** {level}",
            color=color,
            timestamp=datetime.now()
        )
        
        # Thêm thông tin chi tiết
        if match_data.get('traits'):
            traits_text = "\n".join([
                f"• {trait.get('name', 'Unknown')} (Tier {trait.get('tier', 1)})"
                for trait in match_data['traits'][:5]
            ])
            embed.add_field(
                name="🏆 Đội hình",
                value=traits_text[:1024],
                inline=True
            )
        
        if match_data.get('units'):
            units_text = "\n".join([
                f"• {unit.get('character_id', 'Unknown').replace('TFT', '').replace('_', ' ').title()}"
                for unit in match_data['units'][:5]
            ])
            embed.add_field(
                name="⚔️ Units chính",
                value=units_text[:1024],
                inline=True
            )
        
        # Thêm phân tích AI nếu được bật
        if settings.get('include_ai_analysis', True) and gemini_analyzer.is_enabled():
            ai_analysis = await gemini_analyzer.analyze_match(match_data, riot_id)
            if ai_analysis:
                # Cắt ngắn nếu quá dài
                if len(ai_analysis) > 1000:
                    ai_analysis = ai_analysis[:1000] + "..."
                
                embed.add_field(
                    name="🤖 AI Analysis",
                    value=ai_analysis,
                    inline=False
                )
        
        embed.set_footer(
            text="TFT Auto Tracker • Tự động thông báo",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        # Gửi thông báo
        await channel.send(mention, embed=embed)
        print(f"✅ Đã thông báo match mới của {riot_id}")
        
    except Exception as e:
        print(f"Lỗi send_match_notification: {e}")

@bot.command(name='forcecheck')
async def force_check(ctx, riot_id: str = None):
    """Kiểm tra ngay lập tức"""
    user_id = str(ctx.author.id)
    
    if not riot_id:
        # Kiểm tra tất cả players của user
        players = db.get_players_by_discord_id(user_id)
        
        if not players:
            await ctx.send("❌ Bạn không theo dõi ai cả!")
            return
        
        msg = await ctx.send(f"🔍 Đang kiểm tra {len(players)} player(s)...")
        
        for player in players:
            try:
                await check_player_matches(player)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Force check error for {player['riot_id']}: {e}")
        
        await msg.edit(content="✅ Đã kiểm tra xong tất cả players!")
        return
    
    # Kiểm tra specific player
    player = db.get_player_by_riot_id(riot_id)
    
    if not player or player['discord_id'] != user_id:
        await ctx.send("❌ Bạn không theo dõi player này!")
        return
    
    await ctx.send(f"🔍 Đang kiểm tra {riot_id}...")
    await check_player_matches(player)
    await ctx.send(f"✅ Đã kiểm tra xong {riot_id}!")

# ========== UTILITY COMMANDS ==========

@bot.command(name='ping')
async def ping_command(ctx):
    """Kiểm tra độ trễ"""
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms**",
        color=0x00ff00
    )
    
    embed.add_field(
        name="📊 Thống kê",
        value=f"• Server: {len(bot.guilds)}\n"
              f"• Players: {len(db.get_all_players())}\n"
              f"• Uptime: {get_uptime()}",
        inline=True
    )
    
    embed.add_field(
        name="🤖 Dịch vụ",
        value=f"• Gemini AI: {gemini_analyzer.status}\n"
              f"• Riot API: {'✅' if riot_verifier.has_api_key else '⚠️'}\n"
              f"• Auto-check: {'✅' if auto_check_matches.is_running() else '❌'}",
        inline=True
    )
    
    await ctx.send(embed=embed)

def get_uptime():
    """Lấy thời gian bot đã chạy"""
    delta = datetime.now() - bot_start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

@bot.command(name='help')
async def help_command(ctx):
    """Hiển thị hướng dẫn"""
    embed = discord.Embed(
        title="🎮 TFT Auto Tracker - Hướng dẫn",
        description="Bot tự động thông báo TFT matches với xác thực 2 bước",
        color=0x7289DA
    )
    
    # Commands
    commands_section = [
        (f"{config.PREFIX}track <Username#Tag> [region]", "Bắt đầu theo dõi player"),
        (f"{config.PREFIX}confirm <RiotID>", "Xác nhận sở hữu tài khoản"),
        (f"{config.PREFIX}cancel", "Hủy quá trình xác thực"),
        (f"{config.PREFIX}untrack [RiotID/số]", "Dừng theo dõi"),
        (f"{config.PREFIX}myplayers", "Danh sách players bạn theo dõi"),
        (f"{config.PREFIX}forcecheck [RiotID]", "Kiểm tra ngay lập tức"),
        (f"{config.PREFIX}ping", "Kiểm tra độ trễ và thống kê"),
        (f"{config.PREFIX}help", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands_section:
        embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
    
    # Examples
    embed.add_field(
        name="📝 Ví dụ sử dụng:",
        value=f"```\n"
              f"{config.PREFIX}track DarkViPer#VN2 vn\n"
              f"# Bot sẽ hiển thị thông tin tài khoản\n"
              f"# Bạn xác nhận với:\n"
              f"{config.PREFIX}confirm DarkViPer#VN2\n"
              f"```",
        inline=False
    )
    
    # Features
    embed.add_field(
        name="✨ Tính năng:",
        value="• Xác thực 2 bước với Riot ID\n"
              "• Tự động thông báo khi có match mới\n"
              "• Phân tích AI từ Gemini (nếu có key)\n"
              "• Thống kê chi tiết từng player",
        inline=False
    )
    
    embed.set_footer(
        text=f"Prefix: {config.PREFIX} • Theo dõi: {len(db.get_all_players())} players"
    )
    
    await ctx.send(embed=embed)

@bot.command(name='settings')
async def settings_command(ctx, setting: str = None, value: str = None):
    """Cài đặt cho player"""
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord_id(user_id)
    
    if not players:
        await ctx.send("❌ Bạn không theo dõi player nào!")
        return
    
    if not setting:
        # Hiển thị current settings
        embed = discord.Embed(
            title="⚙️ Cài đặt của bạn",
            description="Dùng `!settings [tên] [giá trị]` để thay đổi",
            color=0x7289DA
        )
        
        for player in players:
            settings = player.get('settings', {})
            
            embed.add_field(
                name=f"🎮 {player['riot_id']}",
                value=f"• Mention: {'✅' if settings.get('mention_on_notify', True) else '❌'}\n"
                      f"• AI Analysis: {'✅' if settings.get('include_ai_analysis', True) else '❌'}\n"
                      f"• Auto-notify: {'✅' if settings.get('auto_notify', True) else '❌'}",
                inline=True
            )
        
        await ctx.send(embed=embed)
        return
    
    # Update settings
    valid_settings = ['mention', 'ai', 'autonotify']
    
    if setting.lower() not in ['mention', 'ai', 'autonotify']:
        await ctx.send(f"❌ Setting không hợp lệ! Chọn: {', '.join(valid_settings)}")
        return
    
    if value is None:
        await ctx.send("❌ Thiếu giá trị! Dùng: `on` hoặc `off`")
        return
    
    value_bool = value.lower() in ['on', 'true', 'yes', '1', 'enable']
    
    # Update cho tất cả players của user
    updated_count = 0
    for player in players:
        riot_id = player['riot_id']
        
        if setting.lower() == 'mention':
            db.update_setting(user_id, riot_id, 'mention_on_notify', value_bool)
        elif setting.lower() == 'ai':
            db.update_setting(user_id, riot_id, 'include_ai_analysis', value_bool)
        elif setting.lower() == 'autonotify':
            db.update_setting(user_id, riot_id, 'auto_notify', value_bool)
        
        updated_count += 1
    
    status = "✅ Bật" if value_bool else "❌ Tắt"
    setting_name = {
        'mention': 'Mention',
        'ai': 'AI Analysis',
        'autonotify': 'Auto-notify'
    }[setting.lower()]
    
    embed = discord.Embed(
        title="⚙️ Đã cập nhật cài đặt",
        description=f"{status} **{setting_name}** cho {updated_count} player(s)",
        color=0x00ff00
    )
    
    await ctx.send(embed=embed)

# ========== RUN BOT ==========

bot_start_time = datetime.now()

if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Lỗi: DISCORD_TOKEN không được tìm thấy!")
        print("ℹ️ Vui lòng đặt biến môi trường DISCORD_TOKEN")
        exit(1)
    
    print("🚀 Khởi động TFT Auto Tracker Bot...")
    print(f"📊 Database: {db.file_path}")
    print(f"🤖 Gemini AI: {gemini_analyzer.status}")
    print(f"🎮 Riot Verifier: {'✅ Ready' if riot_verifier.has_api_key else '⚠️ Limited'}")
    
    bot.run(config.DISCORD_TOKEN)
