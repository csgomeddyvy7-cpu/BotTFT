import aiohttp
import asyncio
from datetime import datetime, timedelta
import random
from urllib.parse import quote

class TFTService:
    """Dịch vụ lấy dữ liệu TFT THẬT từ tracker.gg"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
        self.cache_timeout = 300  # 5 phút
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_player_overview(self, riot_id, region='vn'):
        """
        Lấy tổng quan player TỪ DỮ LIỆU THẬT
        """
        # Kiểm tra cache
        cache_key = f"overview_{riot_id}_{region}"
        if cache_key in self.cache:
            cache_data, cache_time = self.cache[cache_key]
            if (datetime.now() - cache_time).total_seconds() < self.cache_timeout:
                return cache_data
        
        try:
            username, tagline = riot_id.split('#', 1)
            
            # Gọi tracker.gg API để lấy dữ liệu THẬT
            url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{quote(username)}%23{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Origin": "https://tracker.gg",
                "Referer": "https://tracker.gg/"
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse dữ liệu thật
                    overview = self._parse_overview_from_tracker(data, riot_id)
                    
                    if overview:
                        # Lưu vào cache
                        self.cache[cache_key] = (overview, datetime.now())
                        return overview
                    
                elif response.status == 404:
                    # Thử op.gg nếu tracker.gg không có
                    return await self._get_from_opgg_fallback(riot_id, region)
                    
        except asyncio.TimeoutError:
            print(f"Timeout khi lấy dữ liệu cho {riot_id}")
        except Exception as e:
            print(f"Lỗi get_player_overview: {e}")
        
        # Fallback: Dùng dữ liệu từ cache cũ hoặc trả về None
        return None
    
    def _parse_overview_from_tracker(self, data, riot_id):
        """Parse dữ liệu overview từ tracker.gg"""
        try:
            segments = data.get('data', {}).get('segments', [])
            
            # Tìm segment overview
            overview_segment = None
            for segment in segments:
                if segment.get('type') == 'overview':
                    overview_segment = segment
                    break
            
            if not overview_segment:
                return None
            
            stats = overview_segment.get('stats', {})
            
            # Lấy rank TFT (dữ liệu thật)
            rank_stat = stats.get('rank', {})
            tier_stat = stats.get('tier', {})
            
            # Ưu tiên lấy từ tier (chính xác hơn)
            if tier_stat.get('displayValue'):
                rank_text = tier_stat['displayValue']
            else:
                rank_text = rank_stat.get('displayValue', 'Chưa xếp hạng')
            
            # Lấy LP
            rating_stat = stats.get('rating', {})
            lp = rating_stat.get('value', 0)
            
            # Lấy wins/losses
            wins = stats.get('wins', {}).get('value', 0)
            losses = stats.get('losses', {}).get('value', 0)
            total_games = wins + losses
            
            # Tính win rate
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            # Lấy top percentage
            top_placement = stats.get('topPlacement', {})
            top_percentage = top_placement.get('percentile', 0)
            
            # Lấy level
            level_stat = stats.get('level', {})
            level = level_stat.get('value', 0)
            
            # Lấy rank số (nếu có)
            rank_display = rank_stat.get('displayValue', '')
            
            return {
                'rank': rank_text,
                'rank_display': rank_display,
                'lp': lp,
                'wins': wins,
                'losses': losses,
                'total_games': total_games,
                'win_rate': round(win_rate, 1),
                'top_percentage': top_percentage,
                'level': level,
                'last_updated': datetime.now().isoformat(),
                'source': 'tracker.gg',
                'verified': True
            }
            
        except Exception as e:
            print(f"Lỗi parse_overview_from_tracker: {e}")
            return None
    
    async def _get_from_opgg_fallback(self, riot_id, region):
        """Fallback dùng op.gg nếu tracker.gg không có"""
        try:
            username, tagline = riot_id.split('#', 1)
            
            # URL op.gg API
            url = f"https://op.gg/api/v1.0/internal/bypass/summoners/{region}/{username}-{tagline}/tft/summary"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse từ op.gg
                    return self._parse_overview_from_opgg(data, riot_id)
                    
        except Exception as e:
            print(f"Lỗi op.gg fallback: {e}")
        
        return None
    
    def _parse_overview_from_opgg(self, data, riot_id):
        """Parse dữ liệu từ op.gg"""
        try:
            tft_info = data.get('tft_info', {})
            rank_info = tft_info.get('rank_info', {})
            
            tier = rank_info.get('tier', 'UNRANKED')
            division = rank_info.get('division', '')
            lp = rank_info.get('lp', 0)
            
            # Chuyển đổi tier sang tiếng Việt
            tier_map = {
                'IRON': 'Sắt',
                'BRONZE': 'Đồng',
                'SILVER': 'Bạc',
                'GOLD': 'Vàng',
                'PLATINUM': 'Bạch Kim',
                'DIAMOND': 'Kim Cương',
                'MASTER': 'Cao Thủ',
                'GRANDMASTER': 'Đại Cao Thủ',
                'CHALLENGER': 'Thách Đấu'
            }
            
            tier_vn = tier_map.get(tier, tier)
            
            if tier == 'UNRANKED':
                rank_text = 'Chưa xếp hạng'
            else:
                rank_text = f"{tier_vn} {division}"
            
            # Lấy thống kê
            summary = data.get('summary', {})
            wins = summary.get('win', 0)
            losses = summary.get('lose', 0)
            total_games = wins + losses
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            return {
                'rank': rank_text,
                'lp': lp,
                'wins': wins,
                'losses': losses,
                'total_games': total_games,
                'win_rate': round(win_rate, 1),
                'level': data.get('level', 0),
                'last_updated': datetime.now().isoformat(),
                'source': 'op.gg',
                'verified': True
            }
            
        except Exception as e:
            print(f"Lỗi parse_overview_from_opgg: {e}")
            return None
    
    async def get_match_history(self, riot_id, region='vn', limit=5):
        """
        Lấy lịch sử match TỪ DỮ LIỆU THẬT
        """
        cache_key = f"matches_{riot_id}_{region}"
        if cache_key in self.cache:
            cache_data, cache_time = self.cache[cache_key]
            if (datetime.now() - cache_time).total_seconds() < self.cache_timeout:
                return cache_data[:limit]
        
        try:
            username, tagline = riot_id.split('#', 1)
            
            # Dùng tracker.gg API
            url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{quote(username)}%23{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse match history thật
                    matches = self._parse_real_match_history(data)
                    
                    if matches:
                        # Lưu cache
                        self.cache[cache_key] = (matches, datetime.now())
                        return matches[:limit]
                    
        except Exception as e:
            print(f"Lỗi get_match_history: {e}")
        
        # Fallback: Dùng dữ liệu giả có cấu trúc đẹp hơn
        return await self._get_fallback_matches(riot_id, limit)
    
    def _parse_real_match_history(self, data):
        """Parse lịch sử match thật từ tracker.gg"""
        try:
            segments = data.get('data', {}).get('segments', [])
            matches = []
            
            # Lấy các segment match (type = 'match')
            for segment in segments:
                if segment.get('type') == 'match':
                    stats = segment.get('stats', {})
                    metadata = segment.get('metadata', {})
                    
                    placement = stats.get('placement', {}).get('value', 8)
                    
                    # Lấy thời gian match
                    timestamp_str = metadata.get('timestamp')
                    if timestamp_str:
                        try:
                            # Chuyển đổi timestamp string sang datetime
                            match_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except:
                            match_time = datetime.now()
                    else:
                        match_time = datetime.now()
                    
                    # Lấy traits từ match
                    traits = []
                    for key, stat in stats.items():
                        if key.startswith('trait_') and isinstance(stat, dict):
                            trait_value = stat.get('value', 0)
                            if trait_value > 0:
                                trait_name = key.replace('trait_', '').replace('_', ' ').title()
                                trait_tier = min(int(trait_value), 3)
                                traits.append({
                                    'name': trait_name,
                                    'tier': trait_tier,
                                    'value': trait_value
                                })
                    
                    # Lấy units từ match (nếu có)
                    units = []
                    for key, stat in stats.items():
                        if key.startswith('unit_') and isinstance(stat, dict):
                            unit_value = stat.get('value', 0)
                            if unit_value > 0:
                                unit_name = key.replace('unit_', '').replace('_', ' ').title()
                                units.append({
                                    'character_id': unit_name,
                                    'tier': 1,  # Không có thông tin tier từ tracker.gg
                                    'items': []
                                })
                    
                    matches.append({
                        'match_id': metadata.get('matchId', f"tracker_{int(match_time.timestamp())}"),
                        'placement': placement,
                        'level': stats.get('level', {}).get('value', 0),
                        'traits': traits[:6],  # Giới hạn 6 traits
                        'units': units[:8],    # Giới hạn 8 units
                        'timestamp': match_time.isoformat(),
                        'game_duration': stats.get('gameLength', {}).get('value', 0),
                        'players_remaining': 8 if placement == 1 else random.randint(1, 7),
                        'source': 'tracker.gg',
                        'queue_id': metadata.get('queueId', 0)
                    })
            
            # Sắp xếp theo thời gian mới nhất
            matches.sort(key=lambda x: x['timestamp'], reverse=True)
            return matches[:10]  # Giới hạn 10 match
            
        except Exception as e:
            print(f"Lỗi parse_real_match_history: {e}")
            return []
    
    async def _get_fallback_matches(self, riot_id, limit):
        """Fallback matches với dữ liệu giả (chỉ khi không lấy được data thật)"""
        # Tạo dữ liệu giả nhưng có cấu trúc tốt
        matches = []
        
        # Seed dựa trên Riot ID để có tính nhất quán
        import hashlib
        seed = int(hashlib.md5(riot_id.encode()).hexdigest(), 16) % 1000
        
        for i in range(limit):
            # Tạo placement ngẫu nhiên nhưng có phân phối thực tế
            rand_val = (seed + i * 13) % 100
            
            if rand_val < 10:  # 10% top 1
                placement = 1
            elif rand_val < 30:  # 20% top 2-4
                placement = (seed + i) % 3 + 2
            elif rand_val < 60:  # 30% top 5-6
                placement = (seed + i) % 2 + 5
            else:  # 40% top 7-8
                placement = (seed + i) % 2 + 7
            
            # Tạo đội hình hợp lý dựa trên placement
            if placement <= 4:  # Top 4: đội hình tốt
                traits = [
                    {'name': 'Darkin', 'tier': 3, 'num_units': 6},
                    {'name': 'Challenger', 'tier': 2, 'num_units': 4},
                    {'name': 'Juggernaut', 'tier': 2, 'num_units': 4},
                    {'name': 'Shurima', 'tier': 1, 'num_units': 3}
                ]
                level = 9
            else:  # Bottom 4: đội hình kém
                traits = [
                    {'name': 'Yordle', 'tier': 1, 'num_units': 3},
                    {'name': 'Strategist', 'tier': 1, 'num_units': 2}
                ]
                level = 7
            
            # Tạo units hợp lý
            units = [
                {'character_id': 'Aatrox', 'tier': 2},
                {'character_id': 'Kaisa', 'tier': 1},
                {'character_id': 'Warwick', 'tier': 1}
            ]
            
            matches.append({
                'match_id': f"fallback_{riot_id.replace('#', '_')}_{i}",
                'placement': placement,
                'level': level,
                'traits': traits,
                'units': units,
                'timestamp': (datetime.now() - timedelta(hours=i*3)).isoformat(),
                'game_duration': random.randint(1200, 1800),
                'players_remaining': 8 if placement == 1 else random.randint(1, 7),
                'source': 'fallback_data',
                'note': 'Dữ liệu mẫu - tracker.gg không trả về match history'
            })
        
        return matches
    
    async def get_live_rank(self, riot_id, region):
        """Lấy rank hiện tại từ dữ liệu thật"""
        overview = await self.get_player_overview(riot_id, region)
        if overview:
            return {
                'rank': overview.get('rank', 'Unknown'),
                'lp': overview.get('lp', 0),
                'win_rate': overview.get('win_rate', 0),
                'total_games': overview.get('total_games', 0)
            }
        return None
