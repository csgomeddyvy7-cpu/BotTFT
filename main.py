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

# ========== HELPER FUNCTIONS ==========

def format_rank_vietnamese(rank_text):
    """
    Chuyển đổi rank tiếng Anh sang tiếng Việt với định dạng đẹp
    Ví dụ: Gold II -> Vàng II, Platinum III -> Bạch Kim III
    """
    if not rank_text or rank_text.lower() == 'unranked':
        return "Chưa xếp hạng"
    
    # Map từ tiếng Anh sang tiếng Việt
    rank_map = {
        'iron': 'Sắt',
        'bronze': 'Đồng',
        'silver': 'Bạc', 
        'gold': 'Vàng',
        'platinum': 'Bạch Kim',
        'diamond': 'Kim Cương',
        'master': 'Cao Thủ',
        'grandmaster': 'Đại Cao Thủ',
        'challenger': 'Thách Đấu',
        'unranked': 'Chưa xếp hạng'
    }
    
    # Chuyển đổi số La Mã sang số thường
    roman_to_number = {
        'i': 'I', 'ii': 'II', 'iii': 'III', 'iv': 'IV',
        'v': 'V', 'vi': 'VI', 'vii': 'VII', 'viii': 'VIII'
    }
    
    # Tách rank thành từng phần
    words = rank_text.split()
    converted_words = []
    
    for word in words:
        word_lower = word.lower()
        
        # Kiểm tra nếu là tier (Iron, Gold, Platinum, etc.)
        if word_lower in rank_map:
            converted_words.append(rank_map[word_lower])
        # Kiểm tra nếu là division (I, II, III, IV, etc.)
        elif word_lower in roman_to_number:
            converted_words.append(roman_to_number[word_lower])  # Giữ nguyên số La Mã viết hoa
        else:
            converted_words.append(word)
    
    return ' '.join(converted_words)

def get_rank_emoji(rank_text):
    """
    Lấy emoji tương ứng với rank
    """
    rank_lower = rank_text.lower()
    
    if 'sắt' in rank_lower:
        return "⚫"
    elif 'đồng' in rank_lower:
        return "🟤"
    elif 'bạc' in rank_lower:
        return "⚪"
    elif 'vàng' in rank_lower:
        return "🟡"
    elif 'bạch kim' in rank_lower:
        return "🔵"
    elif 'kim cương' in rank_lower:
        return "💎"
    elif 'cao thủ' in rank_lower:
        return "🔥"
    elif 'đại cao thủ' in rank_lower:
        return "🌟"
    elif 'thách đấu' in rank_lower:
        return "👑"
    else:
        return "🎮"

def format_large_number(num):
    """Định dạng số lớn"""
    if num >= 1000:
        return f"{num:,}".replace(",", ".")
    return str(num)

def get_uptime(start_time):
    """Tính thời gian đã chạy"""
    delta = datetime.now() - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

# ========== EVENTS ==========

@bot.event
async def on_ready():
    """Sự kiện khi bot sẵn sàng"""
    print(f'✅ TFT Tracker Bot đã sẵn sàng!')
    print(f'🤖 Bot: {bot.user.name} (ID: {bot.user.id})')
    print(f'🎮 Prefix: {config.PREFIX}')
    
    # Load players từ database
    players = db.get_all_players()
    print(f'📊 Database: {len(players)} players đang theo dõi')
    print(f'🔧 Gemini AI: {gemini_analyzer.status}')
    print(f'🎯 Riot Verifier: {"✅ Có API Key" if riot_verifier.has_api_key else "⚠️ Không có API Key"}')
    
    # Khởi động task tự động
    if not auto_check_matches.is_running():
        auto_check_matches.start()
        print(f'🔄 Đã bật auto-check (mỗi {config.AUTO_CHECK_INTERVAL} phút)')
    
    # Set status
    await update_bot_status()

async def update_bot_status():
    """Cập nhật status bot"""
    players_count = len(db.get_all_players())
    activity_text = f"{players_count} TFT players"
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=activity_text
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
        
        # Gợi ý cho từng lệnh
        if ctx.command.name == 'track':
            embed.add_field(
                name="📝 Ví dụ đúng:",
                value=f"`{config.PREFIX}track TênGame#Tagline vn`\n`{config.PREFIX}track DarkViPer#VN2`",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Tham số không hợp lệ: {str(error)}")
    
    else:
        print(f"[ERROR] Command {ctx.command}: {error}")
        await ctx.send(f"❌ Đã xảy ra lỗi: {str(error)[:100]}")

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
            description="**Riot ID phải có dạng:** `TênGame#Tagline`",
            color=0xff0000
        )
        embed.add_field(
            name="📝 Ví dụ đúng:",
            value=f"• `{config.PREFIX}track DarkViPer#VN2`\n• `{config.PREFIX}track TFTGod#KR1 kr`",
            inline=False
        )
        embed.add_field(
            name="ℹ️ Tìm Tagline của bạn:",
            value="1. Vào game LOL/TFT\n2. Click vào icon profile\n3. Tagline hiển thị dưới tên\n4. Thường là: VN2, NA1, KR1, EUW...",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Tách username và tagline
    try:
        username, tagline = riot_id.split('#', 1)
        username = username.strip()
        tagline = tagline.strip()
        
        if not username or not tagline:
            await ctx.send("❌ Tên và Tagline không được để trống!")
            return
            
    except ValueError:
        await ctx.send("❌ Sai format! Dùng: TênGame#Tagline")
        return
    
    # Kiểm tra xem đã theo dõi chưa
    existing = db.get_player_by_riot_id(riot_id)
    if existing:
        discord_user = f"<@{existing['discord_id']}>"
        embed = discord.Embed(
            title="⚠️ Đã được theo dõi",
            description=f"Riot ID `{riot_id}` đang được {discord_user} theo dõi!",
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
    embed.set_footer(text="Đang lấy dữ liệu từ tracker.gg...")
    msg = await ctx.send(embed=embed)
    
    # Xác thực Riot ID với dữ liệu THẬT
    verification_result = await riot_verifier.verify_riot_id(riot_id, region)
    
    if not verification_result['success']:
        # Xác thực thất bại
        embed = discord.Embed(
            title="❌ Không tìm thấy tài khoản",
            description=f"Không thể xác thực Riot ID: `{riot_id}`",
            color=0xff0000
        )
        
        error_msg = verification_result.get('error', 'Không rõ lý do')
        
        if '404' in error_msg or 'not found' in error_msg.lower():
            embed.add_field(
                name="📝 Có thể do:",
                value="1. ❌ Sai Riot ID hoặc Tagline\n"
                      "2. 🌍 Sai region (vn, na, euw...)\n"
                      "3. 🎮 Chưa chơi TFT mùa này\n"
                      "4. 🔒 Profile đặt chế độ riêng tư",
                inline=False
            )
            embed.add_field(
                name="💡 Cách kiểm tra:",
                value=f"1. Truy cập: https://tracker.gg/tft\n"
                      f"2. Gõ `{riot_id}` vào ô tìm kiếm\n"
                      f"3. Kiểm tra xem có profile không",
                inline=False
            )
        else:
            embed.add_field(name="📝 Lý do:", value=error_msg, inline=False)
        
        await msg.edit(embed=embed)
        return
    
    # Xác thực thành công - hiển thị thông tin THẬT
    account_data = verification_result['data']
    
    embed = discord.Embed(
        title="✅ Đã tìm thấy tài khoản!",
        description=f"**Riot ID:** `{riot_id}`",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    # Thêm thông tin cơ bản
    game_name = account_data.get('game_name', username)
    tagline_display = account_data.get('tagline', tagline)
    
    embed.add_field(
        name="👤 Tên trong game",
        value=f"`{game_name}#{tagline_display}`",
        inline=True
    )
    
    embed.add_field(
        name="🌍 Region",
        value=region.upper(),
        inline=True
    )
    
    # Lấy thông tin TFT THẬT
    tft_info = account_data.get('tft_info', {})
    
    if tft_info:
        # Format rank sang tiếng Việt
        rank_text = tft_info.get('rank', 'Chưa xếp hạng')
        rank_vn = format_rank_vietnamese(rank_text)
        rank_emoji = get_rank_emoji(rank_vn)
        
        # Thêm rank TFT
        lp = tft_info.get('lp', 0)
        rank_display = f"{rank_emoji} **{rank_vn}**"
        if lp > 0:
            rank_display += f"\n`{lp} LP`"
        
        embed.add_field(
            name="📊 Rank TFT",
            value=rank_display,
            inline=True
        )
        
        # Thêm win rate và tổng trận
        wins = tft_info.get('wins', 0)
        losses = tft_info.get('losses', 0)
        total_games = tft_info.get('total_games', wins + losses)
        win_rate = tft_info.get('win_rate', 0)
        
        if total_games > 0:
            stats_text = f"🎮 **{format_large_number(total_games)}** trận\n"
            stats_text += f"✅ **{format_large_number(wins)}** thắng\n"
            stats_text += f"❌ **{format_large_number(losses)}** thua\n"
            stats_text += f"📈 **{win_rate:.1f}%** win rate"
            
            embed.add_field(
                name="📈 Thống kê",
                value=stats_text,
                inline=True
            )
        
        # Thêm level
        level = tft_info.get('level', 0)
        if level > 0:
            embed.add_field(
                name="🎮 Level",
                value=f"**{format_large_number(level)}**",
                inline=True
            )
    
    # Thêm nguồn dữ liệu
    source = verification_result.get('source', 'unknown')
    source_map = {
        'tracker.gg': '📊 tracker.gg',
        'op.gg': '🌐 op.gg',
        'riot_api': '🎮 Riot API'
    }
    
    embed.add_field(
        name="📡 Nguồn dữ liệu",
        value=source_map.get(source, source),
        inline=True
    )
    
    # Thêm hướng dẫn xác nhận
    embed.add_field(
        name="🔐 Bước 2: Xác nhận sở hữu",
        value=f"**Để xác nhận đây là tài khoản của bạn:**\n"
              f"Gõ `{config.PREFIX}confirm {riot_id}`\n\n"
              f"**Hoặc hủy với:** `{config.PREFIX}cancel`",
        inline=False
    )
    
    # Lưu session xác thực tạm thời
    verification_sessions[ctx.author.id] = {
        'riot_id': riot_id,
        'region': region,
        'data': account_data,
        'tft_info': tft_info,
        'timestamp': datetime.now(),
        'message_id': msg.id,
        'channel_id': ctx.channel.id
    }
    
    # Set timeout cho session (15 phút)
    asyncio.create_task(clear_verification_session(ctx.author.id, 900))
    
    await msg.edit(embed=embed)

async def clear_verification_session(user_id, delay_seconds):
    """Xóa session sau một khoảng thời gian"""
    await asyncio.sleep(delay_seconds)
    if user_id in verification_sessions:
        try:
            session = verification_sessions[user_id]
            channel = bot.get_channel(session['channel_id'])
            if channel:
                embed = discord.Embed(
                    title="⏰ Session đã hết hạn",
                    description=f"Session xác thực cho `{session['riot_id']}` đã hết hạn sau 15 phút.",
                    color=0xff9900
                )
                await channel.send(embed=embed)
        except:
            pass
        finally:
            if user_id in verification_sessions:
                del verification_sessions[user_id]

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
            description="Vui lòng bắt đầu với `!track` trước.\nSession chỉ tồn tại trong 15 phút.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    session = verification_sessions[user_id]
    
    # Kiểm tra Riot ID khớp
    if session['riot_id'].lower() != riot_id.lower():
        embed = discord.Embed(
            title="❌ Riot ID không khớp",
            description=f"Session của bạn: `{session['riot_id']}`\nBạn nhập: `{riot_id}`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra thời gian session (15 phút)
    time_diff = datetime.now() - session['timestamp']
    if time_diff.total_seconds() > 900:  # 15 phút
        del verification_sessions[user_id]
        embed = discord.Embed(
            title="⏰ Session hết hạn",
            description="Session đã hết hạn sau 15 phút.\nVui lòng bắt đầu lại với `!track`.",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Lưu player vào database với dữ liệu THẬT
    player_data = {
        'discord_id': str(user_id),
        'discord_name': ctx.author.name,
        'discord_display_name': ctx.author.display_name,
        'riot_id': session['riot_id'],
        'region': session['region'],
        'game_name': session['data'].get('game_name', ''),
        'tagline': session['data'].get('tagline', ''),
        'verified': True,
        'verification_date': datetime.now().isoformat(),
        'tracking_started': datetime.now().isoformat(),
        'channel_id': str(ctx.channel.id),
        'tft_info': session['tft_info'],
        'settings': {
            'auto_notify': True,
            'include_ai_analysis': True if gemini_analyzer.is_enabled() else False,
            'mention_on_notify': True,
            'notify_on_top4': True,
            'notify_on_win': True
        },
        'last_checked': datetime.now().isoformat(),
        'stats': {
            'total_notifications': 0,
            'last_match_time': None,
            'average_placement': 0
        }
    }
    
    # Sửa: Đổi tên biến 'success' thành 'db_result' để tránh conflict
    db_result = db.add_player(player_data)
    
    if not db_result:
        embed = discord.Embed(
            title="❌ Lỗi khi lưu dữ liệu",
            description="Vui lòng thử lại sau.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Xóa session
    del verification_sessions[user_id]
    
    # Format rank tiếng Việt cho thông báo
    rank_text = session['tft_info'].get('rank', 'Chưa xếp hạng')
    rank_vn = format_rank_vietnamese(rank_text)
    rank_emoji = get_rank_emoji(rank_vn)
    
    # Thông báo thành công
    embed = discord.Embed(
        title="🎉 Đã xác thực thành công!",
        description=f"Bắt đầu theo dõi **{session['riot_id']}**",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Thông tin đã lưu",
        value=f"• 🎮 Riot ID: `{session['riot_id']}`\n"
              f"• 🌍 Region: `{session['region'].upper()}`\n"
              f"• 📊 Rank: {rank_emoji} {rank_vn}\n"
              f"• ✅ Verified: Đã xác thực",
        inline=False
    )
    
    embed.add_field(
        name="🔄 Tự động hóa",
        value="• 🤖 Bot kiểm tra mỗi **5 phút**\n"
              "• 🔔 Thông báo khi có trận TFT mới\n"
              "• 🤖 Phân tích AI tự động",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Cài đặt",
        value=f"• Dùng `{config.PREFIX}settings` để thay đổi\n"
              f"• Dùng `{config.PREFIX}myplayers` để xem danh sách\n"
              f"• Dùng `{config.PREFIX}untrack` để dừng theo dõi",
        inline=False
    )
    
    embed.set_footer(text="Bot sẽ thông báo khi có trận đấu mới!")
    
    await ctx.send(embed=embed)
    
    # Cập nhật bot status
    await update_bot_status()

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
    Usage: !untrack [RiotID/số]
    """
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord_id(user_id)
    
    if not players:
        embed = discord.Embed(
            title="📭 Không có player nào",
            description="Bạn chưa theo dõi player nào cả.",
            color=0x7289DA
        )
        embed.add_field(
            name="🎮 Bắt đầu theo dõi:",
            value=f"`{config.PREFIX}track TênGame#Tagline`",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Nếu không có riot_id, hiển thị danh sách để chọn
    if not riot_id:
        embed = discord.Embed(
            title="📋 Chọn player để dừng theo dõi",
            description=f"Gõ `{config.PREFIX}untrack [số]`",
            color=0x7289DA
        )
        
        for i, player in enumerate(players, 1):
            rank_text = player.get('tft_info', {}).get('rank', 'Chưa xếp hạng')
            rank_vn = format_rank_vietnamese(rank_text)
            rank_emoji = get_rank_emoji(rank_vn)
            
            embed.add_field(
                name=f"{i}. {player['riot_id']}",
                value=f"{rank_emoji} {rank_vn}\n"
                      f"Theo dõi từ: {player['tracking_started'][:10]}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        return
    
    # Nếu riot_id là số, tìm player theo index
    if riot_id.isdigit():
        idx = int(riot_id) - 1
        
        if 0 <= idx < len(players):
            riot_id = players[idx]['riot_id']
        else:
            await ctx.send("❌ Số thứ tự không hợp lệ!")
            return
    
    # Xóa player
    db_result = db.remove_player(user_id, riot_id)
    
    if db_result:
        embed = discord.Embed(
            title="✅ Đã dừng theo dõi",
            description=f"Không theo dõi `{riot_id}` nữa.",
            color=0x00ff00
        )
        
        # Cập nhật status
        await update_bot_status()
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
            title="📭 Chưa theo dõi ai",
            description="Bạn chưa theo dõi player nào.",
            color=0x7289DA
        )
        embed.add_field(
            name="🎮 Bắt đầu theo dõi:",
            value=f"`{config.PREFIX}track TênGame#Tagline`\nVí dụ: `{config.PREFIX}track DarkViPer#VN2`",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    total_games = sum(p.get('tft_info', {}).get('total_games', 0) for p in players)
    total_wins = sum(p.get('tft_info', {}).get('wins', 0) for p in players)
    avg_win_rate = (total_wins / total_games * 100) if total_games > 0 else 0
    
    embed = discord.Embed(
        title=f"📋 Đang theo dõi {len(players)} player(s)",
        description=f"👤 {ctx.author.display_name}",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    
    for player in players:
        tft_info = player.get('tft_info', {})
        rank_text = tft_info.get('rank', 'Chưa xếp hạng')
        rank_vn = format_rank_vietnamese(rank_text)
        rank_emoji = get_rank_emoji(rank_vn)
        
        wins = tft_info.get('wins', 0)
        total_games_player = tft_info.get('total_games', 0)
        win_rate = (wins / total_games_player * 100) if total_games_player > 0 else 0
        
        embed.add_field(
            name=f"{rank_emoji} {player['riot_id']}",
            value=f"• 📊 {rank_vn}\n"
                  f"• 🏆 {wins}/{total_games_player} ({win_rate:.1f}%)\n"
                  f"• ⏰ Từ {player.get('tracking_started', 'N/A')[:10]}",
            inline=True
        )
    
    embed.add_field(
        name="📈 Tổng thống kê",
        value=f"• 🎮 Tổng trận: **{format_large_number(total_games)}**\n"
              f"• ✅ Win rate: **{avg_win_rate:.1f}%**\n"
              f"• 👥 Players: **{len(players)}**",
        inline=False
    )
    
    embed.set_footer(text=f"Dùng {config.PREFIX}untrack [số] để dừng theo dõi")
    await ctx.send(embed=embed)

@bot.command(name='playerinfo')
async def player_info(ctx, riot_id: str = None):
    """Xem thông tin chi tiết của player"""
    user_id = str(ctx.author.id)
    
    # Nếu không có riot_id, lấy players của user
    if not riot_id:
        players = db.get_players_by_discord_id(user_id)
        
        if not players:
            await ctx.send("❌ Bạn không theo dõi ai cả!")
            return
        
        # Hiển thị danh sách để chọn
        embed = discord.Embed(
            title="📋 Chọn player để xem thông tin",
            description=f"Gõ `{config.PREFIX}playerinfo [số]`",
            color=0x7289DA
        )
        
        for i, player in enumerate(players, 1):
            rank_text = player.get('tft_info', {}).get('rank', 'Chưa xếp hạng')
            rank_vn = format_rank_vietnamese(rank_text)
            
            embed.add_field(
                name=f"{i}. {player['riot_id']}",
                value=f"{rank_vn}\nTheo dõi từ: {player['tracking_started'][:10]}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        return
    
    # Nếu riot_id là số, tìm player theo index
    if riot_id.isdigit():
        players = db.get_players_by_discord_id(user_id)
        idx = int(riot_id) - 1
        
        if 0 <= idx < len(players):
            player = players[idx]
            riot_id = player['riot_id']
        else:
            await ctx.send("❌ Số thứ tự không hợp lệ!")
            return
    
    # Tìm player
    player = db.get_player_by_riot_id(riot_id)
    
    if not player or player['discord_id'] != user_id:
        await ctx.send("❌ Bạn không theo dõi player này!")
        return
    
    # Lấy dữ liệu mới nhất từ API
    await ctx.send(f"🔍 Đang cập nhật thông tin mới nhất cho `{riot_id}`...")
    
    new_overview = await tft_service.get_player_overview(riot_id, player['region'])
    
    if new_overview:
        # Cập nhật thông tin mới
        player['tft_info'] = new_overview
        db.update_player_info(user_id, riot_id, 'tft_info', new_overview)
    
    # Hiển thị thông tin chi tiết
    tft_info = player.get('tft_info', {})
    rank_text = tft_info.get('rank', 'Chưa xếp hạng')
    rank_vn = format_rank_vietnamese(rank_text)
    rank_emoji = get_rank_emoji(rank_vn)
    
    embed = discord.Embed(
        title=f"{rank_emoji} Thông tin chi tiết - {riot_id}",
        description=f"Region: {player.get('region', 'vn').upper()}",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    
    # Thông tin cơ bản
    embed.add_field(
        name="👤 Thông tin game",
        value=f"• 🎮 Riot ID: `{riot_id}`\n"
              f"• 🌍 Region: {player.get('region', 'vn').upper()}\n"
              f"• ✅ Verified: {'✅ Đã xác thực' if player.get('verified') else '❌ Chưa xác thực'}\n"
              f"• 🗓️ Theo dõi từ: {player.get('tracking_started', 'N/A')[:10]}",
        inline=False
    )
    
    # Thông tin rank TFT
    lp = tft_info.get('lp', 0)
    wins = tft_info.get('wins', 0)
    losses = tft_info.get('losses', 0)
    total_games = tft_info.get('total_games', wins + losses)
    win_rate = tft_info.get('win_rate', 0)
    level = tft_info.get('level', 0)
    
    embed.add_field(
        name="📊 Rank TFT",
        value=f"• {rank_emoji} **{rank_vn}**\n"
              f"• 🏆 **{lp} LP**\n"
              f"• 🎮 Level: **{level}**",
        inline=True
    )
    
    embed.add_field(
        name="📈 Thống kê",
        value=f"• 🎮 **{format_large_number(total_games)}** trận\n"
              f"• ✅ **{format_large_number(wins)}** thắng\n"
              f"• ❌ **{format_large_number(losses)}** thua\n"
              f"• 📊 **{win_rate:.1f}%** win rate",
        inline=True
    )
    
    # Thông tin thông báo
    settings = player.get('settings', {})
    embed.add_field(
        name="🔔 Cài đặt thông báo",
        value=f"• 🤖 AI Analysis: {'✅ Bật' if settings.get('include_ai_analysis') else '❌ Tắt'}\n"
              f"• 👤 Mention: {'✅ Bật' if settings.get('mention_on_notify') else '❌ Tắt'}\n"
              f"• 🔔 Auto-notify: {'✅ Bật' if settings.get('auto_notify') else '❌ Tắt'}",
        inline=True
    )
    
    # Match history gần nhất
    if total_games > 0:
        match_history = await tft_service.get_match_history(riot_id, player['region'], limit=3)
        
        if match_history:
            history_text = ""
            for match in match_history[:3]:
                placement = match.get('placement', 8)
                emoji = "👑" if placement == 1 else "🥈" if placement <= 4 else "📉"
                history_text += f"{emoji} Top #{placement}\n"
            
            embed.add_field(
                name="🎮 3 trận gần nhất",
                value=history_text,
                inline=True
            )
    
    embed.set_footer(text=f"Dùng {config.PREFIX}forcecheck {riot_id} để kiểm tra ngay")
    await ctx.send(embed=embed)

# ========== MATCH CHECKING & NOTIFICATION ==========

@tasks.loop(minutes=5)
async def auto_check_matches():
    """Tự động kiểm tra trận đấu mới mỗi 5 phút"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Đang kiểm tra TFT matches...")
    
    players = db.get_all_players()
    
    if not players:
        return
    
    checked_count = 0
    notified_count = 0
    
    for player in players:
        try:
            # Kiểm tra auto-notify setting
            settings = player.get('settings', {})
            if not settings.get('auto_notify', True):
                continue
            
            result = await check_and_notify_player(player)
            checked_count += 1
            
            if result.get('notified'):
                notified_count += 1
            
            await asyncio.sleep(1)  # Delay để tránh rate limit
            
        except Exception as e:
            print(f"[ERROR] Kiểm tra {player.get('riot_id', 'unknown')}: {e}")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Đã kiểm tra {checked_count} players, thông báo {notified_count} match mới")

async def check_and_notify_player(player):
    """Kiểm tra và thông báo match mới cho một player"""
    result = {'notified': False, 'error': None}
    
    try:
        riot_id = player['riot_id']
        region = player.get('region', 'vn')
        channel_id = int(player['channel_id'])
        
        # Lấy channel
        channel = bot.get_channel(channel_id)
        if not channel:
            result['error'] = f"Channel {channel_id} không tồn tại"
            return result
        
        # Lấy match history từ dữ liệu THẬT
        matches = await tft_service.get_match_history(riot_id, region, limit=3)
        
        if not matches or len(matches) == 0:
            result['error'] = "Không có match history"
            return result
        
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
            
            # Cập nhật stats
            stats = player.get('stats', {})
            stats['total_notifications'] = stats.get('total_notifications', 0) + 1
            stats['last_match_time'] = datetime.now().isoformat()
            
            # Tính average placement
            placements = []
            for match in matches[:5]:
                placements.append(match.get('placement', 8))
            
            if placements:
                avg_placement = sum(placements) / len(placements)
                stats['average_placement'] = round(avg_placement, 2)
            
            db.update_player_info(player['discord_id'], riot_id, 'stats', stats)
            
            # Gửi thông báo
            await send_match_notification(channel, player, latest_match)
            
            result['notified'] = True
            print(f"[MATCH] Đã thông báo match mới của {riot_id}: Top #{latest_match.get('placement')}")
    
    except Exception as e:
        result['error'] = str(e)
        print(f"[ERROR] check_and_notify_player: {e}")
    
    return result

async def send_match_notification(channel, player, match_data):
    """Gửi thông báo trận đấu mới với dữ liệu THẬT"""
    try:
        riot_id = player['riot_id']
        settings = player.get('settings', {})
        
        # Tạo mention
        mention = ""
        if settings.get('mention_on_notify', True):
            discord_user = await bot.fetch_user(int(player['discord_id']))
            mention = f"{discord_user.mention} "
        
        # Lấy thông tin placement
        placement = match_data.get('placement', 8)
        level = match_data.get('level', 'N/A')
        
        # Màu và emoji theo placement
        if placement == 1:
            color = 0xFFD700  # Vàng
            emoji = "👑"
            title = "CHIẾN THẮNG!"
        elif placement <= 4:
            color = 0xC0C0C0  # Bạc
            emoji = "🥈"
            title = "TOP 4!"
        else:
            color = 0xCD7F32  # Đồng
            emoji = "📉"
            title = "Hoàn thành trận đấu"
        
        # Lấy rank hiện tại của player
        rank_info = await tft_service.get_live_rank(riot_id, player.get('region', 'vn'))
        current_rank = rank_info.get('rank', 'Unknown') if rank_info else 'Unknown'
        rank_vn = format_rank_vietnamese(current_rank)
        rank_emoji = get_rank_emoji(rank_vn)
        
        # Tạo embed
        embed = discord.Embed(
            title=f"{emoji} {riot_id} {title}",
            description=f"**🏆 Placement:** #{placement} | **📊 Level:** {level}",
            color=color,
            timestamp=datetime.now()
        )
        
        # Thêm thông tin rank hiện tại
        embed.add_field(
            name=f"{rank_emoji} Rank hiện tại",
            value=f"**{rank_vn}**",
            inline=True
        )
        
        # Thêm thông tin đội hình
        traits = match_data.get('traits', [])
        if traits:
            # Lấy top 3 traits
            top_traits = sorted(traits, key=lambda x: x.get('tier', 0), reverse=True)[:3]
            
            traits_text = ""
            for trait in top_traits:
                name = trait.get('name', 'Unknown')
                tier = trait.get('tier', 1)
                stars = "⭐" * min(tier, 3)
                traits_text += f"{stars} {name}\n"
            
            embed.add_field(
                name="🏆 Top 3 Traits",
                value=traits_text,
                inline=True
            )
        
        # Thêm thông tin units
        units = match_data.get('units', [])
        if units:
            # Lấy top 4 units
            top_units = units[:4]
            
            units_text = ""
            for unit in top_units:
                name = unit.get('character_id', 'Unknown')
                name = name.replace('TFT', '').replace('_', ' ').title()
                tier = unit.get('tier', 1)
                stars = "★" * tier
                units_text += f"{stars} {name}\n"
            
            embed.add_field(
                name="⚔️ Units chính",
                value=units_text,
                inline=True
            )
        
        # Thêm phân tích AI nếu được bật
        if settings.get('include_ai_analysis', True) and gemini_analyzer.is_enabled():
            ai_analysis = await gemini_analyzer.analyze_match(match_data, riot_id)
            if ai_analysis:
                # Cắt ngắn nếu quá dài
                if len(ai_analysis) > 800:
                    ai_analysis = ai_analysis[:800] + "..."
                
                embed.add_field(
                    name="🤖 Phân tích AI",
                    value=ai_analysis,
                    inline=False
                )
        
        # Footer với thông tin match
        match_time = match_data.get('timestamp')
        if match_time:
            try:
                match_dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
                time_ago = datetime.now() - match_dt
                minutes_ago = int(time_ago.total_seconds() / 60)
                
                if minutes_ago < 60:
                    time_text = f"{minutes_ago} phút trước"
                else:
                    hours_ago = minutes_ago // 60
                    time_text = f"{hours_ago} giờ trước"
            except:
                time_text = "Vừa xong"
        else:
            time_text = "Vừa xong"
        
        embed.set_footer(
            text=f"TFT Auto Tracker • {time_text} • ID: {match_data.get('match_id', '')[:8]}",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        # Gửi thông báo
        await channel.send(mention, embed=embed)
        
        # Gửi thêm tin nhắn chúc mừng nếu top 1
        if placement == 1:
            congrats_embed = discord.Embed(
                title="🎉 CHÚC MỪNG CHIẾN THẮNG! 🎉",
                description=f"**{riot_id}** vừa giành TOP 1!",
                color=0xFFD700
            )
            await channel.send(embed=congrats_embed)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] send_match_notification: {e}")
        return False

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
        
        notified_count = 0
        for player in players:
            try:
                result = await check_and_notify_player(player)
                if result.get('notified'):
                    notified_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[ERROR] Force check {player['riot_id']}: {e}")
        
        if notified_count > 0:
            await msg.edit(content=f"✅ Đã kiểm tra xong! Thông báo {notified_count} match mới.")
        else:
            await msg.edit(content="✅ Đã kiểm tra xong! Không có match mới.")
        
        return
    
    # Kiểm tra specific player
    player = db.get_player_by_riot_id(riot_id)
    
    if not player or player['discord_id'] != user_id:
        await ctx.send("❌ Bạn không theo dõi player này!")
        return
    
    msg = await ctx.send(f"🔍 Đang kiểm tra {riot_id}...")
    
    result = await check_and_notify_player(player)
    
    if result.get('notified'):
        await msg.edit(content=f"✅ Đã thông báo match mới của {riot_id}!")
    elif result.get('error'):
        await msg.edit(content=f"⚠️ Không có match mới. Lỗi: {result['error'][:100]}")
    else:
        await msg.edit(content=f"✅ Đã kiểm tra {riot_id}! Không có match mới.")

# ========== UTILITY COMMANDS ==========

@bot.command(name='ping')
async def ping_command(ctx):
    """Kiểm tra độ trễ"""
    start_time = datetime.now()
    
    # Tính ping
    latency = round(bot.latency * 1000)
    
    # Lấy thông tin bot
    players = db.get_all_players()
    bot_start_time = getattr(bot, 'start_time', datetime.now())
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms**",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Thống kê bot",
        value=f"• 👥 Players: **{len(players)}**\n"
              f"• 🎮 Servers: **{len(bot.guilds)}**\n"
              f"• ⏰ Uptime: **{get_uptime(bot_start_time)}**",
        inline=True
    )
    
    embed.add_field(
        name="🤖 Dịch vụ",
        value=f"• Gemini AI: **{gemini_analyzer.status}**\n"
              f"• Riot API: **{'✅ Có' if riot_verifier.has_api_key else '⚠️ Không'}**\n"
              f"• Auto-check: **{'✅ Đang chạy' if auto_check_matches.is_running() else '❌ Dừng'}**",
        inline=True
    )
    
    # Lấy thông tin database
    db_stats = db.get_stats()
    embed.add_field(
        name="🗄️ Database",
        value=f"• 📁 Size: **{db_stats.get('database_size', 0) // 1024} KB**\n"
              f"• ✨ Verified: **{db_stats.get('verified_players', 0)}**\n"
              f"• 🔄 Modified: **{db_stats.get('last_modified', 'N/A')[:10]}**",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Hiển thị hướng dẫn"""
    embed = discord.Embed(
        title="🎮 TFT Auto Tracker - Hướng dẫn",
        description="Bot tự động thông báo TFT matches với dữ liệu THẬT từ tracker.gg",
        color=0x7289DA
    )
    
    # Commands
    commands_section = [
        (f"{config.PREFIX}track <Tên#Tag> [region]", "Bắt đầu theo dõi player (2 bước)"),
        (f"{config.PREFIX}confirm <RiotID>", "Xác nhận sở hữu tài khoản"),
        (f"{config.PREFIX}myplayers", "Danh sách players bạn theo dõi"),
        (f"{config.PREFIX}playerinfo [RiotID/số]", "Thông tin chi tiết player"),
        (f"{config.PREFIX}untrack [RiotID/số]", "Dừng theo dõi"),
        (f"{config.PREFIX}forcecheck [RiotID]", "Kiểm tra ngay lập tức"),
        (f"{config.PREFIX}settings", "Cài đặt thông báo"),
        (f"{config.PREFIX}ping", "Kiểm tra độ trễ và thống kê"),
        (f"{config.PREFIX}help", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands_section:
        embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
    
    # Ví dụ
    embed.add_field(
        name="📝 Ví dụ sử dụng:",
        value=f"```\n"
              f"# Bước 1: Bắt đầu theo dõi\n"
              f"{config.PREFIX}track DarkViPer#VN2 vn\n\n"
              f"# Bot hiển thị thông tin THẬT từ tracker.gg\n"
              f"# Kiểm tra rank, win rate, v.v.\n\n"
              f"# Bước 2: Xác nhận sở hữu\n"
              f"{config.PREFIX}confirm DarkViPer#VN2\n\n"
              f"# Bot bắt đầu theo dõi tự động!\n"
              f"```",
        inline=False
    )
    
    # Features
    embed.add_field(
        name="✨ Tính năng:",
        value="• ✅ **Dữ liệu THẬT** từ tracker.gg/op.gg\n"
              "• 🔄 **Tự động thông báo** mỗi 5 phút\n"
              "• 🤖 **Phân tích AI** bằng Gemini\n"
              "• 📊 **Rank tiếng Việt** dễ đọc\n"
              "• 🎮 **Xác thực 2 bước** an toàn",
        inline=False
    )
    
    # Sources
    embed.add_field(
        name="📡 Nguồn dữ liệu:",
        value="• 📊 tracker.gg - Rank và thống kê\n"
              "• 🌐 op.gg - Dự phòng khi tracker.gg lỗi\n"
              "• 🤖 Gemini AI - Phân tích đội hình",
        inline=False
    )
    
    players_count = len(db.get_all_players())
    embed.set_footer(
        text=f"Prefix: {config.PREFIX} • Đang theo dõi: {players_count} players • Dữ liệu THẬT 100%"
    )
    
    await ctx.send(embed=embed)

@bot.command(name='settings')
async def settings_command(ctx, setting: str = None, value: str = None):
    """Cài đặt thông báo"""
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord_id(user_id)
    
    if not players:
        embed = discord.Embed(
            title="❌ Chưa theo dõi player nào",
            description="Hãy dùng `!track` để bắt đầu theo dõi trước.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    if not setting:
        # Hiển thị current settings
        embed = discord.Embed(
            title="⚙️ Cài đặt thông báo",
            description=f"Dùng `{config.PREFIX}settings [tên] [on/off]` để thay đổi",
            color=0x7289DA
        )
        
        for player in players:
            settings = player.get('settings', {})
            rank_text = player.get('tft_info', {}).get('rank', 'Chưa xếp hạng')
            rank_vn = format_rank_vietnamese(rank_text)
            
            embed.add_field(
                name=f"🎮 {player['riot_id']}",
                value=f"{rank_vn}\n"
                      f"• 🔔 Mention: {'✅' if settings.get('mention_on_notify', True) else '❌'}\n"
                      f"• 🤖 AI Analysis: {'✅' if settings.get('include_ai_analysis', True) else '❌'}\n"
                      f"• 🎯 Auto-notify: {'✅' if settings.get('auto_notify', True) else '❌'}",
                inline=True
        )
        
        await ctx.send(embed=embed)
        return
    
    # Update settings
    valid_settings = ['mention', 'ai', 'notify']
    setting_map = {
        'mention': 'mention_on_notify',
        'ai': 'include_ai_analysis',
        'notify': 'auto_notify'
    }
    
    if setting.lower() not in setting_map:
        embed = discord.Embed(
            title="❌ Setting không hợp lệ",
            description=f"Setting hợp lệ: {', '.join(valid_settings)}",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    if value is None:
        embed = discord.Embed(
            title="❌ Thiếu giá trị",
            description="Dùng: `on`, `off`, `true`, `false`, `1`, `0`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Parse giá trị
    value_lower = value.lower()
    if value_lower in ['on', 'true', 'yes', '1', 'enable', 'bật']:
        value_bool = True
        display_value = "✅ Bật"
    elif value_lower in ['off', 'false', 'no', '0', 'disable', 'tắt']:
        value_bool = False
        display_value = "❌ Tắt"
    else:
        await ctx.send("❌ Giá trị không hợp lệ! Dùng `on` hoặc `off`")
        return
    
    # Update cho tất cả players của user
    updated_count = 0
    setting_key = setting_map[setting.lower()]
    
    for player in players:
        riot_id = player['riot_id']
        if db.update_setting(user_id, riot_id, setting_key, value_bool):
            updated_count += 1
    
    # Tên setting hiển thị
    setting_names = {
        'mention': 'Mention khi thông báo',
        'ai': 'Phân tích AI',
        'notify': 'Tự động thông báo'
    }
    
    embed = discord.Embed(
        title="⚙️ Đã cập nhật cài đặt",
        description=f"{display_value} **{setting_names[setting.lower()]}** cho {updated_count} player(s)",
        color=0x00ff00
    )
    
    await ctx.send(embed=embed)

# ========== RUN BOT ==========

if __name__ == "__main__":
    # Validate config
    errors = Config.validate()
    if errors:
        print("❌ Lỗi cấu hình:")
        for error in errors:
            print(f"  - {error}")
        exit(1)
    
    print("🚀 Khởi động TFT Auto Tracker Bot...")
    print(f"📁 Database: {Config.DB_FILE}")
    print(f"🤖 Gemini AI: {gemini_analyzer.status}")
    print(f"🎮 Riot API: {'✅ Có key' if riot_verifier.has_api_key else '⚠️ Không có key'}")
    print(f"🔧 Prefix: {config.PREFIX}")
    print(f"🔄 Auto-check: Mỗi {config.AUTO_CHECK_INTERVAL} phút")
    
    # Lưu thời gian bắt đầu
    bot.start_time = datetime.now()
    
    # Chạy bot
    bot.run(config.DISCORD_TOKEN)
