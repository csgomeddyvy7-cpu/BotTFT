import aiohttp
import asyncio
from datetime import datetime
import re
import json
from urllib.parse import quote

class RiotVerifier:
    """Xác thực Riot ID và lấy thông tin THẬT từ tracker.gg"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.has_api_key = bool(api_key)
        self.session = None
    
    async def get_session(self):
        """Lấy aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Đóng session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def verify_riot_id(self, riot_id, region='vn'):
        """
        Xác thực Riot ID với dữ liệu THẬT từ tracker.gg
        """
        if '#' not in riot_id:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline'
            }
        
        try:
            username, tagline = riot_id.split('#', 1)
            username = username.strip()
            tagline = tagline.strip()
            
            # Ưu tiên dùng tracker.gg (dữ liệu thật)
            tracker_data = await self._get_tracker_gg_data(username, tagline, region)
            if tracker_data and tracker_data.get('success'):
                return tracker_data
            
            # Fallback: Dùng op.gg
            opgg_data = await self._get_opgg_data(username, tagline, region)
            if opgg_data and opgg_data.get('success'):
                return opgg_data
            
            return {
                'success': False,
                'error': 'Không tìm thấy tài khoản. Kiểm tra lại Riot ID và region.'
            }
            
        except Exception as e:
            print(f"Lỗi verify_riot_id: {e}")
            return {
                'success': False,
                'error': f'Lỗi kết nối: {str(e)[:100]}'
            }
    
    async def _get_tracker_gg_data(self, username, tagline, region):
        """Lấy dữ liệu THẬT từ tracker.gg"""
        try:
            # API tracker.gg cho TFT
            url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{quote(username)}%23{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Origin": "https://tracker.gg",
                "Referer": "https://tracker.gg/",
                "sec-ch-ua": '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse dữ liệu từ tracker.gg
                    account_info = self._parse_tracker_gg_response(data, username, tagline)
                    
                    if account_info:
                        return {
                            'success': True,
                            'data': account_info,
                            'source': 'tracker.gg'
                        }
                elif response.status == 404:
                    return {
                        'success': False,
                        'error': 'Không tìm thấy tài khoản trên tracker.gg'
                    }
                    
        except asyncio.TimeoutError:
            print(f"Timeout khi lấy dữ liệu từ tracker.gg cho {username}#{tagline}")
        except Exception as e:
            print(f"Lỗi tracker.gg API: {e}")
        
        return None
    
    def _parse_tracker_gg_response(self, data, username, tagline):
        """Parse dữ liệu từ tracker.gg response"""
        try:
            # Lấy thông tin cơ bản
            platform_info = data.get('data', {}).get('platformInfo', {})
            segments = data.get('data', {}).get('segments', [])
            
            # Tìm segment "overview" cho TFT
            tft_segment = None
            for segment in segments:
                if segment.get('type') == 'overview':
                    tft_segment = segment
                    break
            
            if not tft_segment:
                return None
            
            stats = tft_segment.get('stats', {})
            
            # Lấy rank TFT
            rank_stat = stats.get('rank', {})
            tier_stat = stats.get('tier', {})
            
            rank_display = rank_stat.get('displayValue', 'Unranked')
            tier_display = tier_stat.get('displayValue', '')
            
            # Ưu tiên tier nếu có
            rank_text = tier_display if tier_display else rank_display
            
            # Lấy LP
            rating_stat = stats.get('rating', {})
            lp = rating_stat.get('value', 0)
            
            # Lấy win/loss
            wins = stats.get('wins', {}).get('value', 0)
            losses = stats.get('losses', {}).get('value', 0)
            total_games = wins + losses
            
            # Lấy top percentage
            top_placement = stats.get('topPlacement', {})
            top_percentage = top_placement.get('percentile', 0)
            
            # Lấy level
            level_stat = stats.get('level', {})
            level = level_stat.get('value', 0)
            
            return {
                'game_name': platform_info.get('platformUserHandle', username),
                'tagline': platform_info.get('platformUserIdentifier', tagline).split('#')[-1],
                'verified': True,
                'source': 'tracker.gg',
                'verified_at': datetime.now().isoformat(),
                'tft_info': {
                    'rank': rank_text,
                    'lp': lp,
                    'wins': wins,
                    'losses': losses,
                    'total_games': total_games,
                    'win_rate': (wins / total_games * 100) if total_games > 0 else 0,
                    'top_percentage': top_percentage,
                    'level': level,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            print(f"Lỗi parse tracker.gg response: {e}")
            return None
    
    async def _get_opgg_data(self, username, tagline, region):
        """Lấy dữ liệu từ op.gg (fallback)"""
        try:
            # Chuyển region code cho op.gg
            region_map = {
                'vn': 'vn',
                'na': 'na',
                'euw': 'euw',
                'eune': 'eune',
                'kr': 'kr',
                'jp': 'jp'
            }
            
            opgg_region = region_map.get(region.lower(), 'vn')
            
            # URL op.gg cho TFT
            url = f"https://op.gg/api/v1.0/internal/bypass/summoners/{opgg_region}/{username}-{tagline}/tft/summary"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "vi-VN,vi;q=0.9"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse dữ liệu từ op.gg
                    account_info = self._parse_opgg_response(data, username, tagline)
                    
                    if account_info:
                        return {
                            'success': True,
                            'data': account_info,
                            'source': 'op.gg'
                        }
                        
        except Exception as e:
            print(f"Lỗi op.gg API: {e}")
        
        return None
    
    def _parse_opgg_response(self, data, username, tagline):
        """Parse dữ liệu từ op.gg response"""
        try:
            # Lấy thông tin rank TFT từ op.gg
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
            
            # Tạo rank text
            if tier == 'UNRANKED':
                rank_text = 'Chưa xếp hạng'
            else:
                rank_text = f"{tier_vn} {division}"
            
            # Lấy thông tin tổng quan
            summary = data.get('summary', {})
            wins = summary.get('win', 0)
            losses = summary.get('lose', 0)
            total_games = wins + losses
            
            return {
                'game_name': username,
                'tagline': tagline,
                'verified': True,
                'source': 'op.gg',
                'verified_at': datetime.now().isoformat(),
                'tft_info': {
                    'rank': rank_text,
                    'lp': lp,
                    'wins': wins,
                    'losses': losses,
                    'total_games': total_games,
                    'win_rate': (wins / total_games * 100) if total_games > 0 else 0,
                    'level': data.get('level', 0),
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            print(f"Lỗi parse op.gg response: {e}")
            return None
    
    async def get_tft_stats_live(self, riot_id, region='vn'):
        """Lấy thống kê TFT live từ tracker.gg"""
        try:
            username, tagline = riot_id.split('#', 1)
            
            # Gọi tracker.gg API
            url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{quote(username)}%23{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse match history
                    matches = self._parse_match_history(data)
                    
                    return {
                        'success': True,
                        'matches': matches[:5],  # Lấy 5 match gần nhất
                        'total_matches': len(matches)
                    }
                    
        except Exception as e:
            print(f"Lỗi get_tft_stats_live: {e}")
        
        return {'success': False, 'matches': [], 'total_matches': 0}
    
    def _parse_match_history(self, data):
        """Parse lịch sử match từ tracker.gg"""
        try:
            segments = data.get('data', {}).get('segments', [])
            matches = []
            
            for segment in segments:
                if segment.get('type') == 'match':
                    stats = segment.get('stats', {})
                    
                    placement = stats.get('placement', {}).get('value', 8)
                    game_length = stats.get('gameLength', {}).get('value', 0)
                    queue_id = stats.get('queueId', {}).get('value', 0)
                    
                    # Lấy thời gian match
                    metadata = segment.get('metadata', {})
                    timestamp = metadata.get('timestamp', None)
                    
                    if timestamp:
                        match_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        match_time = datetime.now()
                    
                    # Lấy traits (nếu có)
                    traits = []
                    for key, stat in stats.items():
                        if key.startswith('trait_') and stat.get('value', 0) > 0:
                            trait_name = key.replace('trait_', '').replace('_', ' ').title()
                            trait_tier = min(int(stat.get('value', 0)), 3)
                            traits.append({
                                'name': trait_name,
                                'tier': trait_tier
                            })
                    
                    matches.append({
                        'placement': placement,
                        'game_length': game_length,
                        'queue_id': queue_id,
                        'timestamp': match_time.isoformat(),
                        'traits': traits[:8],  # Giới hạn 8 traits
                        'match_id': f"tracker_{int(match_time.timestamp())}"
                    })
            
            # Sắp xếp theo thời gian mới nhất
            matches.sort(key=lambda x: x['timestamp'], reverse=True)
            return matches
            
        except Exception as e:
            print(f"Lỗi parse_match_history: {e}")
            return []
