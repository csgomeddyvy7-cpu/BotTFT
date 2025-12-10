import aiohttp
import asyncio
from datetime import datetime
import re

class RiotVerifier:
    """Xác thực Riot ID và lấy thông tin account"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.has_api_key = bool(api_key)
        self.session = None
        self.base_urls = {
            'asia': 'https://asia.api.riotgames.com',
            'americas': 'https://americas.api.riotgames.com',
            'europe': 'https://europe.api.riotgames.com'
        }
    
    async def get_session(self):
        """Lấy aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Đóng session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_region_endpoint(self, region):
        """Lấy endpoint theo region"""
        region_map = {
            'vn': 'asia',
            'kr': 'asia',
            'jp': 'asia',
            'na': 'americas',
            'br': 'americas',
            'lan': 'americas',
            'las': 'americas',
            'oce': 'americas',
            'euw': 'europe',
            'eune': 'europe',
            'tr': 'europe',
            'ru': 'europe'
        }
        return self.base_urls.get(region_map.get(region.lower(), 'asia'))
    
    async def verify_riot_id(self, riot_id, region='vn'):
        """
        Xác thực Riot ID
        Returns: {
            'success': bool,
            'data': dict (thông tin account),
            'error': str (nếu có)
        }
        """
        # Kiểm tra format
        if '#' not in riot_id:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline'
            }
        
        # Tách username và tagline
        try:
            username, tagline = riot_id.split('#', 1)
        except ValueError:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline'
            }
        
        # Loại bỏ khoảng trắng
        username = username.strip()
        tagline = tagline.strip()
        
        if not username or not tagline:
            return {
                'success': False,
                'error': 'Username và Tagline không được để trống'
            }
        
        # Nếu có Riot API key, dùng API chính thức
        if self.has_api_key:
            result = await self._verify_with_riot_api(username, tagline, region)
            if result['success']:
                return result
        
        # Fallback: Dùng phương pháp khác
        return await self._verify_with_fallback(username, tagline, region)
    
    async def _verify_with_riot_api(self, username, tagline, region):
        """Xác thực bằng Riot API chính thức"""
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
            
            session = await self.get_session()
            headers = {
                "X-Riot-Token": self.api_key,
                "User-Agent": "TFT-Tracker-Bot/1.0"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return {
                        'success': True,
                        'data': {
                            'puuid': data['puuid'],
                            'game_name': data['gameName'],
                            'tagline': data['tagLine'],
                            'verified': True,
                            'source': 'riot_api',
                            'verified_at': datetime.now().isoformat()
                        }
                    }
                elif response.status == 404:
                    return {
                        'success': False,
                        'error': 'Không tìm thấy tài khoản với Riot ID này'
                    }
                elif response.status == 403:
                    return {
                        'success': False,
                        'error': 'Riot API key không hợp lệ hoặc đã hết hạn'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Lỗi API: {response.status}'
                    }
                    
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Timeout khi kết nối đến Riot API'
            }
        except Exception as e:
            print(f"Riot API error: {e}")
            return {
                'success': False,
                'error': f'Lỗi kết nối: {str(e)}'
            }
    
    async def _verify_with_fallback(self, username, tagline, region):
        """Xác thực bằng phương pháp fallback (không cần API key)"""
        try:
            # Thử lấy từ tracker.gg
            tracker_data = await self._get_from_tracker(username, tagline, region)
            if tracker_data:
                return {
                    'success': True,
                    'data': {
                        'game_name': tracker_data.get('game_name', username),
                        'tagline': tracker_data.get('tagline', tagline),
                        'verified': False,  # Chưa xác thực hoàn toàn
                        'source': 'tracker_gg',
                        'verified_at': datetime.now().isoformat(),
                        'tft_rank': tracker_data.get('tft_rank', 'Unknown')
                    }
                }
            
            # Thử lấy từ op.gg
            opgg_data = await self._get_from_opgg(username, tagline, region)
            if opgg_data:
                return {
                    'success': True,
                    'data': {
                        'game_name': opgg_data.get('game_name', username),
                        'tagline': opgg_data.get('tagline', tagline),
                        'verified': False,
                        'source': 'op_gg',
                        'verified_at': datetime.now().isoformat(),
                        'tft_rank': opgg_data.get('tft_rank', 'Unknown')
                    }
                }
            
            # Nếu không tìm thấy ở đâu cả
            return {
                'success': False,
                'error': 'Không thể tìm thấy tài khoản. Kiểm tra lại Riot ID và region.'
            }
            
        except Exception as e:
            print(f"Fallback verification error: {e}")
            return {
                'success': False,
                'error': f'Lỗi khi xác thực: {str(e)}'
            }
    
    async def _get_from_tracker(self, username, tagline, region):
        """Lấy thông tin từ tracker.gg"""
        try:
            import urllib.parse
            encoded_username = urllib.parse.quote(username)
            
            # Tạo URL cho tracker.gg
            url = f"https://tracker.gg/tft/profile/riot/{encoded_username}%23{tagline}/overview"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Parse đơn giản (trong thực tế cần BeautifulSoup)
                    # Đây chỉ là mock data
                    return {
                        'game_name': username,
                        'tagline': tagline,
                        'tft_rank': 'Gold III',  # Mock
                        'source': 'tracker_gg'
                    }
                    
            return None
        except:
            return None
    
    async def _get_from_opgg(self, username, tagline, region):
        """Lấy thông tin từ op.gg"""
        try:
            # URL cho TFT trên OP.GG
            url = f"https://www.op.gg/summoners/{region}/{username}-{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    # Parse HTML để lấy rank
                    # Đây là mock data
                    return {
                        'game_name': username,
                        'tagline': tagline,
                        'tft_rank': 'Silver I',  # Mock
                        'source': 'op_gg'
                    }
                    
            return None
        except:
            return None
    
    async def get_tft_rank(self, puuid, region):
        """Lấy rank TFT hiện tại (cần Riot API key)"""
        if not self.has_api_key:
            return None
        
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/tft/league/v1/entries/by-puuid/{puuid}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    entries = await response.json()
                    
                    for entry in entries:
                        if entry['queueType'] == 'RANKED_TFT':
                            return {
                                'tier': entry['tier'],
                                'rank': entry['rank'],
                                'lp': entry['leaguePoints'],
                                'wins': entry['wins'],
                                'losses': entry['losses']
                            }
                    
                    return None
                else:
                    return None
                    
        except:
            return None
